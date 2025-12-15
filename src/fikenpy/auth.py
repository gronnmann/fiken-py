"""Authentication and rate limiting for Fiken API."""

import asyncio
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta

import httpx

from fikenpy.exceptions import FikenAuthError


class RateLimiter:
    """Rate limiter implementing Fiken's constraints:
    - Maximum 1 concurrent request
    - Maximum 4 requests per second
    """

    def __init__(self) -> None:
        """Initialize rate limiter."""
        self._lock = threading.Lock()
        self._request_times: deque[float] = deque(maxlen=4)
        self._max_requests_per_second = 4

    def acquire(self) -> None:
        """Acquire permission to make a request (sync version)."""
        with self._lock:
            now = time.time()
            # Remove requests older than 1 second
            while self._request_times and now - self._request_times[0] > 1.0:
                self._request_times.popleft()

            # If we've made 4 requests in the last second, wait
            if len(self._request_times) >= self._max_requests_per_second:
                sleep_time = 1.0 - (now - self._request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                now = time.time()
                # Clean up old requests after sleeping
                while self._request_times and now - self._request_times[0] > 1.0:
                    self._request_times.popleft()

            self._request_times.append(now)


class AsyncRateLimiter:
    """Async rate limiter implementing Fiken's constraints:
    - Maximum 1 concurrent request
    - Maximum 4 requests per second
    """

    def __init__(self) -> None:
        """Initialize async rate limiter."""
        self._semaphore = asyncio.Semaphore(1)  # Only 1 concurrent request
        self._request_times: deque[float] = deque(maxlen=4)
        self._max_requests_per_second = 4

    async def acquire(self) -> None:
        """Acquire permission to make a request (async version)."""
        async with self._semaphore:
            now = time.time()
            # Remove requests older than 1 second
            while self._request_times and now - self._request_times[0] > 1.0:
                self._request_times.popleft()

            # If we've made 4 requests in the last second, wait
            if len(self._request_times) >= self._max_requests_per_second:
                sleep_time = 1.0 - (now - self._request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                now = time.time()
                # Clean up old requests after sleeping
                while self._request_times and now - self._request_times[0] > 1.0:
                    self._request_times.popleft()

            self._request_times.append(now)


class BaseAuth(ABC):
    """Base authentication class."""

    @abstractmethod
    def get_headers(self) -> dict[str, str]:
        """Get authentication headers for requests."""
        pass

    def generate_request_id(self) -> str:
        """Generate a unique request ID for X-Request-ID header."""
        return str(uuid.uuid4())


class TokenAuth(BaseAuth):
    """Authentication using a personal API token."""

    def __init__(self, api_token: str) -> None:
        """Initialize token authentication.

        Args:
            api_token: Personal API token from Fiken
        """
        self.api_token = api_token

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "X-Request-ID": self.generate_request_id(),
        }


class OAuth2Handler(BaseAuth):
    """OAuth2 authentication with automatic token refresh."""

    # Token lifetime is 86157 seconds (~24 hours), refresh 5 minutes before expiry
    TOKEN_REFRESH_BUFFER = 300  # 5 minutes

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        token_url: str = "https://fiken.no/oauth/token",
    ) -> None:
        """Initialize OAuth2 handler.

        Args:
            access_token: Current OAuth2 access token
            refresh_token: OAuth2 refresh token
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            token_url: Token endpoint URL
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        # Assume token expires in 24 hours from initialization
        self.token_expires_at = datetime.now() + timedelta(seconds=86157)
        self._lock = threading.Lock()

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers, refreshing token if needed."""
        self._refresh_if_needed()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": self.generate_request_id(),
        }

    def _refresh_if_needed(self) -> None:
        """Refresh access token if it's about to expire."""
        with self._lock:
            if datetime.now() >= self.token_expires_at - timedelta(
                seconds=self.TOKEN_REFRESH_BUFFER
            ):
                self._refresh_token()

    def _refresh_token(self) -> None:
        """Refresh the access token using the refresh token."""
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = httpx.post(self.token_url, data=data, timeout=30.0)
            response.raise_for_status()
            token_data = response.json()

            self.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            expires_in = token_data.get("expires_in", 86157)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        except httpx.HTTPStatusError as e:
            raise FikenAuthError(
                f"Failed to refresh OAuth2 token: {e.response.text}",
                status_code=e.response.status_code,
                response_data=e.response.json() if e.response.text else {},
            ) from e
        except Exception as e:
            raise FikenAuthError(f"Failed to refresh OAuth2 token: {str(e)}") from e


class AsyncOAuth2Handler(BaseAuth):
    """Async OAuth2 authentication with automatic token refresh."""

    # Token lifetime is 86157 seconds (~24 hours), refresh 5 minutes before expiry
    TOKEN_REFRESH_BUFFER = 300  # 5 minutes

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        token_url: str = "https://fiken.no/oauth/token",
    ) -> None:
        """Initialize async OAuth2 handler.

        Args:
            access_token: Current OAuth2 access token
            refresh_token: OAuth2 refresh token
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            token_url: Token endpoint URL
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        # Assume token expires in 24 hours from initialization
        self.token_expires_at = datetime.now() + timedelta(seconds=86157)
        self._lock = asyncio.Lock()

    async def get_headers_async(self) -> dict[str, str]:
        """Get authentication headers, refreshing token if needed (async)."""
        await self._refresh_if_needed()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": self.generate_request_id(),
        }

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers (sync fallback, doesn't refresh)."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Request-ID": self.generate_request_id(),
        }

    async def _refresh_if_needed(self) -> None:
        """Refresh access token if it's about to expire."""
        async with self._lock:
            if datetime.now() >= self.token_expires_at - timedelta(
                seconds=self.TOKEN_REFRESH_BUFFER
            ):
                await self._refresh_token()

    async def _refresh_token(self) -> None:
        """Refresh the access token using the refresh token."""
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.token_url, data=data, timeout=30.0)
                response.raise_for_status()
                token_data = response.json()

                self.access_token = token_data["access_token"]
                if "refresh_token" in token_data:
                    self.refresh_token = token_data["refresh_token"]
                expires_in = token_data.get("expires_in", 86157)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        except httpx.HTTPStatusError as e:
            raise FikenAuthError(
                f"Failed to refresh OAuth2 token: {e.response.text}",
                status_code=e.response.status_code,
                response_data=e.response.json() if e.response.text else {},
            ) from e
        except Exception as e:
            raise FikenAuthError(f"Failed to refresh OAuth2 token: {str(e)}") from e
