"""Anthropic Usage API client.

Tries two strategies to fetch usage data:
1. Web API via Claude Desktop cookies + curl (bypasses OAuth 429 rate limit)
2. OAuth API (original method, currently rate-limited)

See: https://github.com/anthropics/claude-code/issues/30930
"""

import json
import logging
import os
import platform
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request

try:
    from .credentials import CredentialsError, get_access_token
    from .desktop_cookies import CookieError, DesktopCookies, get_desktop_cookies
    from .models import UsageSnapshot
except ImportError:
    from ccburn.data.credentials import CredentialsError, get_access_token
    from ccburn.data.desktop_cookies import CookieError, DesktopCookies, get_desktop_cookies
    from ccburn.data.models import UsageSnapshot

log = logging.getLogger(__name__)


def _create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context with proper certificate handling.

    PyInstaller bundles on macOS may not find the system certificate store.
    This tries multiple certificate sources to ensure HTTPS works reliably.
    """
    # Try certifi first (most reliable for bundled apps)
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    # If SSL_CERT_FILE or SSL_CERT_DIR is set, the default context uses it
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return ssl.create_default_context()

    # On macOS with PyInstaller, the bundled ssl module can't find the system
    # certificate store. Try well-known macOS certificate paths.
    if platform.system() == "Darwin":
        for cert_path in [
            "/etc/ssl/cert.pem",
            "/opt/homebrew/etc/openssl@3/cert.pem",
            "/opt/homebrew/etc/openssl/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem",
            "/usr/local/etc/openssl/cert.pem",
        ]:
            if os.path.isfile(cert_path):
                try:
                    return ssl.create_default_context(cafile=cert_path)
                except ssl.SSLError:
                    continue

    # Fall back to default context (works on most non-bundled installs)
    return ssl.create_default_context()


class UsageClientError(Exception):
    """Base exception for usage client errors."""

    pass


class APIError(UsageClientError):
    """API returned an error response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NetworkError(UsageClientError):
    """Network error during API call."""

    pass


