"""Tests for UX polish (Phase 6D): inline validation, empty states, dashboard loading, recurring search."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Customer, CustomerInvoice
from app.models.recurring_invoice import RecurringInvoiceTemplate


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6D Test AB', org_number='556000-7777', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


# ---------------------------------------------------------------------------
# Macro files exist
# ---------------------------------------------------------------------------

class TestMacroFiles:
    def test_form_field_macro_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'macros', 'form_field.html')
        assert os.path.exists(path)

    def test_empty_state_macro_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'macros', 'empty_state.html')
        assert os.path.exists(path)


# ---------------------------------------------------------------------------
# Inline form validation
# ---------------------------------------------------------------------------

class TestInlineValidation:
    def test_employee_form_renders(self, logged_in_client):
        co = _setup_company(logged_in_client)
        response = logged_in_client.get('/salary/employees/new')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'form-label' in html

    def test_bank_account_form_renders(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/bank/accounts/new')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'form-label' in html

    def test_new_supplier_form_renders(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/suppliers/new')
        assert response.status_code == 200

    def test_new_customer_form_renders(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/customers/new')
        assert response.status_code == 200

    def test_recurring_form_renders(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/recurring/new')
        assert response.status_code == 200

    def test_consolidation_form_renders(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/consolidation/groups/new')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Empty states
# ---------------------------------------------------------------------------

class TestEmptyStates:
    def test_verifications_empty_state(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get(f'/accounting/?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'Inga verifikationer' in html
        assert 'bi-journal-text' in html

    def test_supplier_invoices_empty_state(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/supplier-invoices')
        html = response.data.decode()
        assert 'Inga leverantörsfakturor' in html or 'bi-receipt' in html

    def test_customer_invoices_empty_state(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/customer-invoices')
        html = response.data.decode()
        assert 'Inga kundfakturor' in html or 'bi-file-earmark-text' in html

    def test_employees_empty_state(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/salary/employees')
        html = response.data.decode()
        assert 'bi-people' in html

    def test_documents_empty_state(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/documents/')
        html = response.data.decode()
        assert 'bi-folder2-open' in html

    def test_recurring_empty_state(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/recurring/')
        html = response.data.decode()
        assert 'bi-arrow-repeat' in html


# ---------------------------------------------------------------------------
# Dashboard loading indicators
# ---------------------------------------------------------------------------

class TestDashboardLoading:
    def test_dashboard_has_chart_loading_spinner(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        acct = Account(company_id=co.id, account_number=1910,
                       name='Kassa', account_type='asset', active=True)
        db.session.add_all([fy, acct])
        db.session.commit()

        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'chart-loading' in html
        assert 'spinner-border' in html

    def test_dashboard_charts_js_has_show_chart(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'dashboard_charts.js')
        with open(path) as f:
            content = f.read()
        assert 'showChart' in content


# ---------------------------------------------------------------------------
# Recurring search + pagination
# ---------------------------------------------------------------------------

class TestRecurringSearch:
    def test_recurring_list_has_search(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/recurring/')
        html = response.data.decode()
        assert 'name="search"' in html

    def test_recurring_search_filter(self, logged_in_client):
        co = _setup_company(logged_in_client)
        customer = Customer(company_id=co.id, name='Sök Kund AB')
        db.session.add(customer)
        db.session.flush()
        t1 = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=customer.id,
            name='Månadsavgift Test', currency='SEK', vat_type='standard',
            interval='monthly', payment_terms=30,
            start_date=date(2024, 1, 1), next_date=date(2024, 2, 1),
        )
        t2 = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=customer.id,
            name='Kvartalsrapport', currency='SEK', vat_type='standard',
            interval='quarterly', payment_terms=30,
            start_date=date(2024, 1, 1), next_date=date(2024, 4, 1),
        )
        db.session.add_all([t1, t2])
        db.session.commit()

        # Search by name
        response = logged_in_client.get('/invoices/recurring/?search=Månadsavgift')
        html = response.data.decode()
        assert 'Månadsavgift Test' in html
        assert 'Kvartalsrapport' not in html

    def test_recurring_pagination(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/recurring/')
        # Page loads successfully with pagination
        assert response.status_code == 200
