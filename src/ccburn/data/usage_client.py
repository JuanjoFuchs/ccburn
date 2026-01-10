"""Anthropic Usage API client."""

import json
import time
import urllib.error
import urllib.request

try:
    from .credentials import get_access_token
    from .models import UsageSnapshot
except ImportError:
    from ccburn.data.credentials import get_access_token
    from ccburn.data.models import UsageSnapshot


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
    """Client for the Anthropic Usage API."""

    API_URL = "https://api.anthropic.com/api/oauth/usage"
    API_BETA_HEADER = "oauth-2025-04-20"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """Initialize the usage client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._last_response: dict | None = None
        self._last_error: str | None = None

    def fetch_usage(self) -> UsageSnapshot:
        """Fetch current usage data from the API.

        Returns:
            UsageSnapshot with current usage data

        Raises:
            CredentialsError: If credentials are missing or invalid
            APIError: If API returns an error
            NetworkError: If network request fails after retries
        """
        token = get_access_token()

        request = urllib.request.Request(
            self.API_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "anthropic-beta": self.API_BETA_HEADER,
            },
        )

        last_error = None

        for attempt, delay in enumerate(self.RETRY_DELAYS):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
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
                elif e.code >= 500:
                    # Server error - retry
                    last_error = NetworkError(f"Server error: {e.code} {e.reason}")
                else:
                    raise APIError(f"API error: {e.code} {e.reason}", status_code=e.code) from e

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

        # All retries exhausted
        if last_error:
            raise last_error
        raise NetworkError("Failed to fetch usage data after retries")

    def get_last_response(self) -> dict | None:
        """Get the last raw API response (for debugging).

        Returns:
            Last API response dictionary, or None if no successful call
        """
        return self._last_response

    def get_last_error(self) -> str | None:
        """Get the last error message.

        Returns:
            Last error message, or None if last call succeeded
        """
        return self._last_error
