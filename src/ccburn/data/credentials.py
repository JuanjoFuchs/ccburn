"""OAuth credentials reader for Claude Code."""

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class CredentialsError(Exception):
    """Base exception for credentials errors."""

    pass


class CredentialsNotFoundError(CredentialsError):
    """Credentials file not found."""

    pass


class TokenExpiredError(CredentialsError):
    """OAuth token has expired."""

    pass


class InvalidCredentialsError(CredentialsError):
    """Credentials file is malformed."""

    pass


def get_credentials_path() -> Path:
    """Get the path to Claude credentials file.

    Returns:
        Path to ~/.claude/.credentials.json
    """
    # Check environment variable first
    env_path = os.environ.get("CREDENTIALS_PATH")
    if env_path:
        return Path(env_path)

    return Path.home() / ".claude" / ".credentials.json"


def _read_credentials_from_keychain() -> dict | None:
    """Read credentials from macOS Keychain.

    Returns:
        Parsed credentials dictionary or None if not found/failed.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout.strip())
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return None


def _read_credentials_from_file() -> dict | None:
    """Read credentials from file.

    Returns:
        Parsed credentials dictionary or None if not found/failed.
    """
    creds_path = get_credentials_path()

    if not creds_path.exists():
        return None

    try:
        with open(creds_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError):
        return None


def read_credentials() -> dict:
    """Read credentials from the appropriate storage.

    On macOS, tries Keychain first, then falls back to file.
    On Linux/Windows, reads from file.

    Returns:
        Parsed credentials dictionary

    Raises:
        CredentialsNotFoundError: If credentials not found
        InvalidCredentialsError: If credentials are malformed
    """
    credentials = None

    # On macOS, try Keychain first
    if platform.system() == "Darwin":
        credentials = _read_credentials_from_keychain()

    # Fall back to file (or use file on non-macOS)
    if credentials is None:
        credentials = _read_credentials_from_file()

    if credentials is None:
        creds_path = get_credentials_path()
        if platform.system() == "Darwin":
            raise CredentialsNotFoundError(
                "Credentials not found in macOS Keychain or file.\n"
                "Please ensure Claude Code is installed and you are logged in.\n"
                "Run 'claude' to log in if needed."
            )
        else:
            raise CredentialsNotFoundError(
                f"Credentials file not found at {creds_path}\n"
                "Please ensure Claude Code is installed and you are logged in.\n"
                "Run 'claude' to log in if needed."
            )

    return credentials


def check_token_expired(credentials: dict) -> bool:
    """Check if the OAuth token has expired.

    Args:
        credentials: Parsed credentials dictionary

    Returns:
        True if token is expired, False otherwise
    """
    oauth = credentials.get("claudeAiOauth", {})
    expires_at = oauth.get("expiresAt")

    if not expires_at:
        return False  # No expiry info, assume valid

    try:
        # Parse ISO timestamp
        if isinstance(expires_at, str):
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        elif isinstance(expires_at, (int, float)):
            # Handle milliseconds (JS timestamps) vs seconds (Unix timestamps)
            if expires_at > 1e12:  # Likely milliseconds
                expires_at = expires_at / 1000
            expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        else:
            return False

        now = datetime.now(timezone.utc)
        return now >= expiry
    except (ValueError, TypeError):
        return False  # Can't parse, assume valid


def get_access_token() -> str:
    """Get the OAuth access token for API calls.

    Returns:
        Access token string

    Raises:
        CredentialsNotFoundError: If credentials file doesn't exist
        TokenExpiredError: If token has expired
        InvalidCredentialsError: If token not found in credentials
    """
    credentials = read_credentials()

    if check_token_expired(credentials):
        raise TokenExpiredError(
            "OAuth token has expired.\n"
            "Please restart Claude Code to refresh your token.\n"
            "Run 'claude' to refresh authentication."
        )

    oauth = credentials.get("claudeAiOauth", {})
    token = oauth.get("accessToken")

    if not token:
        raise InvalidCredentialsError(
            "No access token found in credentials.\n"
            "Please ensure you are logged in to Claude Code.\n"
            "Run 'claude' to log in."
        )

    return token
