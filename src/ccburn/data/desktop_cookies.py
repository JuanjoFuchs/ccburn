"""Claude Desktop cookie extraction for web API access.

Decrypts cookies from Claude Desktop's Chromium cookie database to enable
calling the claude.ai web usage API, which has a separate rate limit bucket
from the OAuth API that is currently broken (persistent 429s).

Supports:
- Windows: DPAPI key decryption + AES-256-GCM cookie decryption
- macOS: Keychain password + PBKDF2 key derivation + AES-128-CBC

See: https://github.com/anthropics/claude-code/issues/30930
"""

import json
import logging
import os
import platform
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Chromium prepends a 32-byte binary header to decrypted cookie values
DECRYPTED_PREFIX_LEN = 32


class CookieError(Exception):
    """Failed to extract cookies from Claude Desktop."""

    pass


@dataclass
class DesktopCookies:
    """Decrypted cookies from Claude Desktop."""

    session_key: str
    org_id: str
    cf_clearance: str | None = None

    @property
    def cookie_header(self) -> str:
        """Format cookies as an HTTP Cookie header value."""
        parts = [f"sessionKey={self.session_key}", f"lastActiveOrg={self.org_id}"]
        if self.cf_clearance:
            parts.append(f"cf_clearance={self.cf_clearance}")
        return "; ".join(parts)

    @property
    def usage_url(self) -> str:
        """The web API usage endpoint URL."""
        return f"https://claude.ai/api/organizations/{self.org_id}/usage"


def get_desktop_cookies() -> DesktopCookies:
    """Extract and decrypt cookies from Claude Desktop.

    Returns:
        DesktopCookies with session_key, org_id, and optionally cf_clearance.

    Raises:
        CookieError: If cookies cannot be extracted.
    """
    system = platform.system()
    if system == "Windows":
        return _get_cookies_windows()
    elif system == "Darwin":
        return _get_cookies_macos()
    else:
        raise CookieError(f"Unsupported platform: {system}")


# === Windows Implementation ===


def _get_cookies_windows() -> DesktopCookies:
    """Extract cookies on Windows using DPAPI + AES-256-GCM."""
    import base64

    # Paths
    appdata = os.environ.get("APPDATA", "")
    local_state_path = os.path.join(appdata, "Claude", "Local State")
    cookies_db_path = os.path.join(appdata, "Claude", "Network", "Cookies")

    if not os.path.exists(local_state_path):
        raise CookieError("Claude Desktop not installed (Local State not found)")
    if not os.path.exists(cookies_db_path):
        raise CookieError("Claude Desktop cookie database not found")

    # Step 1: Get AES key via DPAPI
    try:
        with open(local_state_path) as f:
            encrypted_key_b64 = json.load(f)["os_crypt"]["encrypted_key"]
    except (json.JSONDecodeError, KeyError) as e:
        raise CookieError(f"Failed to read encryption key: {e}") from e

    encrypted_key = base64.b64decode(encrypted_key_b64)
    if not encrypted_key.startswith(b"DPAPI"):
        raise CookieError("Unexpected encryption key format (missing DPAPI prefix)")

    aes_key = _dpapi_decrypt(encrypted_key[5:])

    # Step 2: Copy cookie DB (it's locked while Claude Desktop is running)
    encrypted_cookies = _read_cookie_db(cookies_db_path)

    # Step 3: Decrypt cookies with AES-256-GCM
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise CookieError(
            "cryptography package required for cookie decryption.\n"
            "Install with: pip install cryptography"
        ) from e

    aesgcm = AESGCM(aes_key)
    cookies = {}
    for name, encrypted_value in encrypted_cookies.items():
        # Format: v10 prefix (3 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
        nonce = encrypted_value[3:15]
        ciphertext_with_tag = encrypted_value[15:]
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
            cookies[name] = plaintext[DECRYPTED_PREFIX_LEN:].decode("utf-8")
        except Exception as e:
            log.warning("Failed to decrypt cookie %s: %s", name, e)

    return _build_desktop_cookies(cookies)


def _dpapi_decrypt(data: bytes) -> bytes:
    """Decrypt data using Windows DPAPI (CryptUnprotectData)."""
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise CookieError("DPAPI decryption failed")

    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


# === macOS Implementation ===


def _get_cookies_macos() -> DesktopCookies:
    """Extract cookies on macOS using Keychain + PBKDF2 + AES-128-CBC."""
    import hashlib

    cookies_db_path = os.path.expanduser(
        "~/Library/Application Support/Claude/Cookies"
    )
    if not os.path.exists(cookies_db_path):
        raise CookieError("Claude Desktop not installed (Cookies DB not found)")

    # Step 1: Get encryption key from Keychain via PBKDF2
    try:
        password = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Safe Storage", "-w"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise CookieError(f"Failed to read Claude Safe Storage from Keychain: {e}") from e

    aes_key = hashlib.pbkdf2_hmac("sha1", password.encode(), b"saltysalt", 1003, dklen=16)

    # Step 2: Read cookie DB
    encrypted_cookies = _read_cookie_db(cookies_db_path)

    # Step 3: Decrypt with AES-128-CBC

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
    except ImportError as e:
        raise CookieError(
            "cryptography package required for cookie decryption.\n"
            "Install with: pip install cryptography"
        ) from e

    cookies = {}
    iv = b"\x20" * 16  # Chromium uses space-filled IV on macOS
    for name, encrypted_value in encrypted_cookies.items():
        if not encrypted_value.startswith(b"v10"):
            continue
        try:
            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            padded = decryptor.update(encrypted_value[3:]) + decryptor.finalize()
            # Remove PKCS7 padding
            unpadder = PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
            cookies[name] = plaintext[DECRYPTED_PREFIX_LEN:].decode("utf-8")
        except Exception as e:
            log.warning("Failed to decrypt cookie %s: %s", name, e)

    return _build_desktop_cookies(cookies)


