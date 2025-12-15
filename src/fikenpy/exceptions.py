"""Exceptions for the FikenPy library."""

from typing import Any

import httpx


class FikenAPIError(httpx.HTTPStatusError):
    """Base exception for all Fiken API errors.

    Extends httpx.HTTPStatusError so users can catch both FikenAPIError
    and httpx.HTTPStatusError to handle API errors.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict[str, Any] | None = None,
        request: httpx.Request | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        """Initialize FikenAPIError.

        Args:
            message: Error message
            status_code: HTTP status code from the API response
            response_data: Full response data from the API
            request: The request that caused the error
            response: The response from the API
        """
        # Call httpx.HTTPStatusError's __init__ if we have request and response
        if request and response:
            super().__init__(message, request=request, response=response)
        else:
            # Fallback for cases where we don't have full httpx objects
            Exception.__init__(self, message)

        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class FikenAuthError(FikenAPIError):
    """Raised when authentication fails (401/403)."""

    pass


class FikenRateLimitError(FikenAPIError):
    """Raised when rate limit is exceeded (429).

    Fiken allows only 1 concurrent request and max 4 requests per second.
    """

    pass


class FikenNotFoundError(FikenAPIError):
    """Raised when a resource is not found (404)."""

    pass


class FikenValidationError(FikenAPIError):
    """Raised when request validation fails (400)."""

    pass


class FikenMethodNotAllowedError(FikenAPIError):
    """Raised when HTTP method is not allowed (405)."""

    pass


class FikenUnsupportedMediaTypeError(FikenAPIError):
    """Raised when media type is not supported (415)."""

    pass


class FikenServerError(FikenAPIError):
    """Raised when server encounters an error (5xx)."""

    pass
