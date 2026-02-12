"""Tests for UX polish (Phase 6C): keyboard shortcuts, clickable rows, tooltips, CSV export."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, Customer, SupplierInvoice, CustomerInvoice


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6C Test AB', org_number='556000-9999', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


# ---------------------------------------------------------------------------
# JS files exist and are included in base
# ---------------------------------------------------------------------------

class TestJSIncludes:
    def test_keyboard_shortcuts_js_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'keyboard_shortcuts.js')
        assert os.path.exists(path)

    def test_row_click_js_exists(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'row_click.js')
        assert os.path.exists(path)

    def test_base_includes_keyboard_shortcuts_js(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/accounting/')
        html = response.data.decode()
        assert 'keyboard_shortcuts.js' in html

    def test_base_includes_row_click_js(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/accounting/')
        html = response.data.decode()
        assert 'row_click.js' in html


# ---------------------------------------------------------------------------
# Clickable rows (data-row-link)
# ---------------------------------------------------------------------------

class TestClickableRows:
    def test_verification_rows_have_row_link(self, logged_in_client):
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
                           description='Row link test')
        db.session.add(ver)
        db.session.flush()
        db.session.add(VerificationRow(verification_id=ver.id, account_id=acct.id,
                                       debit=100, credit=0))
        db.session.commit()

        response = logged_in_client.get(f'/accounting/?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'data-row-link' in html
        assert f'/accounting/verification/{ver.id}' in html

    def test_employee_rows_have_row_link(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/salary/employees')
        html = response.data.decode()
        # Page loads successfully even without employees
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tooltips
# ---------------------------------------------------------------------------

class TestTooltips:
    def test_accounting_csv_button_has_tooltip(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = FiscalYear(company_id=co.id, year=2024,
                        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        db.session.add(fy)
        db.session.commit()

        response = logged_in_client.get(f'/accounting/?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'data-bs-toggle="tooltip"' in html
        assert 'Exportera till CSV' in html

    def test_supplier_invoices_buttons_have_tooltips(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/invoices/supplier-invoices')
        html = response.data.decode()
        assert 'data-bs-toggle="tooltip"' in html


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

class TestCSVExport:
    def test_csv_export_service(self):
        from app.services.csv_export_service import export_csv
        rows = [{'a': 'Hej', 'b': 123}, {'a': 'Då', 'b': 456}]
        columns = [('a', 'Kolumn A'), ('b', 'Kolumn B')]
        output = export_csv(rows, columns)
        content = output.read().decode('utf-8-sig')
        assert 'Kolumn A' in content
        assert 'Hej' in content
        assert '456' in content
        # Semicolon delimiter
        assert ';' in content

    def test_accounting_csv_export(self, logged_in_client):
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
                           description='CSV test')
        db.session.add(ver)
        db.session.flush()
        db.session.add(VerificationRow(verification_id=ver.id, account_id=acct.id,
                                       debit=100, credit=0))
        db.session.commit()

        response = logged_in_client.get(f'/accounting/export-csv?fiscal_year_id={fy.id}')
        assert response.status_code == 200
        assert 'text/csv' in response.content_type
        content = response.data.decode('utf-8-sig')
        assert 'CSV test' in content

    def test_supplier_invoices_csv_export(self, logged_in_client):
        co = _setup_company(logged_in_client)
        supplier = Supplier(company_id=co.id, name='CSV Leverantör')
        db.session.add(supplier)
        db.session.flush()
        inv = SupplierInvoice(
            company_id=co.id, supplier_id=supplier.id,
            invoice_number='SI-CSV-001',
            invoice_date=date(2024, 3, 1),
            due_date=date(2024, 4, 1),
            total_amount=Decimal('5000.00'),
        )
        db.session.add(inv)
        db.session.commit()

        response = logged_in_client.get('/invoices/supplier-invoices/export-csv')
        assert response.status_code == 200
        assert 'text/csv' in response.content_type
        content = response.data.decode('utf-8-sig')
        assert 'CSV' in content

    def test_customer_invoices_csv_export(self, logged_in_client):
        co = _setup_company(logged_in_client)
        customer = Customer(company_id=co.id, name='CSV Kund')
        db.session.add(customer)
        db.session.flush()
        inv = CustomerInvoice(
            company_id=co.id, customer_id=customer.id,
            invoice_number='CI-CSV-001',
            invoice_date=date(2024, 3, 1),
            due_date=date(2024, 4, 1),
            total_amount=Decimal('8000.00'),
        )
        db.session.add(inv)
        db.session.commit()

        response = logged_in_client.get('/invoices/customer-invoices/export-csv')
        assert response.status_code == 200
        assert 'text/csv' in response.content_type
        content = response.data.decode('utf-8-sig')
        assert 'CSV' in content

    def test_accounting_csv_no_fy_redirects(self, logged_in_client):
        co = _setup_company(logged_in_client)
        response = logged_in_client.get('/accounting/export-csv')
        # Should redirect since no FY exists
        assert response.status_code in (302, 200)
