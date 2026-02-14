"""Tests for Enhanced Tables & Breadcrumbs (Phase 7E)."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.user import User
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.document import Document
from app.models.salary import Employee


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ux7e_company(db):
    """Company with data for UX 7E tests."""
    co = Company(name='UX7E AB', org_number='556900-0077', company_type='AB')
    db.session.add(co)
    db.session.flush()

    today = date.today()
    fy = FiscalYear(
        company_id=co.id, year=today.year,
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.flush()

    acct = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')
    acct2 = Account(company_id=co.id, account_number='5010', name='Lokalhyra', account_type='expense')
    db.session.add_all([acct, acct2])
    db.session.flush()

    v = Verification(
        company_id=co.id, fiscal_year_id=fy.id,
        verification_number=1, verification_date=today,
        description='Test',
    )
    db.session.add(v)
    db.session.flush()
    db.session.add(VerificationRow(verification_id=v.id, account_id=acct.id, debit=Decimal('100'), credit=Decimal('0')))
    db.session.add(VerificationRow(verification_id=v.id, account_id=acct2.id, debit=Decimal('0'), credit=Decimal('100')))

    doc = Document(company_id=co.id, file_name='test.pdf', document_type='faktura')
    db.session.add(doc)

    emp = Employee(
        company_id=co.id, first_name='Test', last_name='Person',
        personal_number='19900101-1234', email='test@test.com',
        employment_start=today, monthly_salary=Decimal('30000'),
    )
    db.session.add(emp)

    sup = Supplier(company_id=co.id, name='Supplier UX', org_number='556000-1111')
    db.session.add(sup)
    db.session.flush()
    si = SupplierInvoice(
        company_id=co.id, supplier_id=sup.id, invoice_number='SUX-1',
        invoice_date=today, due_date=today, total_amount=Decimal('1000'),
        status='pending',
    )
    db.session.add(si)

    cust = Customer(company_id=co.id, name='Kund UX', org_number='556000-2222')
    db.session.add(cust)
    db.session.flush()
    ci = CustomerInvoice(
        company_id=co.id, customer_id=cust.id, invoice_number='CUX-1',
        invoice_date=today, due_date=today, total_amount=Decimal('2000'),
        status='draft',
    )
    db.session.add(ci)

    db.session.commit()

    user = User.query.filter_by(username='admin').first()
    if not user:
        user = User(username='ux7e_admin', email='ux7e@test.com', role='admin')
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()

    return {'company': co, 'fy': fy, 'user': user}


def _set_company(client, company):
    with client.session_transaction() as sess:
        sess['active_company_id'] = company.id


# ---------------------------------------------------------------------------
# Breadcrumb Tests
# ---------------------------------------------------------------------------

class TestBreadcrumbs:
    def test_accounting_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/accounting/')
        html = resp.data.decode()
        assert 'breadcrumb' in html
        assert 'Verifikationer' in html

    def test_supplier_invoices_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/invoices/supplier-invoices')
        html = resp.data.decode()
        assert 'breadcrumb' in html
        assert 'Leverantörsfakturor' in html

    def test_customer_invoices_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/invoices/customer-invoices')
        html = resp.data.decode()
        assert 'breadcrumb' in html
        assert 'Kundfakturor' in html

    def test_documents_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/documents/')
        html = resp.data.decode()
        assert 'breadcrumb' in html
        assert 'Dokument' in html

    def test_reports_pnl_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/reports/pnl')
        html = resp.data.decode()
        assert 'breadcrumb' in html

    def test_bank_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/bank/')
        html = resp.data.decode()
        assert 'breadcrumb' in html

    def test_tax_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/tax/')
        html = resp.data.decode()
        assert 'breadcrumb' in html

    def test_salary_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/salary/')
        html = resp.data.decode()
        assert 'breadcrumb' in html

    def test_companies_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/companies/')
        html = resp.data.decode()
        assert 'breadcrumb' in html

    def test_notifications_breadcrumbs(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/notifications/')
        html = resp.data.decode()
        assert 'breadcrumb' in html


# ---------------------------------------------------------------------------
# CSV Export Tests
# ---------------------------------------------------------------------------

class TestCSVExport:
    def test_documents_export_csv(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/documents/export-csv')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_documents_csv_content(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/documents/export-csv')
        content = resp.data.decode('utf-8-sig')
        assert 'Filnamn' in content
        assert 'test.pdf' in content

    def test_employees_export_csv(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/salary/employees/export-csv')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_employees_csv_content(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/salary/employees/export-csv')
        content = resp.data.decode('utf-8-sig')
        assert 'Namn' in content
        assert 'Test Person' in content

    def test_csv_requires_login(self, client):
        resp = client.get('/documents/export-csv')
        assert resp.status_code == 302

    def test_csv_requires_company(self, logged_in_client):
        resp = logged_in_client.get('/documents/export-csv')
        assert resp.status_code == 302  # redirect to dashboard


# ---------------------------------------------------------------------------
# Sticky Header & Column Visibility Tests
# ---------------------------------------------------------------------------

class TestTableEnhancements:
    def test_sticky_header_class(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/accounting/')
        html = resp.data.decode()
        assert 'table-sticky-header' in html

    def test_column_visibility_dropdown(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/accounting/')
        html = resp.data.decode()
        assert 'col-visibility-dropdown' in html
        assert 'Kolumner' in html

    def test_table_responsive_present(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/accounting/')
        html = resp.data.decode()
        assert 'table-responsive' in html

    def test_table_enhancements_js_loaded(self, logged_in_client, ux7e_company):
        _set_company(logged_in_client, ux7e_company['company'])
        resp = logged_in_client.get('/accounting/')
        html = resp.data.decode()
        assert 'table_enhancements.js' in html
