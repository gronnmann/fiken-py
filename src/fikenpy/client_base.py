"""Base client functionality for Fiken API."""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO, Generic, TypeVar, cast

import httpx
from pydantic import BaseModel

from fikenpy.exceptions import (
    FikenAPIError,
    FikenAuthError,
    FikenMethodNotAllowedError,
    FikenNotFoundError,
    FikenRateLimitError,
    FikenServerError,
    FikenUnsupportedMediaTypeError,
    FikenValidationError,
)

T = TypeVar("T", bound=BaseModel)


class ClientConfig:
    """Configuration for Fiken API client."""

    BASE_URL = "https://api.fiken.no/api/v2"
    DEFAULT_TIMEOUT = 30.0


def parse_error_response(response: httpx.Response) -> FikenAPIError:
    """Parse error response and return appropriate exception.

    Args:
        response: HTTP response from the API

    Returns:
        Appropriate FikenAPIError subclass
    """
    status_code = response.status_code
    try:
        error_data: dict[str, Any] = response.json()
        message = error_data.get("message", response.text or "Unknown error")
    except Exception:
        message = response.text or f"HTTP {status_code} error"
        error_data = {}

    # Pass request and response to maintain httpx.HTTPStatusError compatibility
    request = response.request

    if status_code == 400:
        return FikenValidationError(message, status_code, error_data, request, response)
    elif status_code in (401, 403):
        return FikenAuthError(message, status_code, error_data, request, response)
    elif status_code == 404:
        return FikenNotFoundError(message, status_code, error_data, request, response)
    elif status_code == 405:
        return FikenMethodNotAllowedError(
            message, status_code, error_data, request, response
        )
    elif status_code == 415:
        return FikenUnsupportedMediaTypeError(
            message, status_code, error_data, request, response
        )
    elif status_code == 429:
        return FikenRateLimitError(message, status_code, error_data, request, response)
    elif status_code >= 500:
        return FikenServerError(message, status_code, error_data, request, response)
    else:
        return FikenAPIError(message, status_code, error_data, request, response)


def prepare_attachment(
    file: Path | str | BinaryIO,
    filename: str | None = None,
) -> tuple[str, bytes, str]:
    """Prepare file attachment for upload.

    Args:
        file: File path, file path string, or file-like object
        filename: Optional filename override

    Returns:
        Tuple of (filename, file_bytes, content_type)
    """
    if isinstance(file, (Path, str)):
        file_path = Path(file)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        actual_filename = filename or file_path.name

        # Read bytes immediately to avoid async file handle issues
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        return actual_filename, file_bytes, content_type
    else:
        # file-like object - read into bytes
        actual_filename = filename or "attachment"
        if hasattr(file, "read"):
            file_bytes = file.read()
        else:
            # Already bytes
            file_bytes = file
        content_type = (
            mimetypes.guess_type(actual_filename)[0] or "application/octet-stream"
        )
        return actual_filename, file_bytes, content_type


class PaginatedIterator(Iterator[T]):
    """Iterator for paginated API responses.

    Automatically fetches subsequent pages as needed.
    """

    def __init__(
        self,
        client: Any,  # httpx.Client or httpx.AsyncClient
        url: str,
        params: dict[str, Any],
        model_class: type[T],
        headers: dict[str, str],
    ) -> None:
        """Initialize paginated iterator.

        Args:
            client: HTTP client instance
            url: Base URL for the request
            params: Query parameters
            model_class: Pydantic model class for response items
            headers: Request headers
        """
        self.client = client
        self.url = url
        self.params = params.copy()
        self.model_class = model_class
        self.headers = headers
        self.current_page = 0
        self.total_pages: int | None = None
        self.items: list[T] = []
        self.index = 0
        self._fetched_first_page = False

    def __iter__(self) -> Iterator[T]:
        """Return iterator."""
        return self

    def __next__(self) -> T:
        """Get next item, fetching new page if needed."""
        if not self._fetched_first_page:
            self._fetch_page(0)
            self._fetched_first_page = True

        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return item

        # Need to fetch next page
        if self.total_pages is not None and self.current_page >= self.total_pages - 1:
            raise StopIteration

        self._fetch_page(self.current_page + 1)

        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return item

        raise StopIteration

    def _fetch_page(self, page: int) -> None:
        """Fetch a specific page of results.

        Args:
            page: Page number to fetch
        """
        params = self.params.copy()
        params["page"] = page

        response = self.client.get(
            self.url,
            params=params,
            headers=self.headers,
        )

        if response.status_code != 200:
            raise parse_error_response(response)

        # Parse pagination headers
        if "Fiken-Api-Page" in response.headers:
            self.current_page = int(response.headers["Fiken-Api-Page"])
        if "Fiken-Api-Page-Count" in response.headers:
            self.total_pages = int(response.headers["Fiken-Api-Page-Count"])

        # Parse response data
        data: Any = response.json()
        if isinstance(data, list):
            self.items = [self.model_class.model_validate(item) for item in data]
        else:
            # Handle case where API returns object with results array
            self.items = []

        self.index = 0


class AsyncPaginatedIterator(Generic[T]):
    """Async iterator for paginated API responses.

    Automatically fetches subsequent pages as needed.
    """

    def __init__(
        self,
        client: Any,  # httpx.AsyncClient
        url: str,
        params: dict[str, Any],
        model_class: type[T],
        headers: dict[str, str],
    ) -> None:
        """Initialize async paginated iterator.

        Args:
            client: Async HTTP client instance
            url: Base URL for the request
            params: Query parameters
            model_class: Pydantic model class for response items
            headers: Request headers
        """
        self.client = client
        self.url = url
        self.params = params.copy()
        self.model_class: type[BaseModel] = model_class
        self.headers = headers
        self.current_page = 0
        self.total_pages: int | None = None
        self.items: list[BaseModel] = []
        self.index = 0
        self._fetched_first_page = False

    def __aiter__(self) -> AsyncPaginatedIterator[T]:
        """Return async iterator."""
        return self

    async def __anext__(self) -> T:
        """Get next item, fetching new page if needed."""
        if not self._fetched_first_page:
            await self._fetch_page(0)
            self._fetched_first_page = True

        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return cast("T", item)

        # Need to fetch next page
        if self.total_pages is not None and self.current_page >= self.total_pages - 1:
            raise StopAsyncIteration

        await self._fetch_page(self.current_page + 1)

        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return cast("T", item)

        raise StopAsyncIteration

    async def _fetch_page(self, page: int) -> None:
        """Fetch a specific page of results.

        Args:
            page: Page number to fetch
        """
        params = self.params.copy()
        params["page"] = page

        response = await self.client.get(
            self.url,
            params=params,
            headers=self.headers,
        )

        if response.status_code != 200:
            raise parse_error_response(response)

        # Parse pagination headers
        if "Fiken-Api-Page" in response.headers:
            self.current_page = int(response.headers["Fiken-Api-Page"])
        if "Fiken-Api-Page-Count" in response.headers:
            self.total_pages = int(response.headers["Fiken-Api-Page-Count"])

        # Parse response data
        data = response.json()
        if isinstance(data, list):
            self.items = [self.model_class.model_validate(item) for item in data]
        else:
            # Handle case where API returns object with results array
            self.items = []

        self.index = 0
