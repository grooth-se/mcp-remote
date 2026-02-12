"""Tests for UX polish (Phase 6A): pagination, search, flash auto-fade, confirmations."""
from datetime import date

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, Customer, SupplierInvoice, CustomerInvoice
from app.models.salary import Employee


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX Test AB', org_number='556000-9999', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


class TestVerificationPagination:
    def test_verifications_paginated(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get(f'/accounting/?fiscal_year_id={fy.id}')
        assert response.status_code == 200
        assert 'Verifikationer' in response.data.decode()

    def test_verifications_search(self, logged_in_client):
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
                           description='Kontorsmat Unik123')
        db.session.add(ver)
        db.session.flush()
        db.session.add(VerificationRow(verification_id=ver.id, account_id=acct.id,
                                       debit=100, credit=0))
        db.session.commit()

        response = logged_in_client.get(
            f'/accounting/?fiscal_year_id={fy.id}&search=Unik123')
        html = response.data.decode()
        assert 'Kontorsmat Unik123' in html

        response2 = logged_in_client.get(
            f'/accounting/?fiscal_year_id={fy.id}&search=DOESNOTEXIST')
        html2 = response2.data.decode()
        assert 'Kontorsmat Unik123' not in html2


class TestSupplierPagination:
    def test_suppliers_paginated(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/suppliers')
        assert response.status_code == 200
        assert 'Leverantörer' in response.data.decode()

    def test_suppliers_search(self, logged_in_client):
        co = _setup_company(logged_in_client)
        s = Supplier(company_id=co.id, name='TestLev XYZ',
                     org_number='556000-1234', payment_terms=30)
        db.session.add(s)
        db.session.commit()

        response = logged_in_client.get('/invoices/suppliers?search=XYZ')
        assert 'TestLev XYZ' in response.data.decode()

        response2 = logged_in_client.get('/invoices/suppliers?search=NOMATCH')
        assert 'TestLev XYZ' not in response2.data.decode()


class TestCustomerPagination:
    def test_customers_paginated(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/customers')
        assert response.status_code == 200
        assert 'Kunder' in response.data.decode()

    def test_customers_search(self, logged_in_client):
        co = _setup_company(logged_in_client)
        c = Customer(company_id=co.id, name='KundABC Unik',
                     payment_terms=30, default_currency='SEK', country='SE')
        db.session.add(c)
        db.session.commit()

        response = logged_in_client.get('/invoices/customers?search=KundABC')
        assert 'KundABC Unik' in response.data.decode()

        response2 = logged_in_client.get('/invoices/customers?search=NOMATCH')
        assert 'KundABC Unik' not in response2.data.decode()


class TestSupplierInvoicePagination:
    def test_supplier_invoices_paginated(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/supplier-invoices')
        assert response.status_code == 200
        assert 'Leverantörsfakturor' in response.data.decode()


class TestCustomerInvoicePagination:
    def test_customer_invoices_paginated(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/customer-invoices')
        assert response.status_code == 200
        assert 'Kundfakturor' in response.data.decode()


class TestEmployeePagination:
    def test_employees_paginated(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/salary/employees')
        assert response.status_code == 200
        assert 'Anställda' in response.data.decode()

    def test_employees_search(self, logged_in_client):
        co = _setup_company(logged_in_client)
        emp = Employee(company_id=co.id, first_name='Anna',
                       last_name='Sökbar', personal_number='199001011234',
                       employment_start=date(2024, 1, 1),
                       monthly_salary=30000, pension_plan='ITP1',
                       tax_column=1, tax_table=30)
        db.session.add(emp)
        db.session.commit()

        response = logged_in_client.get('/salary/employees?search=Sökbar')
        assert 'Sökbar' in response.data.decode()

        response2 = logged_in_client.get('/salary/employees?search=NOMATCH')
        assert 'Sökbar' not in response2.data.decode()


class TestFlashAutoFade:
    def test_base_includes_auto_fade_js(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/accounting/')
        html = response.data.decode()
        assert 'bootstrap.Alert' in html

    def test_base_includes_confirm_dialog_js(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/accounting/')
        html = response.data.decode()
        assert 'confirm_dialog.js' in html


class TestConfirmDialogFile:
    def test_confirm_dialog_js_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'js', 'confirm_dialog.js')
        assert os.path.exists(path)


class TestPaginationMacro:
    def test_pagination_macro_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'app', 'templates', 'macros', 'pagination.html')
        assert os.path.exists(path)
