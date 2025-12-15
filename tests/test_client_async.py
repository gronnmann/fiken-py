"""Tests for AsyncFikenClient (asynchronous)."""

import pytest
import respx
from httpx import Response

from fikenpy import AsyncFikenClient
from fikenpy.exceptions import (
    FikenAuthError,
    FikenNotFoundError,
    FikenRateLimitError,
)


class TestAuthentication:
    """Test authentication methods."""

    @pytest.mark.asyncio
    async def test_token_auth_initialization(self, api_token: str):
        """Test client initialization with API token."""
        async with AsyncFikenClient(api_token=api_token) as client:
            assert client.auth is not None

    @pytest.mark.asyncio
    async def test_oauth_auth_initialization(self, oauth_tokens: dict):
        """Test client initialization with OAuth2 tokens."""
        async with AsyncFikenClient(
            access_token=oauth_tokens["access_token"],
            refresh_token=oauth_tokens["refresh_token"],
            client_id="test_client_id",
            client_secret="test_client_secret",
        ) as client:
            assert client.auth is not None

    def test_missing_credentials_raises_error(self):
        """Test that missing credentials raises ValueError."""
        try:
            AsyncFikenClient()
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Either api_token or all OAuth2 credentials" in str(e)

    @pytest.mark.asyncio
    async def test_context_manager(self, api_token: str):
        """Test client works as async context manager."""
        async with AsyncFikenClient(api_token=api_token) as client:
            assert client is not None


