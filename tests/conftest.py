"""Pytest fixtures for FikenPy tests."""

from datetime import datetime, timedelta
from typing import Any

import pytest
import respx

from fikenpy import AsyncFikenClient, FikenClient


@pytest.fixture
def api_token() -> str:
    """Return a test API token."""
    return "test_api_token_12345"


@pytest.fixture
def oauth_credentials() -> dict[str, str]:
    """Return test OAuth2 credentials."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "redirect_uri": "https://example.com/callback",
    }


@pytest.fixture
def oauth_tokens() -> dict[str, Any]:
    """Return test OAuth2 tokens."""
    expires_at = datetime.now() + timedelta(hours=24)
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_type": "Bearer",
        "expires_in": 86157,
        "scope": "read write",
        "expires_at": expires_at,
    }


@pytest.fixture
def company_slug() -> str:
    """Return a test company slug."""
    return "test-company"


@pytest.fixture
def base_url() -> str:
    """Return the base API URL."""
    return "https://api.fiken.no/api/v2"


@pytest.fixture
def sync_client(api_token: str) -> FikenClient:
    """Create a sync FikenClient for testing."""
    return FikenClient(api_token=api_token)


@pytest.fixture
async def async_client(api_token: str):
    """Create an async FikenClient for testing."""
    client = AsyncFikenClient(api_token=api_token)
    yield client
    await client.close()


@pytest.fixture
def mock_userinfo() -> dict[str, Any]:
    """Return mock user info data."""
    return {
        "name": "Test User",
        "email": "test@example.com",
    }


@pytest.fixture
def mock_company() -> dict[str, Any]:
    """Return mock company data."""
    return {
        "name": "Test Company AS",
        "slug": "test-company",
        "organizationNumber": "123456789",
        "vatType": "registered",
        "address": {
            "streetAddress": "Test Street 1",
            "city": "Oslo",
            "postCode": "0123",
            "country": "Norge",
        },
        "creationDate": "2024-01-01",
        "hasApiAccess": True,
        "testCompany": True,
    }


@pytest.fixture
def mock_contact() -> dict[str, Any]:
    """Return mock contact data."""
    return {
        "contactId": 1001,
        "name": "Test Customer AS",
        "organizationNumber": "987654321",
        "customerNumber": 1,
        "customer": True,
        "supplier": False,
        "email": "customer@example.com",
        "currency": "NOK",
        "language": "no",
        "inactive": False,
    }


@pytest.fixture
def respx_mock():
    """Create a respx mock context."""
    with respx.mock:
        yield respx