class UsageClient:
    """Client for the Anthropic Usage API.

    Tries the web API (via Claude Desktop cookies + curl) first, which uses a
    separate rate limit bucket unaffected by the persistent 429 on the OAuth API.
    Falls back to the OAuth API if web API is unavailable.
    """

    API_URL = "https://api.anthropic.com/api/oauth/usage"
    API_BETA_HEADER = "oauth-2025-04-20"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._ssl_context = _create_ssl_context()
        self._last_response: dict | None = None
        self._last_error: str | None = None
        self._cookies: DesktopCookies | None = None
        self._cookies_failed: bool = False  # Don't retry cookies if extraction failed
        self._has_curl: bool | None = None

    def _check_curl(self) -> bool:
        """Check if curl is available on the system."""
        if self._has_curl is None:
            self._has_curl = shutil.which("curl") is not None
        return self._has_curl

    def _get_cookies(self) -> DesktopCookies | None:
        """Get cached or fresh Claude Desktop cookies."""
        if self._cookies_failed:
            return None
        if self._cookies is not None:
            return self._cookies
        try:
            self._cookies = get_desktop_cookies()
            return self._cookies
        except CookieError as e:
            log.debug("Cookie extraction failed: %s", e)
            self._cookies_failed = True
            return None

    def _fetch_web_api(self, cookies: DesktopCookies) -> UsageSnapshot:
        """Fetch usage via claude.ai web API using curl.

        curl is needed because Cloudflare validates TLS fingerprints and blocks
        Python's urllib/httpx. curl's TLS fingerprint passes Cloudflare when
        combined with the cf_clearance cookie.

        Raises:
            NetworkError: If the request fails
        """
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-w",
                "\n%{http_code}",
                "-H",
                f"Cookie: {cookies.cookie_header}",
                "-H",
                "Accept: application/json",
                "-H",
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--max-time",
                str(self.timeout),
                cookies.usage_url,
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout + 5,
        )

        lines = result.stdout.strip().rsplit("\n", 1)
        if len(lines) != 2:
            raise NetworkError("Empty response from web API")

        body, status_str = lines
        try:
            status = int(status_str)
        except ValueError:
            raise NetworkError(f"Invalid status from web API: {status_str}")

        if status == 403 and "Just a moment" in body:
            raise NetworkError("Cloudflare challenge — cf_clearance cookie may be expired")
        if status != 200:
            raise NetworkError(f"Web API returned {status}")

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise NetworkError(f"Invalid JSON from web API: {e}")

        self._last_response = data
        self._last_error = None
        return UsageSnapshot.from_api_response(data)

    def _fetch_oauth_api(self) -> UsageSnapshot:
        """Fetch usage via the OAuth API (original method).

        Retries with backoff on 5xx/network errors.
        On 429, gives up immediately (persistent rate limit).
        """
        token = get_access_token()
        last_error = None

        for attempt, delay in enumerate(self.RETRY_DELAYS):
            try:
                request = urllib.request.Request(
                    self.API_URL,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                        "anthropic-beta": self.API_BETA_HEADER,
                    },
                )
                with urllib.request.urlopen(
                    request, timeout=self.timeout, context=self._ssl_context
                ) as response:
                    data = json.loads(response.read())
                    self._last_response = data
                    self._last_error = None
                    return UsageSnapshot.from_api_response(data)

            except urllib.error.HTTPError as e:
                self._last_error = f"HTTP {e.code}: {e.reason}"
                if e.code == 401:
                    raise APIError(
                        "Authentication failed. Your token may be invalid.\n"
                        "Please restart Claude Code to refresh authentication.",
                        status_code=e.code,
                    ) from e
                elif e.code == 403:
                    raise APIError(
                        "Access forbidden. You may not have permission to access usage data.",
                        status_code=e.code,
                    ) from e
                elif e.code == 429:
                    last_error = NetworkError(
                        "Rate limited by the API (429). "
                        "This is a known issue — see github.com/anthropics/claude-code/issues/30930"
                    )
                    break  # Don't retry 429s — they're persistent
                elif e.code >= 500:
                    last_error = NetworkError(f"Server error: {e.code} {e.reason}")
                else:
                    raise APIError(
                        f"API error: {e.code} {e.reason}", status_code=e.code
                    ) from e

            except urllib.error.URLError as e:
                self._last_error = str(e.reason)
                last_error = NetworkError(f"Network error: {e.reason}")

            except json.JSONDecodeError as e:
                self._last_error = f"Invalid JSON: {e}"
                raise APIError(f"Invalid JSON response from API: {e}") from e

            except TimeoutError:
                self._last_error = "Request timed out"
                last_error = NetworkError("Request timed out")

            # Wait before retry (except on last attempt)
            if attempt < len(self.RETRY_DELAYS) - 1:
                time.sleep(delay)

        if last_error:
            raise last_error
        raise NetworkError("Failed to fetch usage data after retries")

    def fetch_usage(self) -> UsageSnapshot:
        """Fetch current usage data.

        Strategy:
        1. Try web API via Claude Desktop cookies + curl (separate rate limit)
        2. Fall back to OAuth API

        Returns:
            UsageSnapshot with current usage data

        Raises:
            CredentialsError: If credentials are missing or invalid
            APIError: If API returns an error
            NetworkError: If all methods fail
        """
        # Strategy 1: OAuth API (clean path, no side effects)
        try:
            return self._fetch_oauth_api()
        except NetworkError as e:
            log.debug("OAuth API failed: %s", e)
            oauth_error = e

        # Strategy 2: Web API via Claude Desktop cookies + curl
        # Fallback for the persistent 429 rate limit on the OAuth endpoint.
        # See: https://github.com/anthropics/claude-code/issues/30930
        if self._check_curl():
            cookies = self._get_cookies()
            if cookies:
                try:
                    return self._fetch_web_api(cookies)
                except (NetworkError, subprocess.SubprocessError) as e:
                    log.debug("Web API failed: %s", e)
                    self._last_error = str(e)
                    # Invalidate cookies on Cloudflare challenge (need fresh cf_clearance)
                    if "cf_clearance" in str(e):
                        self._cookies = None
                        self._cookies_failed = False

        # Both strategies failed — raise the original OAuth error
        raise oauth_error

    def get_last_response(self) -> dict | None:
        """Get the last raw API response (for debugging)."""
        return self._last_response

    def get_last_error(self) -> str | None:
        """Get the last error message."""
        return self._last_error
