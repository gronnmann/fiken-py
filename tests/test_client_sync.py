"""Tests for FikenClient (synchronous)."""

import respx
from httpx import Response

from fikenpy import FikenClient
from fikenpy.exceptions import (
    FikenAuthError,
    FikenNotFoundError,
    FikenRateLimitError,
    FikenValidationError,
)


class TestAuthentication:
    """Test authentication methods."""

    def test_token_auth_initialization(self, api_token: str):
        """Test client initialization with API token."""
        client = FikenClient(api_token=api_token)
        assert client.auth is not None
        client.close()

    def test_oauth_auth_initialization(self, oauth_tokens: dict[str, str]):
        """Test client initialization with OAuth2 tokens."""
        client = FikenClient(
            access_token=oauth_tokens["access_token"],
            refresh_token=oauth_tokens["refresh_token"],
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        assert client.auth is not None
        client.close()

    def test_missing_credentials_raises_error(self):
        """Test that missing credentials raises ValueError."""
        try:
            FikenClient()
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Either api_token or all OAuth2 credentials" in str(e)

    def test_context_manager(self, api_token: str):
        """Test client works as context manager."""
        with FikenClient(api_token=api_token) as client:
            assert client is not None


class TestUserEndpoints:
    """Test user-related endpoints."""

    @respx.mock
    def test_get_user(self, sync_client: FikenClient, base_url: str):
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

        user = sync_client.get_user()
        assert user.name == "Test User"
        assert user.email == "test@example.com"
        assert route.called


class TestCompanyEndpoints:
    """Test company-related endpoints."""

    @respx.mock
    def test_get_companies(self, sync_client: FikenClient, base_url: str):
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

        companies = list(sync_client.get_companies())
        assert len(companies) == 1
        assert companies[0].name == "Test Company AS"
        assert companies[0].slug == "test-company"
        assert route.called

    @respx.mock
    def test_get_company(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        company = sync_client.get_company(company_slug)
        assert company.name == "Test Company AS"
        assert company.slug == company_slug
        assert route.called


class TestContactEndpoints:
    """Test contact-related endpoints."""

    @respx.mock
    def test_get_contacts(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        contacts = list(sync_client.get_contacts(company_slug))
        assert len(contacts) == 1
        assert contacts[0].name == "Test Customer AS"
        assert route.called

    @respx.mock
    def test_get_contact(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        contact = sync_client.get_contact(company_slug, contact_id)
        assert contact.contact_id == contact_id
        assert contact.name == "Test Customer AS"
        assert route.called

    @respx.mock
    def test_create_contact(
        self, sync_client: FikenClient, base_url: str, company_slug: str
    ):
        """Test creating a new contact."""
        contact_data = {
            "name": "New Customer AS",
            "email": "new@example.com",
            "customer": True,
        }

        post_route = respx.post(f"{base_url}/companies/{company_slug}/contacts").mock(
            return_value=Response(
                201,
                headers={"Location": f"/companies/{company_slug}/contacts/2001"},
            )
        )

        get_route = respx.get(
            f"{base_url}/companies/{company_slug}/contacts/2001"
        ).mock(
            return_value=Response(
                200,
                json={
                    "contactId": 2001,
                    "name": "New Customer AS",
                    "email": "new@example.com",
                    "customer": True,
                },
            )
        )

        contact = sync_client.create_contact(company_slug, contact_data)
        assert contact.contact_id == 2001
        assert contact.name == "New Customer AS"
        assert post_route.called
        assert get_route.called


class TestProductEndpoints:
    """Test product-related endpoints."""

    @respx.mock
    def test_get_products(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        products = list(sync_client.get_products(company_slug))
        assert len(products) == 1
        assert products[0].name == "Test Product"
        assert products[0].unit_price == 10000
        assert route.called


class TestInvoiceEndpoints:
    """Test invoice-related endpoints."""

    @respx.mock
    def test_get_invoices(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        invoices = list(sync_client.get_invoices(company_slug))
        assert len(invoices) == 1
        assert invoices[0].invoice_number == 10001
        assert route.called


class TestPagination:
    """Test pagination functionality."""

    @respx.mock
    def test_automatic_pagination(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        contacts = list(sync_client.get_contacts(company_slug))
        assert len(contacts) == 60


class TestScopedClient:
    """Test scoped client functionality."""

    @respx.mock
    def test_scoped_client_get_contacts(
        self, sync_client: FikenClient, base_url: str, company_slug: str
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

        scoped = sync_client.for_company(company_slug)
        contacts = list(scoped.get_contacts())
        assert len(contacts) == 1
        assert route.called


class TestErrorHandling:
    """Test error handling."""

    @respx.mock
    def test_404_raises_not_found(
        self, sync_client: FikenClient, base_url: str, company_slug: str
    ):
        """Test that 404 raises FikenNotFoundError."""
        respx.get(f"{base_url}/companies/{company_slug}/contacts/99999").mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        try:
            sync_client.get_contact(company_slug, 99999)
            assert False, "Should have raised FikenNotFoundError"
        except FikenNotFoundError as e:
            assert e.status_code == 404

    @respx.mock
    def test_401_raises_auth_error(
        self, sync_client: FikenClient, base_url: str
    ):
        """Test that 401 raises FikenAuthError."""
        respx.get(f"{base_url}/user").mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        try:
            sync_client.get_user()
            assert False, "Should have raised FikenAuthError"
        except FikenAuthError as e:
            assert e.status_code == 401

    @respx.mock
    def test_400_raises_validation_error(
        self, sync_client: FikenClient, base_url: str, company_slug: str
    ):
        """Test that 400 raises FikenValidationError."""
        respx.post(f"{base_url}/companies/{company_slug}/contacts").mock(
            return_value=Response(400, json={"error": "Invalid data"})
        )

        try:
            sync_client.create_contact(company_slug, {"invalid": "data"})
            assert False, "Should have raised FikenValidationError"
        except FikenValidationError as e:
            assert e.status_code == 400

    @respx.mock
    def test_429_raises_rate_limit_error(
        self, sync_client: FikenClient, base_url: str
    ):
        """Test that 429 raises FikenRateLimitError."""
        respx.get(f"{base_url}/user").mock(
            return_value=Response(429, json={"error": "Rate limit exceeded"})
        )

        try:
            sync_client.get_user()
            assert False, "Should have raised FikenRateLimitError"
        except FikenRateLimitError as e:
            assert e.status_code == 429
