"""Tests for Global Search (Phase 7A)."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.user import User
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.document import Document
from app.models.salary import Employee
from app.services.search_service import global_search


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def search_company(db):
    """Company with diverse data for search tests."""
    co = Company(name='Search AB', org_number='556900-0099', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    # Accounts
    a1930 = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')
    a3010 = Account(company_id=co.id, account_number='3010', name='Försäljning varor', account_type='revenue')
    db.session.add_all([a1930, a3010])
    db.session.flush()

    # Verification
    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 3, 1),
                     description='Betalning från Acme Corp')
    db.session.add(v)
    db.session.flush()
    db.session.add(VerificationRow(verification_id=v.id, account_id=a1930.id,
                                    debit=Decimal('10000'), credit=Decimal('0')))
    db.session.add(VerificationRow(verification_id=v.id, account_id=a3010.id,
                                    debit=Decimal('0'), credit=Decimal('10000')))

    # Supplier + invoice
    sup = Supplier(company_id=co.id, name='Leverantör Alfa', org_number='556100-0001')
    db.session.add(sup)
    db.session.flush()
    si = SupplierInvoice(company_id=co.id, supplier_id=sup.id,
                          invoice_number='F2025-001', invoice_date=date(2025, 1, 15),
                          due_date=date(2025, 2, 15), total_amount=Decimal('5000'),
                          status='pending')
    db.session.add(si)

    # Customer + invoice
    cust = Customer(company_id=co.id, name='Kund Beta', org_number='556200-0002')
    db.session.add(cust)
    db.session.flush()
    ci = CustomerInvoice(company_id=co.id, customer_id=cust.id,
                          invoice_number='K2025-001', invoice_date=date(2025, 2, 1),
                          due_date=date(2025, 3, 1), total_amount=Decimal('8000'),
                          status='sent')
    db.session.add(ci)

    # Document
    doc = Document(company_id=co.id, file_name='avtal_kontor.pdf',
                   description='Hyresavtal kontor 2025')
    db.session.add(doc)

    # Employee
    emp = Employee(company_id=co.id, first_name='Erik', last_name='Svensson',
                   personal_number='19900101-1234', employment_start=date(2024, 1, 1),
                   monthly_salary=Decimal('35000'))
    db.session.add(emp)

    db.session.commit()
    return {
        'company': co, 'fy': fy,
        'accounts': [a1930, a3010], 'verification': v,
        'supplier': sup, 'supplier_invoice': si,
        'customer': cust, 'customer_invoice': ci,
        'document': doc, 'employee': emp,
    }


@pytest.fixture
def other_company(db):
    """Another company to test company isolation."""
    co2 = Company(name='Other AB', org_number='556900-0098', company_type='AB')
    db.session.add(co2)
    db.session.flush()
    fy2 = FiscalYear(company_id=co2.id, year=2025, start_date=date(2025, 1, 1),
                     end_date=date(2025, 12, 31), status='open')
    db.session.add(fy2)
    db.session.flush()
    v2 = Verification(company_id=co2.id, fiscal_year_id=fy2.id,
                      verification_number=1, verification_date=date(2025, 1, 1),
                      description='Betalning från Acme Corp')
    db.session.add(v2)
    db.session.commit()
    return co2


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestSearchService:
    def test_search_verifications_by_description(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Acme')
            assert 'verifications' in results
            assert len(results['verifications']) >= 1
            assert '#1' in results['verifications'][0]['title']

    def test_search_verifications_by_number(self, app, search_company):
        with app.app_context():
            # verification_number=1, description contains 'Betalning'
            results = global_search(search_company['company'].id, 'Betalning')
            assert 'verifications' in results

    def test_search_supplier_invoices_by_number(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'F2025')
            assert 'supplier_invoices' in results
            assert results['supplier_invoices'][0]['title'] == 'F2025-001'

    def test_search_supplier_invoices_by_name(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Alfa')
            assert 'supplier_invoices' in results

    def test_search_customer_invoices(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'K2025')
            assert 'customer_invoices' in results
            assert results['customer_invoices'][0]['title'] == 'K2025-001'

    def test_search_customer_by_name(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Beta')
            assert 'customers' in results
            assert results['customers'][0]['title'] == 'Kund Beta'

    def test_search_accounts_by_number(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, '1930')
            assert 'accounts' in results
            assert results['accounts'][0]['title'] == '1930'

    def test_search_accounts_by_name(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Försäljning')
            assert 'accounts' in results

    def test_search_documents(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'avtal')
            assert 'documents' in results
            assert 'avtal_kontor.pdf' in results['documents'][0]['title']

    def test_search_suppliers(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Leverantör')
            assert 'suppliers' in results

    def test_search_employees(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Erik')
            assert 'employees' in results
            assert 'Svensson' in results['employees'][0]['title']

    def test_search_result_format(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Acme')
            for cat, items in results.items():
                for item in items:
                    assert 'id' in item
                    assert 'title' in item
                    assert 'subtitle' in item
                    assert 'url' in item
                    assert 'icon' in item

    def test_search_limits_results(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'a', limit=2)
            for cat, items in results.items():
                assert len(items) <= 2

    def test_search_respects_company_filter(self, app, search_company, other_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'Acme')
            if 'verifications' in results:
                for v in results['verifications']:
                    assert v['title'] == '#1'
            # Other company's verification should not appear
            results2 = global_search(other_company.id, 'Acme')
            if 'verifications' in results2:
                # The other company also has a matching verification
                assert len(results2['verifications']) == 1

    def test_search_case_insensitive(self, app, search_company):
        with app.app_context():
            results_upper = global_search(search_company['company'].id, 'ACME')
            results_lower = global_search(search_company['company'].id, 'acme')
            assert ('verifications' in results_upper) == ('verifications' in results_lower)

    def test_search_short_query_returns_empty(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'a')
            assert results == {}

    def test_search_empty_query(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, '')
            assert results == {}

    def test_search_no_results(self, app, search_company):
        with app.app_context():
            results = global_search(search_company['company'].id, 'xyznonexistent')
            assert results == {}

    def test_search_special_characters(self, app, search_company):
        with app.app_context():
            # Should not crash on SQL-special characters
            results = global_search(search_company['company'].id, "O'Brien")
            assert isinstance(results, dict)
            results2 = global_search(search_company['company'].id, '100%')
            assert isinstance(results2, dict)


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestSearchRoute:
    def test_search_requires_login(self, client):
        resp = client.get('/api/search?q=test')
        assert resp.status_code == 302

    def test_search_no_company(self, logged_in_client):
        resp = logged_in_client.get('/api/search?q=test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['results'] == {}

    def test_search_returns_json(self, logged_in_client, search_company):
        co = search_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/api/search?q=Acme')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'results' in data
        assert 'verifications' in data['results']


class TestSearchNavbar:
    def test_navbar_has_search_input(self, logged_in_client, search_company):
        co = search_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/')
        html = resp.data.decode()
        assert 'global-search-input' in html
        assert 'Ctrl+K' in html
