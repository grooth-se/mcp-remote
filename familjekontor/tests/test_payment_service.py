"""Tests for payment_service functions."""

from datetime import date, datetime, timezone
from decimal import Decimal
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.tax import TaxPayment
from app.services.payment_service import get_all_payments


@pytest.fixture
def company(db):
    c = Company(name='TestAB', org_number='5566778899', company_type='AB')
    db.session.add(c)
    db.session.flush()
    return c


@pytest.fixture
def payment_data(db, company):
    """Create supplier invoice, customer invoice, and tax payment — all paid."""
    # Supplier + paid invoice
    supplier = Supplier(company_id=company.id, name='Leverantör AB')
    db.session.add(supplier)
    db.session.flush()

    si = SupplierInvoice(
        company_id=company.id,
        supplier_id=supplier.id,
        invoice_number='F-001',
        invoice_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
        total_amount=Decimal('5000.00'),
        status='paid',
        paid_at=datetime(2026, 2, 5, tzinfo=timezone.utc),
    )
    db.session.add(si)

    # Customer + paid invoice
    customer = Customer(company_id=company.id, name='Kund AB')
    db.session.add(customer)
    db.session.flush()

    ci = CustomerInvoice(
        company_id=company.id,
        customer_id=customer.id,
        invoice_number='K-001',
        invoice_date=date(2026, 1, 15),
        due_date=date(2026, 2, 15),
        total_amount=Decimal('10000.00'),
        status='paid',
        paid_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    db.session.add(ci)

    # Tax payment
    tp = TaxPayment(
        company_id=company.id,
        payment_type='vat',
        amount=Decimal('4000.00'),
        payment_date=date(2026, 2, 12),
        reference='OCR123',
    )
    db.session.add(tp)

    db.session.commit()
    return si, ci, tp


class TestGetAllPayments:
    def test_empty(self, db, company):
        payments, summary = get_all_payments(company.id)
        assert payments == []
        assert summary['total_in'] == 0
        assert summary['total_out'] == 0
        assert summary['net'] == 0

    def test_all_types_returned(self, db, company, payment_data):
        payments, summary = get_all_payments(company.id)
        assert len(payments) == 3
        types = {p['type'] for p in payments}
        assert types == {'supplier', 'customer', 'tax'}

    def test_directions(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id)
        by_type = {p['type']: p for p in payments}
        assert by_type['supplier']['direction'] == 'out'
        assert by_type['customer']['direction'] == 'in'
        assert by_type['tax']['direction'] == 'out'

    def test_summary_totals(self, db, company, payment_data):
        _, summary = get_all_payments(company.id)
        assert summary['total_in'] == 10000.0
        assert summary['total_out'] == 9000.0  # 5000 supplier + 4000 tax
        assert summary['net'] == 1000.0

    def test_sorted_by_date_descending(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id)
        dates = [p['date'] for p in payments]
        assert dates == sorted(dates, reverse=True)

    def test_descriptions(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id)
        by_type = {p['type']: p for p in payments}
        assert 'Leverantör AB' in by_type['supplier']['description']
        assert 'F-001' in by_type['supplier']['description']
        assert 'Kund AB' in by_type['customer']['description']
        assert 'K-001' in by_type['customer']['description']
        assert 'Moms' in by_type['tax']['description']
        assert 'OCR123' in by_type['tax']['description']


class TestTypeFilter:
    def test_filter_supplier(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id, payment_type='supplier')
        assert len(payments) == 1
        assert payments[0]['type'] == 'supplier'

    def test_filter_customer(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id, payment_type='customer')
        assert len(payments) == 1
        assert payments[0]['type'] == 'customer'

    def test_filter_tax(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id, payment_type='tax')
        assert len(payments) == 1
        assert payments[0]['type'] == 'tax'

    def test_summary_matches_filter(self, db, company, payment_data):
        _, summary = get_all_payments(company.id, payment_type='customer')
        assert summary['total_in'] == 10000.0
        assert summary['total_out'] == 0
        assert summary['net'] == 10000.0


class TestDateFilter:
    def test_from_date(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id, from_date=date(2026, 2, 10))
        # customer paid 2026-03-01, tax 2026-02-12 match; supplier paid 2026-02-05 excluded
        types = {p['type'] for p in payments}
        assert 'supplier' not in types
        assert 'customer' in types
        assert 'tax' in types

    def test_to_date(self, db, company, payment_data):
        payments, _ = get_all_payments(company.id, to_date=date(2026, 2, 10))
        # supplier paid 2026-02-05 matches; customer 2026-03-01 excluded; tax 2026-02-12 excluded
        types = {p['type'] for p in payments}
        assert 'supplier' in types
        assert 'customer' not in types
        assert 'tax' not in types

    def test_date_range(self, db, company, payment_data):
        payments, _ = get_all_payments(
            company.id, from_date=date(2026, 2, 1), to_date=date(2026, 2, 28)
        )
        # supplier 2026-02-05 and tax 2026-02-12 match; customer 2026-03-01 excluded
        assert len(payments) == 2
        types = {p['type'] for p in payments}
        assert types == {'supplier', 'tax'}


class TestCompanyIsolation:
    def test_other_company_not_included(self, db, company, payment_data):
        other = Company(name='OtherAB', org_number='1122334455', company_type='AB')
        db.session.add(other)
        db.session.flush()

        supplier = Supplier(company_id=other.id, name='Annan Leverantör')
        db.session.add(supplier)
        db.session.flush()

        si = SupplierInvoice(
            company_id=other.id, supplier_id=supplier.id,
            invoice_number='X-001', invoice_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), total_amount=Decimal('9999'),
            status='paid', paid_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        db.session.add(si)
        db.session.commit()

        payments, summary = get_all_payments(company.id)
        assert len(payments) == 3  # only original company's payments
        assert summary['total_out'] == 9000.0


class TestTaxPaymentLabels:
    def test_unknown_payment_type_uses_raw(self, db, company):
        tp = TaxPayment(
            company_id=company.id,
            payment_type='custom_type',
            amount=Decimal('100'),
            payment_date=date(2026, 6, 1),
        )
        db.session.add(tp)
        db.session.commit()

        payments, _ = get_all_payments(company.id, payment_type='tax')
        assert payments[0]['description'] == 'custom_type'

    def test_tax_without_reference(self, db, company):
        tp = TaxPayment(
            company_id=company.id,
            payment_type='vat',
            amount=Decimal('200'),
            payment_date=date(2026, 6, 1),
            reference=None,
        )
        db.session.add(tp)
        db.session.commit()

        payments, _ = get_all_payments(company.id, payment_type='tax')
        assert payments[0]['description'] == 'Moms'
        assert '(' not in payments[0]['description']
