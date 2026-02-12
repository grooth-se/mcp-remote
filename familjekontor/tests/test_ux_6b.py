"""Tests for UX polish (Phase 6B): breadcrumbs, column sorting, form submit spinner."""
from datetime import date

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, Customer, SupplierInvoice, CustomerInvoice
from app.models.salary import Employee


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6B Test AB', org_number='556000-8888', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


# ---------------------------------------------------------------------------
# Breadcrumbs
# ---------------------------------------------------------------------------

class TestBreadcrumbs:
    def test_breadcrumbs_macro_file_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'macros', 'breadcrumbs.html')
        assert os.path.exists(path)

    def test_verification_detail_has_breadcrumb(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.flush()
        acct = Account(company_id=co.id, account_number=1910,
                       name='Kassa', account_type='asset', active=True)
        db.session.add(acct)
        db.session.flush()
        ver = Verification(company_id=co.id, fiscal_year_id=fy.id,
                           verification_number=1, verification_date=date(2024, 6, 1),
                           description='Test ver')
        db.session.add(ver)
        db.session.flush()
        db.session.add(VerificationRow(verification_id=ver.id, account_id=acct.id,
                                       debit=100, credit=0))
        db.session.commit()

        response = logged_in_client.get(f'/accounting/verification/{ver.id}')
        html = response.data.decode()
        assert 'breadcrumb' in html
        assert 'Verifikationer' in html

    def test_new_verification_has_breadcrumb(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get('/accounting/verification/new')
        html = response.data.decode()
        assert 'breadcrumb' in html

    def test_trial_balance_has_breadcrumb(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get('/accounting/trial-balance')
        html = response.data.decode()
        assert 'breadcrumb' in html
        assert 'Råbalans' in html or 'R\u00e5balans' in html

    def test_new_supplier_has_breadcrumb(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/suppliers/new')
        html = response.data.decode()
        assert 'breadcrumb' in html
        assert 'Leverantörer' in html or 'Leverant' in html


# ---------------------------------------------------------------------------
# Column sorting
# ---------------------------------------------------------------------------

class TestColumnSorting:
    def test_verifications_sort_by_date(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get(
            f'/accounting/?fiscal_year_id={fy.id}&sort=verification_date&order=asc')
        assert response.status_code == 200

    def test_verifications_sort_link_in_header(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get(f'/accounting/?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'sort=verification_number' in html
        assert 'sort=verification_date' in html

    def test_suppliers_sort_by_name(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/suppliers?sort=name&order=desc')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'sort=name' in html

    def test_supplier_invoices_sort_by_amount(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/supplier-invoices?sort=total_amount&order=asc')
        assert response.status_code == 200

    def test_customers_sort_by_payment_terms(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/customers?sort=payment_terms&order=desc')
        assert response.status_code == 200

    def test_customer_invoices_sort_by_due_date(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/customer-invoices?sort=due_date&order=asc')
        assert response.status_code == 200

    def test_employees_sort_by_salary(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/salary/employees?sort=monthly_salary&order=desc')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'sort=monthly_salary' in html

    def test_invalid_sort_column_ignored(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/suppliers?sort=DROP_TABLE&order=asc')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Form submit spinner
# ---------------------------------------------------------------------------

class TestFormSubmitSpinner:
    def test_form_submit_js_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'form_submit.js')
        assert os.path.exists(path)

    def test_base_includes_form_submit_js(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/accounting/')
        html = response.data.decode()
        assert 'form_submit.js' in html
