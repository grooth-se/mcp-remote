"""Tests for AR/AP & Customer/Supplier analysis (Phase 6D)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Customer, Supplier, CustomerInvoice, SupplierInvoice
from app.services.arap_service import (
    get_ar_aging_by_customer, get_ap_aging_by_supplier,
    get_dso, get_dpo,
    get_top_customers, get_top_suppliers,
    get_customer_revenue_breakdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def arap_company(db):
    """Company with customers, suppliers, and invoices for ARAP tests."""
    co = Company(name='ARAP AB', org_number='556800-0091', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    # Accounts for DSO/DPO
    accts = {}
    for num, name, atype in [
        ('1510', 'Kundfordringar', 'asset'),
        ('1930', 'Företagskonto', 'asset'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('3010', 'Försäljning', 'revenue'),
        ('4010', 'Inköp', 'expense'),
    ]:
        a = Account(company_id=co.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accts[num] = a

    # Revenue 200000, Receivables 40000, COGS 80000, Payables 20000
    _add_ver(db, co.id, fy.id, 1, date(2025, 3, 1), [
        (accts['1930'], Decimal('200000'), Decimal('0')),
        (accts['3010'], Decimal('0'), Decimal('200000')),
    ])
    _add_ver(db, co.id, fy.id, 2, date(2025, 4, 1), [
        (accts['1510'], Decimal('40000'), Decimal('0')),
        (accts['3010'], Decimal('0'), Decimal('40000')),
    ])
    _add_ver(db, co.id, fy.id, 3, date(2025, 5, 1), [
        (accts['4010'], Decimal('80000'), Decimal('0')),
        (accts['1930'], Decimal('0'), Decimal('80000')),
    ])
    _add_ver(db, co.id, fy.id, 4, date(2025, 5, 15), [
        (accts['4010'], Decimal('20000'), Decimal('0')),
        (accts['2440'], Decimal('0'), Decimal('20000')),
    ])

    # Customers
    cust_a = Customer(company_id=co.id, name='Kund Alfa')
    cust_b = Customer(company_id=co.id, name='Kund Beta')
    db.session.add_all([cust_a, cust_b])
    db.session.flush()

    today = date.today()

    # Customer invoices — Alfa: 2 invoices, Beta: 1 invoice
    # Alfa invoice 1: due in future (current)
    inv1 = CustomerInvoice(
        company_id=co.id, customer_id=cust_a.id,
        invoice_number='F001', invoice_date=date(2025, 3, 1),
        due_date=today + timedelta(days=10),
        amount_excl_vat=Decimal('50000'), vat_amount=Decimal('12500'),
        total_amount=Decimal('62500'), status='sent')
    # Alfa invoice 2: overdue 45 days (31-60 bucket)
    inv2 = CustomerInvoice(
        company_id=co.id, customer_id=cust_a.id,
        invoice_number='F002', invoice_date=date(2025, 2, 1),
        due_date=today - timedelta(days=45),
        amount_excl_vat=Decimal('30000'), vat_amount=Decimal('7500'),
        total_amount=Decimal('37500'), status='sent')
    # Beta invoice: overdue 10 days (1-30 bucket)
    inv3 = CustomerInvoice(
        company_id=co.id, customer_id=cust_b.id,
        invoice_number='F003', invoice_date=date(2025, 4, 1),
        due_date=today - timedelta(days=10),
        amount_excl_vat=Decimal('20000'), vat_amount=Decimal('5000'),
        total_amount=Decimal('25000'), status='sent')
    # Paid invoice — should NOT appear in aging
    inv4 = CustomerInvoice(
        company_id=co.id, customer_id=cust_a.id,
        invoice_number='F004', invoice_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
        amount_excl_vat=Decimal('10000'), vat_amount=Decimal('2500'),
        total_amount=Decimal('12500'), status='paid',
        paid_at=datetime(2025, 1, 20))
    db.session.add_all([inv1, inv2, inv3, inv4])

    # Suppliers
    sup_a = Supplier(company_id=co.id, name='Leverantör X')
    sup_b = Supplier(company_id=co.id, name='Leverantör Y')
    db.session.add_all([sup_a, sup_b])
    db.session.flush()

    # Supplier invoices
    sinv1 = SupplierInvoice(
        company_id=co.id, supplier_id=sup_a.id,
        invoice_number='L001', invoice_date=date(2025, 3, 1),
        due_date=today + timedelta(days=5),
        total_amount=Decimal('30000'), status='approved')
    sinv2 = SupplierInvoice(
        company_id=co.id, supplier_id=sup_b.id,
        invoice_number='L002', invoice_date=date(2025, 2, 1),
        due_date=today - timedelta(days=100),
        total_amount=Decimal('15000'), status='pending')
    # Paid supplier invoice — should NOT appear
    sinv3 = SupplierInvoice(
        company_id=co.id, supplier_id=sup_a.id,
        invoice_number='L003', invoice_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
        total_amount=Decimal('8000'), status='paid',
        paid_at=datetime(2025, 1, 25))
    db.session.add_all([sinv1, sinv2, sinv3])

    db.session.commit()

    return {
        'company': co, 'fy': fy, 'accounts': accts,
        'customers': {'a': cust_a, 'b': cust_b},
        'suppliers': {'a': sup_a, 'b': sup_b},
    }


def _add_ver(db, company_id, fy_id, num, ver_date, rows):
    v = Verification(company_id=company_id, fiscal_year_id=fy_id,
                     verification_number=num, verification_date=ver_date)
    db.session.add(v)
    db.session.flush()
    for account, debit, credit in rows:
        db.session.add(VerificationRow(
            verification_id=v.id, account_id=account.id,
            debit=debit, credit=credit))


# ---------------------------------------------------------------------------
# AR Aging Tests
# ---------------------------------------------------------------------------

class TestARaging:
    def test_basic_aging(self, app, arap_company):
        with app.app_context():
            ar = get_ar_aging_by_customer(arap_company['company'].id)
            assert len(ar['rows']) == 2  # Two customers with unpaid invoices

    def test_aging_buckets(self, app, arap_company):
        with app.app_context():
            ar = get_ar_aging_by_customer(arap_company['company'].id)
            alfa = next(r for r in ar['rows'] if r['customer_name'] == 'Kund Alfa')
            # Invoice 1: current (62500), Invoice 2: 31-60 days (37500)
            assert alfa['current'] == 62500.0
            assert alfa['31_60'] == 37500.0
            assert alfa['total'] == 100000.0

    def test_totals(self, app, arap_company):
        with app.app_context():
            ar = get_ar_aging_by_customer(arap_company['company'].id)
            # Total = 62500 + 37500 + 25000 = 125000
            assert ar['totals']['total'] == 125000.0

    def test_paid_excluded(self, app, arap_company):
        with app.app_context():
            ar = get_ar_aging_by_customer(arap_company['company'].id)
            # F004 (paid) should not appear — total should be 125000 not 137500
            assert ar['totals']['total'] == 125000.0

    def test_sorted_by_total(self, app, arap_company):
        with app.app_context():
            ar = get_ar_aging_by_customer(arap_company['company'].id)
            if len(ar['rows']) >= 2:
                assert ar['rows'][0]['total'] >= ar['rows'][1]['total']

    def test_no_invoices(self, app, db):
        with app.app_context():
            co = Company(name='EmptyAR AB', org_number='556800-0092', company_type='AB')
            db.session.add(co)
            db.session.commit()
            ar = get_ar_aging_by_customer(co.id)
            assert ar['rows'] == []
            assert ar['totals']['total'] == 0.0


# ---------------------------------------------------------------------------
# AP Aging Tests
# ---------------------------------------------------------------------------

class TestAPaging:
    def test_basic_aging(self, app, arap_company):
        with app.app_context():
            ap = get_ap_aging_by_supplier(arap_company['company'].id)
            assert len(ap['rows']) == 2

    def test_includes_approved(self, app, arap_company):
        with app.app_context():
            ap = get_ap_aging_by_supplier(arap_company['company'].id)
            x = next(r for r in ap['rows'] if r['supplier_name'] == 'Leverantör X')
            # L001 is approved, due in future → current
            assert x['current'] == 30000.0

    def test_90_plus_bucket(self, app, arap_company):
        with app.app_context():
            ap = get_ap_aging_by_supplier(arap_company['company'].id)
            y = next(r for r in ap['rows'] if r['supplier_name'] == 'Leverantör Y')
            # L002 overdue 100 days → 90+ bucket
            assert y['90_plus'] == 15000.0

    def test_paid_excluded(self, app, arap_company):
        with app.app_context():
            ap = get_ap_aging_by_supplier(arap_company['company'].id)
            # L003 (paid) should not appear
            assert ap['totals']['total'] == 45000.0


# ---------------------------------------------------------------------------
# DSO/DPO Tests
# ---------------------------------------------------------------------------

class TestDSODPO:
    def test_dso_calculation(self, app, arap_company):
        with app.app_context():
            dso = get_dso(arap_company['company'].id, arap_company['fy'].id)
            # AR (15xx) = 40000, Revenue (3xxx) = 240000
            # DSO = (40000 / 240000) * 365 = 60.8
            assert dso is not None
            assert abs(dso - 60.8) < 0.5

    def test_dpo_calculation(self, app, arap_company):
        with app.app_context():
            dpo = get_dpo(arap_company['company'].id, arap_company['fy'].id)
            # AP (24xx) = 20000, COGS (4xxx) = 100000
            # DPO = (20000 / 100000) * 365 = 73.0
            assert dpo is not None
            assert abs(dpo - 73.0) < 0.5

    def test_no_revenue(self, app, db):
        with app.app_context():
            co = Company(name='NoRevDSO AB', org_number='556800-0093', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.commit()
            assert get_dso(co.id, fy.id) is None

    def test_no_cogs(self, app, db):
        with app.app_context():
            co = Company(name='NoCogsDPO AB', org_number='556800-0094', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.commit()
            assert get_dpo(co.id, fy.id) is None


# ---------------------------------------------------------------------------
# Top Customers/Suppliers Tests
# ---------------------------------------------------------------------------

class TestTopCustomers:
    def test_ordered(self, app, arap_company):
        with app.app_context():
            top = get_top_customers(arap_company['company'].id, arap_company['fy'].id)
            assert len(top) >= 2
            # Alfa has more invoiced amount than Beta
            assert top[0]['customer_name'] == 'Kund Alfa'

    def test_invoice_count(self, app, arap_company):
        with app.app_context():
            top = get_top_customers(arap_company['company'].id, arap_company['fy'].id)
            alfa = next(c for c in top if c['customer_name'] == 'Kund Alfa')
            # Alfa has 3 invoices (F001, F002, F004)
            assert alfa['invoice_count'] == 3

    def test_avg_payment_days(self, app, arap_company):
        with app.app_context():
            top = get_top_customers(arap_company['company'].id, arap_company['fy'].id)
            alfa = next(c for c in top if c['customer_name'] == 'Kund Alfa')
            # F004: paid 2025-01-20, invoice_date 2025-01-01 = 19 days
            assert alfa['avg_payment_days'] == 19

    def test_limit(self, app, arap_company):
        with app.app_context():
            top = get_top_customers(arap_company['company'].id, arap_company['fy'].id, limit=1)
            assert len(top) == 1


class TestTopSuppliers:
    def test_ordered(self, app, arap_company):
        with app.app_context():
            top = get_top_suppliers(arap_company['company'].id, arap_company['fy'].id)
            assert len(top) >= 2
            # X has 30000+8000=38000, Y has 15000
            assert top[0]['supplier_name'] == 'Leverantör X'

    def test_avg_payment_days(self, app, arap_company):
        with app.app_context():
            top = get_top_suppliers(arap_company['company'].id, arap_company['fy'].id)
            x = next(s for s in top if s['supplier_name'] == 'Leverantör X')
            # L003: paid 2025-01-25, invoice 2025-01-01 = 24 days
            assert x['avg_payment_days'] == 24


# ---------------------------------------------------------------------------
# Revenue Breakdown Tests
# ---------------------------------------------------------------------------

class TestRevenueBreakdown:
    def test_breakdown(self, app, arap_company):
        with app.app_context():
            bd = get_customer_revenue_breakdown(arap_company['company'].id, arap_company['fy'].id)
            assert len(bd['labels']) >= 2
            assert len(bd['values']) == len(bd['labels'])

    def test_no_invoices(self, app, db):
        with app.app_context():
            co = Company(name='NoBD AB', org_number='556800-0095', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.commit()
            bd = get_customer_revenue_breakdown(co.id, fy.id)
            assert bd == {'labels': [], 'values': []}


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestARAPRoutes:
    def test_index(self, logged_in_client, arap_company):
        co = arap_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id
        resp = logged_in_client.get('/arap/')
        assert resp.status_code == 200
        assert 'Kund/Leverantörsanalys' in resp.data.decode()

    def test_receivables(self, logged_in_client, arap_company):
        co = arap_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id
        resp = logged_in_client.get('/arap/receivables')
        assert resp.status_code == 200
        assert 'Kund Alfa' in resp.data.decode()

    def test_payables(self, logged_in_client, arap_company):
        co = arap_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id
        resp = logged_in_client.get('/arap/payables')
        assert resp.status_code == 200

    def test_api_top_customers(self, logged_in_client, arap_company):
        co = arap_company['company']
        fy = arap_company['fy']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id
        resp = logged_in_client.get(f'/arap/api/top-customers?fiscal_year_id={fy.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data

    def test_api_revenue_breakdown(self, logged_in_client, arap_company):
        co = arap_company['company']
        fy = arap_company['fy']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id
        resp = logged_in_client.get(f'/arap/api/revenue-breakdown?fiscal_year_id={fy.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data

    def test_no_company_redirect(self, logged_in_client):
        resp = logged_in_client.get('/arap/', follow_redirects=False)
        assert resp.status_code == 302