# === Shared Helpers ===


def _read_cookie_db(db_path: str) -> dict[str, bytes]:
    """Read encrypted cookie values from the Chromium SQLite database.

    Handles the file being locked by Claude Desktop by copying it first.
    """
    needed = ("sessionKey", "lastActiveOrg", "cf_clearance")
    placeholders = ",".join("?" for _ in needed)
    query = (
        f"SELECT name, encrypted_value FROM cookies "
        f"WHERE host_key LIKE '%claude.ai' AND name IN ({placeholders})"
    )

    # Try reading directly first (works when Claude Desktop is closed)
    try:
        conn = sqlite3.connect(db_path, timeout=1)
        rows = conn.execute(query, needed).fetchall()
        conn.close()
        if rows:
            return dict(rows)
    except sqlite3.OperationalError:
        pass

    # File is locked — try copying it
    tmp_path = os.path.join(tempfile.gettempdir(), "ccburn_cookies_tmp.db")
    copied = False

    # On macOS, sqlite3 CLI can read past advisory locks
    if platform.system() == "Darwin":
        try:
            hex_rows = subprocess.run(
                [
                    "sqlite3",
                    db_path,
                    "SELECT name, hex(encrypted_value) FROM cookies "
                    "WHERE host_key = '.claude.ai' "
                    "AND name IN ('sessionKey', 'lastActiveOrg', 'cf_clearance');",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            ).stdout.strip()
            if hex_rows:
                result = {}
                for line in hex_rows.split("\n"):
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        result[parts[0]] = bytes.fromhex(parts[1])
                if result:
                    return result
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # Try shutil.copy2 (works on macOS, may work on Windows if Desktop is closed)
    if not copied:
        try:
            shutil.copy2(db_path, tmp_path)
            copied = True
        except (PermissionError, OSError):
            pass

    # Windows: try taskkill on the network service subprocess
    if not copied and platform.system() == "Windows":
        copied = _copy_cookies_kill_network_service(db_path, tmp_path)

    if not copied:
        raise CookieError(
            "Cannot read Claude Desktop cookies (database is locked).\n"
            "Try closing Claude Desktop briefly, then re-run ccburn."
        )

    try:
        conn = sqlite3.connect(tmp_path, timeout=1)
        rows = conn.execute(query, needed).fetchall()
        conn.close()
        return dict(rows)
    except sqlite3.OperationalError as e:
        raise CookieError(f"Failed to read copied cookie database: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _copy_cookies_kill_network_service(db_path: str, tmp_path: str) -> bool:
    """On Windows, kill the Chromium network service subprocess to release the
    cookie DB lock, copy the file, and let it auto-respawn.

    The network service holds an exclusive lock on the Cookies file.
    Killing it releases the lock briefly (~10-50ms) before Chromium respawns it.
    We retry in a tight loop to catch that window.

    Returns True if copy succeeded.
    """
    import time

    try:
        # Find the network service PID
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "name='claude.exe' and CommandLine like '%network.mojom.NetworkService%'",
                "get",
                "ProcessId",
                "/format:list",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pid = None
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("ProcessId="):
                pid = line.split("=", 1)[1].strip()
                break

        if not pid:
            return False

        # Kill the network service (it auto-respawns within ~1 second)
        subprocess.run(
            ["taskkill", "/PID", pid, "/F"],
            capture_output=True,
            timeout=5,
        )

        # Retry copy in a tight loop — the lock is released briefly before respawn
        for _ in range(50):
            try:
                with open(db_path, "rb") as f:
                    data = f.read()
                with open(tmp_path, "wb") as f:
                    f.write(data)
                return True
            except PermissionError:
                time.sleep(0.01)  # 10ms

        return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def _build_desktop_cookies(cookies: dict[str, str]) -> DesktopCookies:
    """Build DesktopCookies from a name->value dict."""
    session_key = cookies.get("sessionKey")
    org_id = cookies.get("lastActiveOrg")

    if not session_key:
        raise CookieError("sessionKey cookie not found in Claude Desktop")
    if not org_id:
        raise CookieError("lastActiveOrg cookie not found in Claude Desktop")

    return DesktopCookies(
        session_key=session_key,
        org_id=org_id,
        cf_clearance=cookies.get("cf_clearance"),
    )