class TestUserEndpoints:
    """Test user-related endpoints."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_user(self, api_token: str, base_url: str):
        """Test getting current user info."""
        route = respx.get(f"{base_url}/user").mock(
            return_value=Response(
                200,
                json={
                    "name": "Test User",
                    "email": "test@example.com",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            user = await client.get_user()
            assert user.name == "Test User"
            assert user.email == "test@example.com"
            assert route.called


class TestCompanyEndpoints:
    """Test company-related endpoints."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_companies(self, api_token: str, base_url: str):
        """Test getting all companies."""
        route = respx.get(f"{base_url}/companies").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "name": "Test Company AS",
                        "slug": "test-company",
                        "organizationNumber": "123456789",
                    }
                ],
                headers={
                    "Fiken-Api-Page": "0",
                    "Fiken-Api-Page-Count": "1",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            companies = []
            iterator = client.get_companies()
            async for company in iterator:
                companies.append(company)

            assert len(companies) == 1
            assert companies[0].name == "Test Company AS"
            assert companies[0].slug == "test-company"
            assert route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_company(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test getting a specific company."""
        route = respx.get(f"{base_url}/companies/{company_slug}").mock(
            return_value=Response(
                200,
                json={
                    "name": "Test Company AS",
                    "slug": company_slug,
                    "organizationNumber": "123456789",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            company = await client.get_company(company_slug)
            assert company.name == "Test Company AS"
            assert company.slug == company_slug
            assert route.called


class TestContactEndpoints:
    """Test contact-related endpoints."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_contacts(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test getting all contacts."""
        route = respx.get(f"{base_url}/companies/{company_slug}/contacts").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "contactId": 1001,
                        "name": "Test Customer AS",
                        "email": "customer@example.com",
                    }
                ],
                headers={
                    "Fiken-Api-Page": "0",
                    "Fiken-Api-Page-Count": "1",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            contacts = []
            async for contact in client.get_contacts(company_slug):
                contacts.append(contact)

            assert len(contacts) == 1
            assert contacts[0].name == "Test Customer AS"
            assert route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_contact(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test getting a specific contact."""
        contact_id = 1001
        route = respx.get(
            f"{base_url}/companies/{company_slug}/contacts/{contact_id}"
        ).mock(
            return_value=Response(
                200,
                json={
                    "contactId": contact_id,
                    "name": "Test Customer AS",
                    "email": "customer@example.com",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            contact = await client.get_contact(company_slug, contact_id)
            assert contact.contact_id == contact_id
            assert contact.name == "Test Customer AS"
            assert route.called


class TestProductEndpoints:
    """Test product-related endpoints."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_products(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test getting all products."""
        route = respx.get(f"{base_url}/companies/{company_slug}/products").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "productId": 3001,
                        "name": "Test Product",
                        "unitPrice": 10000,
                        "incomeAccount": "3000",
                        "vatType": "HIGH",
                        "active": True,
                    }
                ],
                headers={
                    "Fiken-Api-Page": "0",
                    "Fiken-Api-Page-Count": "1",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            products = []
            async for product in client.get_products(company_slug):
                products.append(product)

            assert len(products) == 1
            assert products[0].name == "Test Product"
            assert products[0].unit_price == 10000
            assert route.called


class TestInvoiceEndpoints:
    """Test invoice-related endpoints."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_invoices(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test getting all invoices."""
        route = respx.get(f"{base_url}/companies/{company_slug}/invoices").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "invoiceId": 4001,
                        "invoiceNumber": 10001,
                        "issueDate": "2024-12-10",
                        "dueDate": "2024-12-24",
                        "settled": False,
                    }
                ],
                headers={
                    "Fiken-Api-Page": "0",
                    "Fiken-Api-Page-Count": "1",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            invoices = []
            async for invoice in client.get_invoices(company_slug):
                invoices.append(invoice)

            assert len(invoices) == 1
            assert invoices[0].invoice_number == 10001
            assert route.called


class TestPagination:
    """Test pagination functionality."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_automatic_pagination(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test that pagination automatically fetches all pages."""
        # First page
        respx.get(f"{base_url}/companies/{company_slug}/contacts").mock(
            return_value=Response(
                200,
                json=[{"contactId": i, "name": f"Contact {i}"} for i in range(25)],
                headers={
                    "Fiken-Api-Page": "0",
                    "Fiken-Api-Page-Count": "3",
                },
            )
        )

        # Second page
        respx.get(f"{base_url}/companies/{company_slug}/contacts", params={"page": 1}).mock(
            return_value=Response(
                200,
                json=[{"contactId": i, "name": f"Contact {i}"} for i in range(25, 50)],
                headers={
                    "Fiken-Api-Page": "1",
                    "Fiken-Api-Page-Count": "3",
                },
            )
        )

        # Third page
        respx.get(f"{base_url}/companies/{company_slug}/contacts", params={"page": 2}).mock(
            return_value=Response(
                200,
                json=[{"contactId": i, "name": f"Contact {i}"} for i in range(50, 60)],
                headers={
                    "Fiken-Api-Page": "2",
                    "Fiken-Api-Page-Count": "3",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            contacts = []
            async for contact in client.get_contacts(company_slug):
                contacts.append(contact)

            assert len(contacts) == 60


class TestScopedClient:
    """Test scoped client functionality."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_scoped_client_get_contacts(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test scoped client automatically uses company_slug."""
        route = respx.get(f"{base_url}/companies/{company_slug}/contacts").mock(
            return_value=Response(
                200,
                json=[{"contactId": 1001, "name": "Test Customer"}],
                headers={
                    "Fiken-Api-Page": "0",
                    "Fiken-Api-Page-Count": "1",
                },
            )
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            scoped = client.for_company(company_slug)
            contacts = []
            async for contact in scoped.get_contacts():
                contacts.append(contact)

            assert len(contacts) == 1
            assert route.called


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_raises_not_found(
        self, api_token: str, base_url: str, company_slug: str
    ):
        """Test that 404 raises FikenNotFoundError."""
        respx.get(f"{base_url}/companies/{company_slug}/contacts/99999").mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            try:
                await client.get_contact(company_slug, 99999)
                assert False, "Should have raised FikenNotFoundError"
            except FikenNotFoundError as e:
                assert e.status_code == 404

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_auth_error(self, api_token: str, base_url: str):
        """Test that 401 raises FikenAuthError."""
        respx.get(f"{base_url}/user").mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            try:
                await client.get_user()
                assert False, "Should have raised FikenAuthError"
            except FikenAuthError as e:
                assert e.status_code == 401

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_raises_rate_limit_error(
        self, api_token: str, base_url: str
    ):
        """Test that 429 raises FikenRateLimitError."""
        respx.get(f"{base_url}/user").mock(
            return_value=Response(429, json={"error": "Rate limit exceeded"})
        )

        async with AsyncFikenClient(api_token=api_token) as client:
            try:
                await client.get_user()
                assert False, "Should have raised FikenRateLimitError"
            except FikenRateLimitError as e:
                assert e.status_code == 429
