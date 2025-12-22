"""Synchronous Fiken API client."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from fikenpy._version import __version__
from fikenpy.auth import OAuth2Handler, RateLimiter, TokenAuth
from fikenpy.client_base import (
    ClientConfig,
    PaginatedIterator,
    parse_error_response,
    prepare_attachment,
)
from fikenpy.models import *  # noqa: F403


class FikenClient:
    """Synchronous client for the Fiken API.

    Supports both API token and OAuth2 authentication with automatic token refresh.
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str = ClientConfig.BASE_URL,
        timeout: float = ClientConfig.DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize Fiken client.

        Args:
            api_token: Personal API token (for individual use)
            access_token: OAuth2 access token (for third-party apps)
            refresh_token: OAuth2 refresh token
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            base_url: Base URL for API (default: https://api.fiken.no/api/v2)
            timeout: Request timeout in seconds

        Raises:
            ValueError: If neither api_token nor OAuth2 credentials are provided
        """
        self.base_url = base_url
        self.timeout = timeout
        self.rate_limiter = RateLimiter()

        # Auto-detect authentication type
        self.auth: TokenAuth | OAuth2Handler
        if api_token:
            self.auth = TokenAuth(api_token)
        elif access_token and refresh_token and client_id and client_secret:
            self.auth = OAuth2Handler(
                access_token=access_token,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            raise ValueError(
                "Either api_token or all OAuth2 credentials "
                "(access_token, refresh_token, client_id, client_secret) must be provided"
            )

        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": f"FikenPy/{__version__}",
            },
        )

    def __enter__(self) -> FikenClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def for_company(self, company_slug: str) -> ScopedFikenClient:
        """Create a scoped client for a specific company.

        Args:
            company_slug: Company identifier

        Returns:
            Scoped client with company_slug pre-filled
        """
        return ScopedFikenClient(self, company_slug)

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with rate limiting and auth.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            **kwargs: Additional arguments for httpx request

        Returns:
            HTTP response

        Raises:
            FikenAPIError: On API errors
        """
        self.rate_limiter.acquire()

        headers = self.auth.get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        # Remove Content-Type header when files are present to let httpx set multipart/form-data
        if "files" in kwargs and "Content-Type" in headers:
            headers.pop("Content-Type")

        response = self.client.request(
            method=method,
            url=endpoint,
            headers=headers,
            **kwargs,
        )

        if response.status_code >= 400:
            raise parse_error_response(response)

        return response

    # User endpoints

    def get_user(self) -> Userinfo:  # noqa: F405
        """Get information about the current user.

        Returns:
            User information
        """
        response = self._request("GET", "/user")
        return Userinfo.model_validate(response.json())  # noqa: F405

    # Company endpoints

    def get_companies(
        self,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[Company]:  # noqa: F405
        """Get all companies for the current user.

        Args:
            page: Page number (default: 0)
            page_size: Number of items per page (default: 25, max: 100)

        Returns:
            Iterator of companies
        """
        params: dict[str, Any] = {
            "page": page,
            "pageSize": page_size,
        }
        return PaginatedIterator(
            client=self.client,
            url="/companies",
            params=params,
            model_class=Company,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def get_company(self, company_slug: str) -> Company:  # noqa: F405
        """Get a specific company.

        Args:
            company_slug: Company identifier

        Returns:
            Company details
        """
        response = self._request("GET", f"/companies/{company_slug}")
        return Company.model_validate(response.json())  # noqa: F405

    # Account endpoints

    def get_accounts(
        self,
        company_slug: str,
        from_account: str | None = None,
        to_account: str | None = None,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[Account]:  # noqa: F405
        """Get accounts for a company.

        Args:
            company_slug: Company identifier
            from_account: Filter by account code range start
            to_account: Filter by account code range end
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of accounts
        """
        params: dict[str, Any] = {
            "page": page,
            "pageSize": page_size,
        }
        if from_account:
            params["fromAccount"] = from_account
        if to_account:
            params["toAccount"] = to_account

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/accounts",
            params=params,
            model_class=Account,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def get_account(
        self, company_slug: str, account_code: str
    ) -> Account:  # noqa: F405
        """Get a specific account.

        Args:
            company_slug: Company identifier
            account_code: Account code

        Returns:
            Account details
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/accounts/{account_code}"
        )
        return Account.model_validate(response.json())  # noqa: F405

    def get_account_balances(
        self,
        company_slug: str,
        from_account: str | None = None,
        to_account: str | None = None,
        date: date | None = None,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[AccountBalance]:  # noqa: F405
        """Get account balances for a company.

        Args:
            company_slug: Company identifier
            from_account: Filter by account code range start
            to_account: Filter by account code range end
            date: Filter by specific date (yyyy-mm-dd)
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of account balances
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if from_account:
            params["fromAccount"] = from_account
        if to_account:
            params["toAccount"] = to_account
        if date:
            params["date"] = date.isoformat()

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/accountBalances",
            params=params,
            model_class=AccountBalance,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def get_account_balance(
        self,
        company_slug: str,
        account_code: str,
        date: date | None = None,
    ) -> AccountBalance:  # noqa: F405
        """Get balance for a specific account.

        Args:
            company_slug: Company identifier
            account_code: Account code
            date: Filter by specific date

        Returns:
            Account balance
        """
        params: dict[str, Any] = {}
        if date:
            params["date"] = date.isoformat()

        response = self._request(
            "GET",
            f"/companies/{company_slug}/accountBalances/{account_code}",
            params=params,
        )
        return AccountBalance.model_validate(response.json())  # noqa: F405

    # Bank Account endpoints

    def get_bank_accounts(
        self,
        company_slug: str,
        inactive: bool | None = None,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[BankAccountResult]:  # noqa: F405
        """Get bank accounts for a company.

        Args:
            company_slug: Company identifier
            inactive: Filter by inactive status
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of bank accounts
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if inactive is not None:
            params["inactive"] = inactive

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/bankAccounts",
            params=params,
            model_class=BankAccountResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_bank_account(
        self,
        company_slug: str,
        data: BankAccountRequest,  # noqa: F405
    ) -> BankAccountResult:  # noqa: F405
        """Create a new bank account.

        Args:
            company_slug: Company identifier
            data: Bank account data

        Returns:
            Created bank account
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/bankAccounts",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            # Fetch the created resource
            bank_account_id = location.split("/")[-1]
            return self.get_bank_account(company_slug, int(bank_account_id))
        return BankAccountResult.model_validate(response.json())  # noqa: F405

    def get_bank_account(
        self, company_slug: str, bank_account_id: int
    ) -> BankAccountResult:  # noqa: F405
        """Get a specific bank account.

        Args:
            company_slug: Company identifier
            bank_account_id: Bank account ID

        Returns:
            Bank account details
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/bankAccounts/{bank_account_id}"
        )
        return BankAccountResult.model_validate(response.json())  # noqa: F405

    # Bank Balance endpoints

    def get_bank_balances(
        self,
        company_slug: str,
        date: date | None = None,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[BankBalanceResult]:  # noqa: F405
        """Get bank balances for a company.

        Args:
            company_slug: Company identifier
            date: Filter by specific date
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of bank balances
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if date:
            params["date"] = date.isoformat()

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/bankBalances",
            params=params,
            model_class=BankBalanceResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    # Contact endpoints

    def get_contacts(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[Contact]:  # noqa: F405
        """Get contacts for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters (name, email, customer, supplier, etc.)

        Returns:
            Iterator of contacts
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/contacts",
            params=params,
            model_class=Contact,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_contact(
        self,
        company_slug: str,
        data: Contact,  # noqa: F405
    ) -> Contact:  # noqa: F405
        """Create a new contact.

        Args:
            company_slug: Company identifier
            data: Contact data

        Returns:
            Created contact
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/contacts",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            contact_id = location.split("/")[-1]
            return self.get_contact(company_slug, int(contact_id))
        return Contact.model_validate(response.json())  # noqa: F405

    def get_contact(self, company_slug: str, contact_id: int) -> Contact:  # noqa: F405
        """Get a specific contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID

        Returns:
            Contact details
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/contacts/{contact_id}"
        )
        return Contact.model_validate(response.json())  # noqa: F405

    def update_contact(
        self,
        company_slug: str,
        contact_id: int,
        data: Contact,  # noqa: F405
    ) -> Contact:  # noqa: F405
        """Update a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            data: Updated contact data

        Returns:
            Updated contact
        """
        self._request(
            "PUT",
            f"/companies/{company_slug}/contacts/{contact_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_contact(company_slug, contact_id)

    def delete_contact(self, company_slug: str, contact_id: int) -> None:
        """Delete a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
        """
        self._request("DELETE", f"/companies/{company_slug}/contacts/{contact_id}")

    def add_attachment_to_contact(
        self,
        company_slug: str,
        contact_id: int,
        file: Path | str | BinaryIO,
        filename: str | None = None,
    ) -> None:
        """Add an attachment to a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            file: File to attach
            filename: Optional filename override
        """
        fname, file_bytes, content_type = prepare_attachment(file, filename)
        files = {
            "file": (fname, file_bytes, content_type),
            "filename": (None, fname),
        }

        self._request(
            "POST",
            f"/companies/{company_slug}/contacts/{contact_id}/attachments",
            files=files,
        )

    def get_contact_persons(
        self, company_slug: str, contact_id: int
    ) -> list[ContactPerson]:  # noqa: F405
        """Get contact persons for a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID

        Returns:
            List of contact persons
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/contacts/{contact_id}/contactPerson"
        )
        return [
            ContactPerson.model_validate(item) for item in response.json()  # noqa: F405
        ]

    def add_contact_person(
        self,
        company_slug: str,
        contact_id: int,
        data: ContactPerson,  # noqa: F405
    ) -> ContactPerson:  # noqa: F405
        """Add a contact person to a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            data: Contact person data

        Returns:
            Created contact person
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/contacts/{contact_id}/contactPerson",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            person_id = location.split("/")[-1]
            return self.get_contact_person(company_slug, contact_id, int(person_id))
        return ContactPerson.model_validate(response.json())  # noqa: F405

    def get_contact_person(
        self, company_slug: str, contact_id: int, person_id: int
    ) -> ContactPerson:  # noqa: F405
        """Get a specific contact person.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            person_id: Contact person ID

        Returns:
            Contact person details
        """
        response = self._request(
            "GET",
            f"/companies/{company_slug}/contacts/{contact_id}/contactPerson/{person_id}",
        )
        return ContactPerson.model_validate(response.json())  # noqa: F405

    def update_contact_person(
        self,
        company_slug: str,
        contact_id: int,
        person_id: int,
        data: ContactPerson,  # noqa: F405
    ) -> ContactPerson:  # noqa: F405
        """Update a contact person.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            person_id: Contact person ID
            data: Updated contact person data

        Returns:
            Updated contact person
        """
        self._request(
            "PUT",
            f"/companies/{company_slug}/contacts/{contact_id}/contactPerson/{person_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_contact_person(company_slug, contact_id, person_id)

    def delete_contact_person(
        self, company_slug: str, contact_id: int, person_id: int
    ) -> None:
        """Delete a contact person.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            person_id: Contact person ID
        """
        self._request(
            "DELETE",
            f"/companies/{company_slug}/contacts/{contact_id}/contactPerson/{person_id}",
        )

    # Product endpoints

    def get_products(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[Product]:  # noqa: F405
        """Get products for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters (name, productNumber, active, etc.)

        Returns:
            Iterator of products
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/products",
            params=params,
            model_class=Product,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_product(
        self,
        company_slug: str,
        data: Product,  # noqa: F405
    ) -> Product:  # noqa: F405
        """Create a new product.

        Args:
            company_slug: Company identifier
            data: Product data

        Returns:
            Created product
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/products",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            product_id = location.split("/")[-1]
            return self.get_product(company_slug, int(product_id))
        return Product.model_validate(response.json())  # noqa: F405

    def get_product(self, company_slug: str, product_id: int) -> Product:  # noqa: F405
        """Get a specific product.

        Args:
            company_slug: Company identifier
            product_id: Product ID

        Returns:
            Product details
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/products/{product_id}"
        )
        return Product.model_validate(response.json())  # noqa: F405

    def update_product(
        self,
        company_slug: str,
        product_id: int,
        data: Product,  # noqa: F405
    ) -> Product:  # noqa: F405
        """Update a product.

        Args:
            company_slug: Company identifier
            product_id: Product ID
            data: Updated product data

        Returns:
            Updated product
        """
        self._request(
            "PUT",
            f"/companies/{company_slug}/products/{product_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_product(company_slug, product_id)

    def delete_product(self, company_slug: str, product_id: int) -> None:
        """Delete a product.

        Args:
            company_slug: Company identifier
            product_id: Product ID
        """
        self._request("DELETE", f"/companies/{company_slug}/products/{product_id}")

    def create_product_sales_report(
        self,
        company_slug: str,
        data: ProductSalesReportRequest,  # noqa: F405
    ) -> ProductSalesReportResult:  # noqa: F405
        """Create a product sales report.

        Args:
            company_slug: Company identifier
            data: Report request data

        Returns:
            Sales report result
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/products/salesReport",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return ProductSalesReportResult.model_validate(response.json())  # noqa: F405

    # Invoice endpoints

    def get_invoices(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[InvoiceResult]:  # noqa: F405
        """Get invoices for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters (issueDate, customerId, settled, etc.)

        Returns:
            Iterator of invoices
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/invoices",
            params=params,
            model_class=InvoiceResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_invoice(
        self,
        company_slug: str,
        data: InvoiceRequest,  # noqa: F405
    ) -> InvoiceResult:  # noqa: F405
        """Create a new invoice.

        Args:
            company_slug: Company identifier
            data: Invoice data

        Returns:
            Created invoice
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/invoices",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            invoice_id = location.split("/")[-1]
            return self.get_invoice(company_slug, int(invoice_id))
        return InvoiceResult.model_validate(response.json())  # noqa: F405

    def get_invoice(
        self, company_slug: str, invoice_id: int
    ) -> InvoiceResult:  # noqa: F405
        """Get a specific invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID

        Returns:
            Invoice details
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/invoices/{invoice_id}"
        )
        return InvoiceResult.model_validate(response.json())  # noqa: F405

    def update_invoice(
        self,
        company_slug: str,
        invoice_id: int,
        data: UpdateInvoiceRequest,  # noqa: F405
    ) -> InvoiceResult:  # noqa: F405
        """Update an invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID
            data: Update data

        Returns:
            Updated invoice
        """
        self._request(
            "PATCH",
            f"/companies/{company_slug}/invoices/{invoice_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_invoice(company_slug, invoice_id)

    def get_invoice_attachments(
        self, company_slug: str, invoice_id: int
    ) -> list[Attachment]:  # noqa: F405
        """Get attachments for an invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID

        Returns:
            List of attachments
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/invoices/{invoice_id}/attachments"
        )
        return [
            Attachment.model_validate(item) for item in response.json()
        ]  # noqa: F405

    def add_attachment_to_invoice(
        self,
        company_slug: str,
        invoice_id: int,
        file: Path | str | BinaryIO,
        filename: str | None = None,
    ) -> None:
        """Add an attachment to an invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID
            file: File to attach
            filename: Optional filename override
        """
        fname, file_bytes, content_type = prepare_attachment(file, filename)
        files = {
            "file": (fname, file_bytes, content_type),
            "filename": (None, fname),
        }

        self._request(
            "POST",
            f"/companies/{company_slug}/invoices/{invoice_id}/attachments",
            files=files,
        )

    def send_invoice(
        self,
        company_slug: str,
        data: SendInvoiceRequest,  # noqa: F405
    ) -> None:
        """Send an invoice.

        Args:
            company_slug: Company identifier
            data: Send invoice request data
        """
        self._request(
            "POST",
            f"/companies/{company_slug}/invoices/send",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )

    # Invoice draft endpoints

    def get_invoice_drafts(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[InvoiceishDraftResult]:  # noqa: F405
        """Get invoice drafts for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters

        Returns:
            Iterator of invoice drafts
        """
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)

        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/invoices/drafts",
            params=params,
            model_class=InvoiceishDraftResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_invoice_draft(
        self,
        company_slug: str,
        data: InvoiceishDraftRequest,  # noqa: F405
    ) -> InvoiceishDraftResult:  # noqa: F405
        """Create a new invoice draft.

        Args:
            company_slug: Company identifier
            data: Invoice draft data

        Returns:
            Created invoice draft
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/invoices/drafts",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            draft_id = location.split("/")[-1]
            return self.get_invoice_draft(company_slug, int(draft_id))
        return InvoiceishDraftResult.model_validate(response.json())  # noqa: F405

    def get_invoice_draft(
        self, company_slug: str, draft_id: int
    ) -> InvoiceishDraftResult:  # noqa: F405
        """Get a specific invoice draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID

        Returns:
            Invoice draft details
        """
        response = self._request(
            "GET", f"/companies/{company_slug}/invoices/drafts/{draft_id}"
        )
        return InvoiceishDraftResult.model_validate(response.json())  # noqa: F405

    def update_invoice_draft(
        self,
        company_slug: str,
        draft_id: int,
        data: InvoiceishDraftRequest,  # noqa: F405
    ) -> InvoiceishDraftResult:  # noqa: F405
        """Update an invoice draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID
            data: Updated draft data

        Returns:
            Updated invoice draft
        """
        self._request(
            "PUT",
            f"/companies/{company_slug}/invoices/drafts/{draft_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_invoice_draft(company_slug, draft_id)

    def delete_invoice_draft(self, company_slug: str, draft_id: int) -> None:
        """Delete an invoice draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID
        """
        self._request("DELETE", f"/companies/{company_slug}/invoices/drafts/{draft_id}")

    def create_invoice_from_draft(
        self, company_slug: str, draft_id: int
    ) -> InvoiceResult:  # noqa: F405
        """Create an invoice from a draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID

        Returns:
            Created invoice
        """
        response = self._request(
            "POST",
            f"/companies/{company_slug}/invoices/drafts/{draft_id}/createInvoice",
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            invoice_id = location.split("/")[-1]
            return self.get_invoice(company_slug, int(invoice_id))
        return InvoiceResult.model_validate(response.json())  # noqa: F405

    # Sales endpoints

    def get_sales(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[SaleResult]:  # noqa: F405
        """Get sales for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/sales",
            params=params,
            model_class=SaleResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_sale(
        self,
        company_slug: str,
        data: SaleRequest,  # noqa: F405
    ) -> SaleResult:  # noqa: F405
        """Create a new sale."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/sales",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            sale_id = location.split("/")[-1]
            return self.get_sale(company_slug, int(sale_id))
        return SaleResult.model_validate(response.json())  # noqa: F405

    def get_sale(self, company_slug: str, sale_id: int) -> SaleResult:  # noqa: F405
        """Get a specific sale."""
        response = self._request("GET", f"/companies/{company_slug}/sales/{sale_id}")
        return SaleResult.model_validate(response.json())  # noqa: F405

    def delete_sale(self, company_slug: str, sale_id: int) -> None:
        """Delete a sale."""
        self._request("PATCH", f"/companies/{company_slug}/sales/{sale_id}/delete")

    def get_sale_attachments(
        self, company_slug: str, sale_id: int
    ) -> list[Attachment]:  # noqa: F405
        """Get attachments for a sale."""
        response = self._request(
            "GET", f"/companies/{company_slug}/sales/{sale_id}/attachments"
        )
        return [
            Attachment.model_validate(item) for item in response.json()
        ]  # noqa: F405

    def add_attachment_to_sale(
        self,
        company_slug: str,
        sale_id: int,
        file: Path | str | BinaryIO,
        filename: str | None = None,
    ) -> None:
        """Add an attachment to a sale."""
        fname, file_bytes, content_type = prepare_attachment(file, filename)
        files = {
            "file": (fname, file_bytes, content_type),
            "filename": (None, fname),
        }
        self._request(
            "POST",
            f"/companies/{company_slug}/sales/{sale_id}/attachments",
            files=files,
        )

    def get_sale_payments(
        self, company_slug: str, sale_id: int
    ) -> list[Payment]:  # noqa: F405
        """Get payments for a sale."""
        response = self._request(
            "GET", f"/companies/{company_slug}/sales/{sale_id}/payments"
        )
        return [Payment.model_validate(item) for item in response.json()]  # noqa: F405

    def create_sale_payment(
        self,
        company_slug: str,
        sale_id: int,
        data: Payment,  # noqa: F405
    ) -> Payment:  # noqa: F405
        """Create a payment for a sale."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/sales/{sale_id}/payments",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            payment_id = location.split("/")[-1]
            return self.get_sale_payment(company_slug, sale_id, int(payment_id))
        return Payment.model_validate(response.json())  # noqa: F405

    def get_sale_payment(
        self, company_slug: str, sale_id: int, payment_id: int
    ) -> Payment:  # noqa: F405
        """Get a specific sale payment."""
        response = self._request(
            "GET", f"/companies/{company_slug}/sales/{sale_id}/payments/{payment_id}"
        )
        return Payment.model_validate(response.json())  # noqa: F405

    def get_sale_drafts(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[DraftResult]:  # noqa: F405
        """Get sale drafts for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/sales/drafts",
            params=params,
            model_class=DraftResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_sale_draft(
        self,
        company_slug: str,
        data: DraftRequest,  # noqa: F405
    ) -> DraftResult:  # noqa: F405
        """Create a new sale draft."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/sales/drafts",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            draft_id = location.split("/")[-1]
            return self.get_sale_draft(company_slug, int(draft_id))
        return DraftResult.model_validate(response.json())  # noqa: F405

    def get_sale_draft(
        self, company_slug: str, draft_id: int
    ) -> DraftResult:  # noqa: F405
        """Get a specific sale draft."""
        response = self._request(
            "GET", f"/companies/{company_slug}/sales/drafts/{draft_id}"
        )
        return DraftResult.model_validate(response.json())  # noqa: F405

    def update_sale_draft(
        self,
        company_slug: str,
        draft_id: int,
        data: DraftRequest,  # noqa: F405
    ) -> DraftResult:  # noqa: F405
        """Update a sale draft."""
        self._request(
            "PUT",
            f"/companies/{company_slug}/sales/drafts/{draft_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_sale_draft(company_slug, draft_id)

    def delete_sale_draft(self, company_slug: str, draft_id: int) -> None:
        """Delete a sale draft."""
        self._request("DELETE", f"/companies/{company_slug}/sales/drafts/{draft_id}")

    def create_sale_from_draft(
        self, company_slug: str, draft_id: int
    ) -> SaleResult:  # noqa: F405
        """Create a sale from a draft."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/sales/drafts/{draft_id}/createSale",
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            sale_id = location.split("/")[-1]
            return self.get_sale(company_slug, int(sale_id))
        return SaleResult.model_validate(response.json())  # noqa: F405

    # Purchase endpoints

    def get_purchases(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[PurchaseResult]:  # noqa: F405
        """Get purchases for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/purchases",
            params=params,
            model_class=PurchaseResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_purchase(
        self,
        company_slug: str,
        data: PurchaseRequest,  # noqa: F405
    ) -> PurchaseResult:  # noqa: F405
        """Create a new purchase."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/purchases",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            purchase_id = location.split("/")[-1]
            return self.get_purchase(company_slug, int(purchase_id))
        return PurchaseResult.model_validate(response.json())  # noqa: F405

    def get_purchase(
        self, company_slug: str, purchase_id: int
    ) -> PurchaseResult:  # noqa: F405
        """Get a specific purchase."""
        response = self._request(
            "GET", f"/companies/{company_slug}/purchases/{purchase_id}"
        )
        return PurchaseResult.model_validate(response.json())  # noqa: F405

    def delete_purchase(self, company_slug: str, purchase_id: int) -> None:
        """Delete a purchase."""
        self._request(
            "PATCH", f"/companies/{company_slug}/purchases/{purchase_id}/delete"
        )

    def get_purchase_attachments(
        self, company_slug: str, purchase_id: int
    ) -> list[Attachment]:  # noqa: F405
        """Get attachments for a purchase."""
        response = self._request(
            "GET", f"/companies/{company_slug}/purchases/{purchase_id}/attachments"
        )
        return [
            Attachment.model_validate(item) for item in response.json()
        ]  # noqa: F405

    def add_attachment_to_purchase(
        self,
        company_slug: str,
        purchase_id: int,
        file: Path | str | BinaryIO,
        filename: str | None = None,
        attach_to_payment: bool = False,
        attach_to_sale: bool = True,
    ) -> None:
        """Add an attachment to a purchase.

        Args:
            company_slug: Company identifier
            purchase_id: Purchase ID
            file: File to attach
            filename: Optional filename override
            attach_to_payment: True if this attachment documents the payment
            attach_to_sale: True if this attachment documents the sale (default: True)
        """
        fname, file_bytes, content_type = prepare_attachment(file, filename)
        files = {
            "file": (fname, file_bytes, content_type),
            "filename": (None, fname),
            "attachToPayment": (None, str(attach_to_payment).lower()),
            "attachToSale": (None, str(attach_to_sale).lower()),
        }
        self._request(
            "POST",
            f"/companies/{company_slug}/purchases/{purchase_id}/attachments",
            files=files,
        )

    def get_purchase_payments(
        self, company_slug: str, purchase_id: int
    ) -> list[Payment]:  # noqa: F405
        """Get payments for a purchase."""
        response = self._request(
            "GET", f"/companies/{company_slug}/purchases/{purchase_id}/payments"
        )
        return [Payment.model_validate(item) for item in response.json()]  # noqa: F405

    def create_purchase_payment(
        self,
        company_slug: str,
        purchase_id: int,
        data: Payment,  # noqa: F405
    ) -> Payment:  # noqa: F405
        """Create a payment for a purchase."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/purchases/{purchase_id}/payments",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            payment_id = location.split("/")[-1]
            return self.get_purchase_payment(company_slug, purchase_id, int(payment_id))
        return Payment.model_validate(response.json())  # noqa: F405

    def get_purchase_payment(
        self, company_slug: str, purchase_id: int, payment_id: int
    ) -> Payment:  # noqa: F405
        """Get a specific purchase payment."""
        response = self._request(
            "GET",
            f"/companies/{company_slug}/purchases/{purchase_id}/payments/{payment_id}",
        )
        return Payment.model_validate(response.json())  # noqa: F405

    def get_purchase_drafts(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[DraftResult]:  # noqa: F405
        """Get purchase drafts for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/purchases/drafts",
            params=params,
            model_class=DraftResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_purchase_draft(
        self,
        company_slug: str,
        data: DraftRequest,  # noqa: F405
    ) -> DraftResult:  # noqa: F405
        """Create a new purchase draft."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/purchases/drafts",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            draft_id = location.split("/")[-1]
            return self.get_purchase_draft(company_slug, int(draft_id))
        return DraftResult.model_validate(response.json())  # noqa: F405

    def get_purchase_draft(
        self, company_slug: str, draft_id: int
    ) -> DraftResult:  # noqa: F405
        """Get a specific purchase draft."""
        response = self._request(
            "GET", f"/companies/{company_slug}/purchases/drafts/{draft_id}"
        )
        return DraftResult.model_validate(response.json())  # noqa: F405

    def update_purchase_draft(
        self,
        company_slug: str,
        draft_id: int,
        data: DraftRequest,  # noqa: F405
    ) -> DraftResult:  # noqa: F405
        """Update a purchase draft."""
        self._request(
            "PUT",
            f"/companies/{company_slug}/purchases/drafts/{draft_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_purchase_draft(company_slug, draft_id)

    def delete_purchase_draft(self, company_slug: str, draft_id: int) -> None:
        """Delete a purchase draft."""
        self._request(
            "DELETE", f"/companies/{company_slug}/purchases/drafts/{draft_id}"
        )

    def create_purchase_from_draft(
        self, company_slug: str, draft_id: int
    ) -> PurchaseResult:  # noqa: F405
        """Create a purchase from a draft."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/purchases/drafts/{draft_id}/createPurchase",
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            purchase_id = location.split("/")[-1]
            return self.get_purchase(company_slug, int(purchase_id))
        return PurchaseResult.model_validate(response.json())  # noqa: F405

    # Credit Note endpoints

    def get_credit_notes(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[CreditNoteResult]:  # noqa: F405
        """Get credit notes for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/creditNotes",
            params=params,
            model_class=CreditNoteResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_full_credit_note(
        self,
        company_slug: str,
        data: FullCreditNoteRequest,  # noqa: F405
    ) -> CreditNoteResult:  # noqa: F405
        """Create a full credit note."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/creditNotes/full",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            credit_note_id = location.split("/")[-1]
            return self.get_credit_note(company_slug, int(credit_note_id))
        return CreditNoteResult.model_validate(response.json())  # noqa: F405

    def create_partial_credit_note(
        self,
        company_slug: str,
        data: PartialCreditNoteRequest,  # noqa: F405
    ) -> CreditNoteResult:  # noqa: F405
        """Create a partial credit note."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/creditNotes/partial",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            credit_note_id = location.split("/")[-1]
            return self.get_credit_note(company_slug, int(credit_note_id))
        return CreditNoteResult.model_validate(response.json())  # noqa: F405

    def get_credit_note(
        self, company_slug: str, credit_note_id: int
    ) -> CreditNoteResult:  # noqa: F405
        """Get a specific credit note."""
        response = self._request(
            "GET", f"/companies/{company_slug}/creditNotes/{credit_note_id}"
        )
        return CreditNoteResult.model_validate(response.json())  # noqa: F405

    def send_credit_note(
        self,
        company_slug: str,
        data: SendCreditNoteRequest,  # noqa: F405
    ) -> None:
        """Send a credit note."""
        self._request(
            "POST",
            f"/companies/{company_slug}/creditNotes/send",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )

    def get_credit_note_drafts(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[InvoiceishDraftResult]:  # noqa: F405
        """Get credit note drafts for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/creditNotes/drafts",
            params=params,
            model_class=InvoiceishDraftResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_credit_note_draft(
        self,
        company_slug: str,
        data: InvoiceishDraftRequest,  # noqa: F405
    ) -> InvoiceishDraftResult:  # noqa: F405
        """Create a new credit note draft."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/creditNotes/drafts",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            draft_id = location.split("/")[-1]
            return self.get_credit_note_draft(company_slug, int(draft_id))
        return InvoiceishDraftResult.model_validate(response.json())  # noqa: F405

    def get_credit_note_draft(
        self, company_slug: str, draft_id: int
    ) -> InvoiceishDraftResult:  # noqa: F405
        """Get a specific credit note draft."""
        response = self._request(
            "GET", f"/companies/{company_slug}/creditNotes/drafts/{draft_id}"
        )
        return InvoiceishDraftResult.model_validate(response.json())  # noqa: F405

    def update_credit_note_draft(
        self,
        company_slug: str,
        draft_id: int,
        data: InvoiceishDraftRequest,  # noqa: F405
    ) -> InvoiceishDraftResult:  # noqa: F405
        """Update a credit note draft."""
        self._request(
            "PUT",
            f"/companies/{company_slug}/creditNotes/drafts/{draft_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_credit_note_draft(company_slug, draft_id)

    def delete_credit_note_draft(self, company_slug: str, draft_id: int) -> None:
        """Delete a credit note draft."""
        self._request(
            "DELETE", f"/companies/{company_slug}/creditNotes/drafts/{draft_id}"
        )

    def create_credit_note_from_draft(
        self, company_slug: str, draft_id: int
    ) -> CreditNoteResult:  # noqa: F405
        """Create a credit note from a draft."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/creditNotes/drafts/{draft_id}/createCreditNote",
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            credit_note_id = location.split("/")[-1]
            return self.get_credit_note(company_slug, int(credit_note_id))
        return CreditNoteResult.model_validate(response.json())  # noqa: F405

    # Journal Entry endpoints

    def get_journal_entries(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[JournalEntry]:  # noqa: F405
        """Get journal entries for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/journalEntries",
            params=params,
            model_class=JournalEntry,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_general_journal_entry(
        self,
        company_slug: str,
        data: GeneralJournalEntryRequest,  # noqa: F405
    ) -> JournalEntry:  # noqa: F405
        """Create a general journal entry."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/generalJournalEntries",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            entry_id = location.split("/")[-1]
            return self.get_journal_entry(company_slug, int(entry_id))
        return JournalEntry.model_validate(response.json())  # noqa: F405

    def get_journal_entry(
        self, company_slug: str, entry_id: int
    ) -> JournalEntry:  # noqa: F405
        """Get a specific journal entry."""
        response = self._request(
            "GET", f"/companies/{company_slug}/journalEntries/{entry_id}"
        )
        return JournalEntry.model_validate(response.json())  # noqa: F405

    def get_journal_entry_attachments(
        self, company_slug: str, entry_id: int
    ) -> list[Attachment]:  # noqa: F405
        """Get attachments for a journal entry."""
        response = self._request(
            "GET", f"/companies/{company_slug}/journalEntries/{entry_id}/attachments"
        )
        return [
            Attachment.model_validate(item) for item in response.json()
        ]  # noqa: F405

    def add_attachment_to_journal_entry(
        self,
        company_slug: str,
        entry_id: int,
        file: Path | str | BinaryIO,
        filename: str | None = None,
    ) -> None:
        """Add an attachment to a journal entry."""
        fname, file_bytes, content_type = prepare_attachment(file, filename)
        files = {
            "file": (fname, file_bytes, content_type),
            "filename": (None, fname),
        }
        self._request(
            "POST",
            f"/companies/{company_slug}/journalEntries/{entry_id}/attachments",
            files=files,
        )

    # Transaction endpoints

    def get_transactions(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[Transaction]:  # noqa: F405
        """Get transactions for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/transactions",
            params=params,
            model_class=Transaction,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def get_transaction(
        self, company_slug: str, transaction_id: int
    ) -> Transaction:  # noqa: F405
        """Get a specific transaction."""
        response = self._request(
            "GET", f"/companies/{company_slug}/transactions/{transaction_id}"
        )
        return Transaction.model_validate(response.json())  # noqa: F405

    def delete_transaction(self, company_slug: str, transaction_id: int) -> None:
        """Delete a transaction."""
        self._request(
            "PATCH", f"/companies/{company_slug}/transactions/{transaction_id}/delete"
        )

    # Project endpoints

    def get_projects(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[ProjectResult]:  # noqa: F405
        """Get projects for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/projects",
            params=params,
            model_class=ProjectResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_project(
        self,
        company_slug: str,
        data: ProjectRequest,  # noqa: F405
    ) -> ProjectResult:  # noqa: F405
        """Create a new project."""
        response = self._request(
            "POST",
            f"/companies/{company_slug}/projects",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            project_id = location.split("/")[-1]
            return self.get_project(company_slug, int(project_id))
        return ProjectResult.model_validate(response.json())  # noqa: F405

    def get_project(
        self, company_slug: str, project_id: int
    ) -> ProjectResult:  # noqa: F405
        """Get a specific project."""
        response = self._request(
            "GET", f"/companies/{company_slug}/projects/{project_id}"
        )
        return ProjectResult.model_validate(response.json())  # noqa: F405

    def update_project(
        self,
        company_slug: str,
        project_id: int,
        data: UpdateProjectRequest,  # noqa: F405
    ) -> ProjectResult:  # noqa: F405
        """Update a project."""
        self._request(
            "PATCH",
            f"/companies/{company_slug}/projects/{project_id}",
            json=data.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return self.get_project(company_slug, project_id)

    def delete_project(self, company_slug: str, project_id: int) -> None:
        """Delete a project."""
        self._request("DELETE", f"/companies/{company_slug}/projects/{project_id}")

    # Inbox endpoints

    def get_inbox(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
        **filters: Any,
    ) -> PaginatedIterator[InboxResult]:  # noqa: F405
        """Get inbox documents for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        params.update(filters)
        return PaginatedIterator(
            client=self.client,
            url=f"/companies/{company_slug}/inbox",
            params=params,
            model_class=InboxResult,  # noqa: F405
            headers=self.auth.get_headers(),
        )

    def create_inbox_document(
        self,
        company_slug: str,
        file: Path | str | BinaryIO,
        filename: str | None = None,
    ) -> InboxResult:  # noqa: F405
        """Upload a document to inbox."""
        fname, file_bytes, content_type = prepare_attachment(file, filename)
        files = {
            "file": (fname, file_bytes, content_type),
            "filename": (None, fname),
        }
        response = self._request(
            "POST",
            f"/companies/{company_slug}/inbox",
            files=files,
        )
        location = response.headers.get("Location", "")
        if location and response.status_code == 201:
            doc_id = location.split("/")[-1]
            return self.get_inbox_document(company_slug, int(doc_id))
        return InboxResult.model_validate(response.json())  # noqa: F405

    def get_inbox_document(
        self, company_slug: str, document_id: int
    ) -> InboxResult:  # noqa: F405
        """Get a specific inbox document."""
        response = self._request(
            "GET", f"/companies/{company_slug}/inbox/{document_id}"
        )
        return InboxResult.model_validate(response.json())  # noqa: F405

    # Groups endpoint

    def get_groups(
        self,
        company_slug: str,
        page: int = 0,
        page_size: int = 25,
    ) -> Any:
        """Get customer groups for a company."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        response = self._request(
            "GET",
            f"/companies/{company_slug}/groups",
            params=params,
        )
        return response.json()


class ScopedFikenClient:
    """Scoped Fiken client with pre-filled company_slug.

    Provides convenient access to company-specific endpoints without
    repeating the company_slug parameter.
    """

    def __init__(self, client: FikenClient, company_slug: str) -> None:
        """Initialize scoped client.

        Args:
            client: Parent FikenClient instance
            company_slug: Company identifier to use for all requests
        """
        self._client = client
        self.company_slug = company_slug

    def for_company(
        self,
    ) -> ScopedFikenClient:
        """Create a scoped client for a specific company.

        Args:
            company_slug: Company identifier

        Returns:
            Scoped client with company_slug pre-filled"""
        return self._client.for_company(self.company_slug)

    def get_company(
        self,
    ) -> Company:
        """Get a specific company.

        Args:
            company_slug: Company identifier

        Returns:
            Company details"""
        return self._client.get_company(self.company_slug)

    def get_accounts(
        self,
        from_account: str | None = None,
        to_account: str | None = None,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[Account]:
        """Get accounts for a company.

        Args:
            company_slug: Company identifier
            from_account: Filter by account code range start
            to_account: Filter by account code range end
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of accounts"""
        return self._client.get_accounts(
            self.company_slug, from_account, to_account, page, page_size
        )

    def get_account(self, account_code: str) -> Account:
        """Get a specific account.

        Args:
            company_slug: Company identifier
            account_code: Account code

        Returns:
            Account details"""
        return self._client.get_account(self.company_slug, account_code)

    def get_account_balances(
        self,
        from_account: str | None = None,
        to_account: str | None = None,
        date: date | None = None,
        page: int = 0,
        page_size: int = 25,
    ) -> PaginatedIterator[AccountBalance]:
        """Get account balances for a company.

        Args:
            company_slug: Company identifier
            from_account: Filter by account code range start
            to_account: Filter by account code range end
            date: Filter by specific date (yyyy-mm-dd)
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of account balances"""
        return self._client.get_account_balances(
            self.company_slug, from_account, to_account, date, page, page_size
        )

    def get_account_balance(
        self, account_code: str, date: date | None = None
    ) -> AccountBalance:
        """Get balance for a specific account.

        Args:
            company_slug: Company identifier
            account_code: Account code
            date: Filter by specific date

        Returns:
            Account balance"""
        return self._client.get_account_balance(self.company_slug, account_code, date)

    def get_bank_accounts(
        self, inactive: bool | None = None, page: int = 0, page_size: int = 25
    ) -> PaginatedIterator[BankAccountResult]:
        """Get bank accounts for a company.

        Args:
            company_slug: Company identifier
            inactive: Filter by inactive status
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of bank accounts"""
        return self._client.get_bank_accounts(
            self.company_slug, inactive, page, page_size
        )

    def create_bank_account(self, data: BankAccountRequest) -> BankAccountResult:
        """Create a new bank account.

        Args:
            company_slug: Company identifier
            data: Bank account data

        Returns:
            Created bank account"""
        return self._client.create_bank_account(self.company_slug, data)

    def get_bank_account(self, bank_account_id: int) -> BankAccountResult:
        """Get a specific bank account.

        Args:
            company_slug: Company identifier
            bank_account_id: Bank account ID

        Returns:
            Bank account details"""
        return self._client.get_bank_account(self.company_slug, bank_account_id)

    def get_bank_balances(
        self, date: date | None = None, page: int = 0, page_size: int = 25
    ) -> PaginatedIterator[BankBalanceResult]:
        """Get bank balances for a company.

        Args:
            company_slug: Company identifier
            date: Filter by specific date
            page: Page number
            page_size: Items per page

        Returns:
            Iterator of bank balances"""
        return self._client.get_bank_balances(self.company_slug, date, page, page_size)

    def get_contacts(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[Contact]:
        """Get contacts for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters (name, email, customer, supplier, etc.)

        Returns:
            Iterator of contacts"""
        return self._client.get_contacts(self.company_slug, page, page_size, **filters)

    def create_contact(self, data: Contact) -> Contact:
        """Create a new contact.

        Args:
            company_slug: Company identifier
            data: Contact data

        Returns:
            Created contact"""
        return self._client.create_contact(self.company_slug, data)

    def get_contact(self, contact_id: int) -> Contact:
        """Get a specific contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID

        Returns:
            Contact details"""
        return self._client.get_contact(self.company_slug, contact_id)

    def update_contact(self, contact_id: int, data: Contact) -> Contact:
        """Update a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            data: Updated contact data

        Returns:
            Updated contact"""
        return self._client.update_contact(self.company_slug, contact_id, data)

    def delete_contact(self, contact_id: int) -> None:
        """Delete a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID"""
        return self._client.delete_contact(self.company_slug, contact_id)

    def add_attachment_to_contact(
        self, contact_id: int, file: Path | str | BinaryIO, filename: str | None = None
    ) -> None:
        """Add an attachment to a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            file: File to attach
            filename: Optional filename override"""
        return self._client.add_attachment_to_contact(
            self.company_slug, contact_id, file, filename
        )

    def get_contact_persons(self, contact_id: int) -> list[ContactPerson]:
        """Get contact persons for a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID

        Returns:
            List of contact persons"""
        return self._client.get_contact_persons(self.company_slug, contact_id)

    def add_contact_person(self, contact_id: int, data: ContactPerson) -> ContactPerson:
        """Add a contact person to a contact.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            data: Contact person data

        Returns:
            Created contact person"""
        return self._client.add_contact_person(self.company_slug, contact_id, data)

    def get_contact_person(self, contact_id: int, person_id: int) -> ContactPerson:
        """Get a specific contact person.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            person_id: Contact person ID

        Returns:
            Contact person details"""
        return self._client.get_contact_person(self.company_slug, contact_id, person_id)

    def update_contact_person(
        self, contact_id: int, person_id: int, data: ContactPerson
    ) -> ContactPerson:
        """Update a contact person.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            person_id: Contact person ID
            data: Updated contact person data

        Returns:
            Updated contact person"""
        return self._client.update_contact_person(
            self.company_slug, contact_id, person_id, data
        )

    def delete_contact_person(self, contact_id: int, person_id: int) -> None:
        """Delete a contact person.

        Args:
            company_slug: Company identifier
            contact_id: Contact ID
            person_id: Contact person ID"""
        return self._client.delete_contact_person(
            self.company_slug, contact_id, person_id
        )

    def get_products(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[Product]:
        """Get products for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters (name, productNumber, active, etc.)

        Returns:
            Iterator of products"""
        return self._client.get_products(self.company_slug, page, page_size, **filters)

    def create_product(self, data: Product) -> Product:
        """Create a new product.

        Args:
            company_slug: Company identifier
            data: Product data

        Returns:
            Created product"""
        return self._client.create_product(self.company_slug, data)

    def get_product(self, product_id: int) -> Product:
        """Get a specific product.

        Args:
            company_slug: Company identifier
            product_id: Product ID

        Returns:
            Product details"""
        return self._client.get_product(self.company_slug, product_id)

    def update_product(self, product_id: int, data: Product) -> Product:
        """Update a product.

        Args:
            company_slug: Company identifier
            product_id: Product ID
            data: Updated product data

        Returns:
            Updated product"""
        return self._client.update_product(self.company_slug, product_id, data)

    def delete_product(self, product_id: int) -> None:
        """Delete a product.

        Args:
            company_slug: Company identifier
            product_id: Product ID"""
        return self._client.delete_product(self.company_slug, product_id)

    def create_product_sales_report(
        self, data: ProductSalesReportRequest
    ) -> ProductSalesReportResult:
        """Create a product sales report.

        Args:
            company_slug: Company identifier
            data: Report request data

        Returns:
            Sales report result"""
        return self._client.create_product_sales_report(self.company_slug, data)

    def get_invoices(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[InvoiceResult]:
        """Get invoices for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters (issueDate, customerId, settled, etc.)

        Returns:
            Iterator of invoices"""
        return self._client.get_invoices(self.company_slug, page, page_size, **filters)

    def create_invoice(self, data: InvoiceRequest) -> InvoiceResult:
        """Create a new invoice.

        Args:
            company_slug: Company identifier
            data: Invoice data

        Returns:
            Created invoice"""
        return self._client.create_invoice(self.company_slug, data)

    def get_invoice(self, invoice_id: int) -> InvoiceResult:
        """Get a specific invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID

        Returns:
            Invoice details"""
        return self._client.get_invoice(self.company_slug, invoice_id)

    def update_invoice(
        self, invoice_id: int, data: UpdateInvoiceRequest
    ) -> InvoiceResult:
        """Update an invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID
            data: Update data

        Returns:
            Updated invoice"""
        return self._client.update_invoice(self.company_slug, invoice_id, data)

    def get_invoice_attachments(self, invoice_id: int) -> list[Attachment]:
        """Get attachments for an invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID

        Returns:
            List of attachments"""
        return self._client.get_invoice_attachments(self.company_slug, invoice_id)

    def add_attachment_to_invoice(
        self, invoice_id: int, file: Path | str | BinaryIO, filename: str | None = None
    ) -> None:
        """Add an attachment to an invoice.

        Args:
            company_slug: Company identifier
            invoice_id: Invoice ID
            file: File to attach
            filename: Optional filename override"""
        return self._client.add_attachment_to_invoice(
            self.company_slug, invoice_id, file, filename
        )

    def send_invoice(self, data: SendInvoiceRequest) -> None:
        """Send an invoice.

        Args:
            company_slug: Company identifier
            data: Send invoice request data"""
        return self._client.send_invoice(self.company_slug, data)

    def get_invoice_drafts(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[InvoiceishDraftResult]:
        """Get invoice drafts for a company.

        Args:
            company_slug: Company identifier
            page: Page number
            page_size: Items per page
            **filters: Additional filters

        Returns:
            Iterator of invoice drafts"""
        return self._client.get_invoice_drafts(
            self.company_slug, page, page_size, **filters
        )

    def create_invoice_draft(
        self, data: InvoiceishDraftRequest
    ) -> InvoiceishDraftResult:
        """Create a new invoice draft.

        Args:
            company_slug: Company identifier
            data: Invoice draft data

        Returns:
            Created invoice draft"""
        return self._client.create_invoice_draft(self.company_slug, data)

    def get_invoice_draft(self, draft_id: int) -> InvoiceishDraftResult:
        """Get a specific invoice draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID

        Returns:
            Invoice draft details"""
        return self._client.get_invoice_draft(self.company_slug, draft_id)

    def update_invoice_draft(
        self, draft_id: int, data: InvoiceishDraftRequest
    ) -> InvoiceishDraftResult:
        """Update an invoice draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID
            data: Updated draft data

        Returns:
            Updated invoice draft"""
        return self._client.update_invoice_draft(self.company_slug, draft_id, data)

    def delete_invoice_draft(self, draft_id: int) -> None:
        """Delete an invoice draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID"""
        return self._client.delete_invoice_draft(self.company_slug, draft_id)

    def create_invoice_from_draft(self, draft_id: int) -> InvoiceResult:
        """Create an invoice from a draft.

        Args:
            company_slug: Company identifier
            draft_id: Draft ID

        Returns:
            Created invoice"""
        return self._client.create_invoice_from_draft(self.company_slug, draft_id)

    def get_sales(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[SaleResult]:
        """Get sales for a company."""
        return self._client.get_sales(self.company_slug, page, page_size, **filters)

    def create_sale(self, data: SaleRequest) -> SaleResult:
        """Create a new sale."""
        return self._client.create_sale(self.company_slug, data)

    def get_sale(self, sale_id: int) -> SaleResult:
        """Get a specific sale."""
        return self._client.get_sale(self.company_slug, sale_id)

    def delete_sale(self, sale_id: int) -> None:
        """Delete a sale."""
        return self._client.delete_sale(self.company_slug, sale_id)

    def get_sale_attachments(self, sale_id: int) -> list[Attachment]:
        """Get attachments for a sale."""
        return self._client.get_sale_attachments(self.company_slug, sale_id)

    def add_attachment_to_sale(
        self, sale_id: int, file: Path | str | BinaryIO, filename: str | None = None
    ) -> None:
        """Add an attachment to a sale."""
        return self._client.add_attachment_to_sale(
            self.company_slug, sale_id, file, filename
        )

    def get_sale_payments(self, sale_id: int) -> list[Payment]:
        """Get payments for a sale."""
        return self._client.get_sale_payments(self.company_slug, sale_id)

    def create_sale_payment(self, sale_id: int, data: Payment) -> Payment:
        """Create a payment for a sale."""
        return self._client.create_sale_payment(self.company_slug, sale_id, data)

    def get_sale_payment(self, sale_id: int, payment_id: int) -> Payment:
        """Get a specific sale payment."""
        return self._client.get_sale_payment(self.company_slug, sale_id, payment_id)

    def get_sale_drafts(
        self, page: int = 0, page_size: int = 25
    ) -> PaginatedIterator[DraftResult]:
        """Get sale drafts for a company."""
        return self._client.get_sale_drafts(self.company_slug, page, page_size)

    def create_sale_draft(self, data: DraftRequest) -> DraftResult:
        """Create a new sale draft."""
        return self._client.create_sale_draft(self.company_slug, data)

    def get_sale_draft(self, draft_id: int) -> DraftResult:
        """Get a specific sale draft."""
        return self._client.get_sale_draft(self.company_slug, draft_id)

    def update_sale_draft(self, draft_id: int, data: DraftRequest) -> DraftResult:
        """Update a sale draft."""
        return self._client.update_sale_draft(self.company_slug, draft_id, data)

    def delete_sale_draft(self, draft_id: int) -> None:
        """Delete a sale draft."""
        return self._client.delete_sale_draft(self.company_slug, draft_id)

    def create_sale_from_draft(self, draft_id: int) -> SaleResult:
        """Create a sale from a draft."""
        return self._client.create_sale_from_draft(self.company_slug, draft_id)

    def get_purchases(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[PurchaseResult]:
        """Get purchases for a company."""
        return self._client.get_purchases(self.company_slug, page, page_size, **filters)

    def create_purchase(self, data: PurchaseRequest) -> PurchaseResult:
        """Create a new purchase."""
        return self._client.create_purchase(self.company_slug, data)

    def get_purchase(self, purchase_id: int) -> PurchaseResult:
        """Get a specific purchase."""
        return self._client.get_purchase(self.company_slug, purchase_id)

    def delete_purchase(self, purchase_id: int) -> None:
        """Delete a purchase."""
        return self._client.delete_purchase(self.company_slug, purchase_id)

    def get_purchase_attachments(self, purchase_id: int) -> list[Attachment]:
        """Get attachments for a purchase."""
        return self._client.get_purchase_attachments(self.company_slug, purchase_id)

    def add_attachment_to_purchase(
        self,
        purchase_id: int,
        file: Path | str | BinaryIO,
        filename: str | None = None,
        attach_to_payment: bool = False,
        attach_to_sale: bool = True,
    ) -> None:
        """Add an attachment to a purchase."""
        return self._client.add_attachment_to_purchase(
            self.company_slug,
            purchase_id,
            file,
            filename,
            attach_to_payment,
            attach_to_sale,
        )

    def get_purchase_payments(self, purchase_id: int) -> list[Payment]:
        """Get payments for a purchase."""
        return self._client.get_purchase_payments(self.company_slug, purchase_id)

    def create_purchase_payment(self, purchase_id: int, data: Payment) -> Payment:
        """Create a payment for a purchase."""
        return self._client.create_purchase_payment(
            self.company_slug, purchase_id, data
        )

    def get_purchase_payment(self, purchase_id: int, payment_id: int) -> Payment:
        """Get a specific purchase payment."""
        return self._client.get_purchase_payment(
            self.company_slug, purchase_id, payment_id
        )

    def get_purchase_drafts(
        self, page: int = 0, page_size: int = 25
    ) -> PaginatedIterator[DraftResult]:
        """Get purchase drafts for a company."""
        return self._client.get_purchase_drafts(self.company_slug, page, page_size)

    def create_purchase_draft(self, data: DraftRequest) -> DraftResult:
        """Create a new purchase draft."""
        return self._client.create_purchase_draft(self.company_slug, data)

    def get_purchase_draft(self, draft_id: int) -> DraftResult:
        """Get a specific purchase draft."""
        return self._client.get_purchase_draft(self.company_slug, draft_id)

    def update_purchase_draft(self, draft_id: int, data: DraftRequest) -> DraftResult:
        """Update a purchase draft."""
        return self._client.update_purchase_draft(self.company_slug, draft_id, data)

    def delete_purchase_draft(self, draft_id: int) -> None:
        """Delete a purchase draft."""
        return self._client.delete_purchase_draft(self.company_slug, draft_id)

    def create_purchase_from_draft(self, draft_id: int) -> PurchaseResult:
        """Create a purchase from a draft."""
        return self._client.create_purchase_from_draft(self.company_slug, draft_id)

    def get_credit_notes(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[CreditNoteResult]:
        """Get credit notes for a company."""
        return self._client.get_credit_notes(
            self.company_slug, page, page_size, **filters
        )

    def create_full_credit_note(self, data: FullCreditNoteRequest) -> CreditNoteResult:
        """Create a full credit note."""
        return self._client.create_full_credit_note(self.company_slug, data)

    def create_partial_credit_note(
        self, data: PartialCreditNoteRequest
    ) -> CreditNoteResult:
        """Create a partial credit note."""
        return self._client.create_partial_credit_note(self.company_slug, data)

    def get_credit_note(self, credit_note_id: int) -> CreditNoteResult:
        """Get a specific credit note."""
        return self._client.get_credit_note(self.company_slug, credit_note_id)

    def send_credit_note(self, data: SendCreditNoteRequest) -> None:
        """Send a credit note."""
        return self._client.send_credit_note(self.company_slug, data)

    def get_credit_note_drafts(
        self, page: int = 0, page_size: int = 25
    ) -> PaginatedIterator[InvoiceishDraftResult]:
        """Get credit note drafts for a company."""
        return self._client.get_credit_note_drafts(self.company_slug, page, page_size)

    def create_credit_note_draft(
        self, data: InvoiceishDraftRequest
    ) -> InvoiceishDraftResult:
        """Create a new credit note draft."""
        return self._client.create_credit_note_draft(self.company_slug, data)

    def get_credit_note_draft(self, draft_id: int) -> InvoiceishDraftResult:
        """Get a specific credit note draft."""
        return self._client.get_credit_note_draft(self.company_slug, draft_id)

    def update_credit_note_draft(
        self, draft_id: int, data: InvoiceishDraftRequest
    ) -> InvoiceishDraftResult:
        """Update a credit note draft."""
        return self._client.update_credit_note_draft(self.company_slug, draft_id, data)

    def delete_credit_note_draft(self, draft_id: int) -> None:
        """Delete a credit note draft."""
        return self._client.delete_credit_note_draft(self.company_slug, draft_id)

    def create_credit_note_from_draft(self, draft_id: int) -> CreditNoteResult:
        """Create a credit note from a draft."""
        return self._client.create_credit_note_from_draft(self.company_slug, draft_id)

    def get_journal_entries(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[JournalEntry]:
        """Get journal entries for a company."""
        return self._client.get_journal_entries(
            self.company_slug, page, page_size, **filters
        )

    def create_general_journal_entry(
        self, data: GeneralJournalEntryRequest
    ) -> JournalEntry:
        """Create a general journal entry."""
        return self._client.create_general_journal_entry(self.company_slug, data)

    def get_journal_entry(self, entry_id: int) -> JournalEntry:
        """Get a specific journal entry."""
        return self._client.get_journal_entry(self.company_slug, entry_id)

    def get_journal_entry_attachments(self, entry_id: int) -> list[Attachment]:
        """Get attachments for a journal entry."""
        return self._client.get_journal_entry_attachments(self.company_slug, entry_id)

    def add_attachment_to_journal_entry(
        self, entry_id: int, file: Path | str | BinaryIO, filename: str | None = None
    ) -> None:
        """Add an attachment to a journal entry."""
        return self._client.add_attachment_to_journal_entry(
            self.company_slug, entry_id, file, filename
        )

    def get_transactions(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[Transaction]:
        """Get transactions for a company."""
        return self._client.get_transactions(
            self.company_slug, page, page_size, **filters
        )

    def get_transaction(self, transaction_id: int) -> Transaction:
        """Get a specific transaction."""
        return self._client.get_transaction(self.company_slug, transaction_id)

    def delete_transaction(self, transaction_id: int) -> None:
        """Delete a transaction."""
        return self._client.delete_transaction(self.company_slug, transaction_id)

    def get_projects(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[ProjectResult]:
        """Get projects for a company."""
        return self._client.get_projects(self.company_slug, page, page_size, **filters)

    def create_project(self, data: ProjectRequest) -> ProjectResult:
        """Create a new project."""
        return self._client.create_project(self.company_slug, data)

    def get_project(self, project_id: int) -> ProjectResult:
        """Get a specific project."""
        return self._client.get_project(self.company_slug, project_id)

    def update_project(
        self, project_id: int, data: UpdateProjectRequest
    ) -> ProjectResult:
        """Update a project."""
        return self._client.update_project(self.company_slug, project_id, data)

    def delete_project(self, project_id: int) -> None:
        """Delete a project."""
        return self._client.delete_project(self.company_slug, project_id)

    def get_inbox(
        self, page: int = 0, page_size: int = 25, **filters: Any
    ) -> PaginatedIterator[InboxResult]:
        """Get inbox documents for a company."""
        return self._client.get_inbox(self.company_slug, page, page_size, **filters)

    def create_inbox_document(
        self, file: Path | str | BinaryIO, filename: str | None = None
    ) -> InboxResult:
        """Upload a document to inbox."""
        return self._client.create_inbox_document(self.company_slug, file, filename)

    def get_inbox_document(self, document_id: int) -> InboxResult:
        """Get a specific inbox document."""
        return self._client.get_inbox_document(self.company_slug, document_id)

    def get_groups(self, page: int = 0, page_size: int = 25) -> Any:
        """Get customer groups for a company."""
        return self._client.get_groups(self.company_slug, page, page_size)
