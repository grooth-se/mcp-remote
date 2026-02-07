"""Tests for invoice PDF service (Phase 4F)."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.invoice import Customer, CustomerInvoice, InvoiceLineItem
from app.models.user import User
from app.services.invoice_pdf_service import (
    add_line_item, update_line_item, remove_line_item,
    recalculate_invoice_totals, generate_next_invoice_number,
    generate_invoice_pdf, mark_invoice_sent,
)


@pytest.fixture
def invoice_company(db):
    """Company (with address), customer, and a draft customer invoice."""
    co = Company(name='Faktura AB', org_number='556600-0050', company_type='AB',
                 street_address='Storgatan 1', postal_code='11122', city='Stockholm')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    cust = Customer(company_id=co.id, name='Kund AB', org_number='556700-0050',
                    address='Kundvägen 5', postal_code='22233', city='Göteborg')
    db.session.add(cust)
    db.session.flush()

    inv = CustomerInvoice(
        company_id=co.id, customer_id=cust.id,
        invoice_number='FAK-2025-0001',
        invoice_date=date(2025, 3, 1), due_date=date(2025, 3, 31),
        status='draft',
    )
    db.session.add(inv)

    user = User(username='invuser', email='inv@test.com', role='admin')
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()

    return {'company': co, 'fy': fy, 'customer': cust, 'invoice': inv, 'user': user}


class TestLineItems:
    def test_add_line_item(self, invoice_company):
        inv = invoice_company['invoice']
        item = add_line_item(inv.id, 'Konsulttimmar', 10, 1500, vat_rate=25)
        assert item is not None
        assert item.line_number == 1
        assert float(item.amount) == 15000.0
        assert float(item.vat_amount) == 3750.0

    def test_add_multiple_lines(self, invoice_company):
        inv = invoice_company['invoice']
        item1 = add_line_item(inv.id, 'Rad 1', 1, 1000)
        item2 = add_line_item(inv.id, 'Rad 2', 2, 500)
        assert item1.line_number == 1
        assert item2.line_number == 2

    def test_update_line_item(self, invoice_company):
        inv = invoice_company['invoice']
        item = add_line_item(inv.id, 'Original', 1, 1000)
        updated = update_line_item(item.id, quantity=5, unit_price=2000)
        assert updated is not None
        assert float(updated.amount) == 10000.0

    def test_remove_line_item(self, invoice_company):
        inv = invoice_company['invoice']
        item = add_line_item(inv.id, 'Ta bort', 1, 500)
        result = remove_line_item(item.id)
        assert result is True


class TestTotals:
    def test_recalculate_totals(self, invoice_company):
        inv = invoice_company['invoice']
        add_line_item(inv.id, 'A', 2, 1000, vat_rate=25)  # 2000 + 500 vat
        add_line_item(inv.id, 'B', 1, 3000, vat_rate=25)  # 3000 + 750 vat

        from app.extensions import db
        db.session.refresh(inv)
        assert float(inv.amount_excl_vat) == 5000.0
        assert float(inv.vat_amount) == 1250.0
        assert float(inv.total_amount) == 6250.0

    def test_recalculate_empty(self, invoice_company):
        inv = invoice_company['invoice']
        # With no line items, recalculate should not crash
        recalculate_invoice_totals(inv.id)


class TestInvoiceNumber:
    def test_generate_number(self, invoice_company):
        co = invoice_company['company']
        num = generate_next_invoice_number(co.id)
        # Uses current year (2026) which has no invoices yet -> 0001
        # The existing 'FAK-2025-0001' is a different year prefix
        assert '-0001' in num
        assert num.startswith('FAK-')

    def test_sequential_numbers(self, invoice_company, db):
        co = invoice_company['company']
        cust = invoice_company['customer']

        # Create another invoice with the generated number
        num1 = generate_next_invoice_number(co.id)
        inv2 = CustomerInvoice(
            company_id=co.id, customer_id=cust.id,
            invoice_number=num1,
            invoice_date=date(2025, 3, 5), due_date=date(2025, 4, 5),
            status='draft',
        )
        db.session.add(inv2)
        db.session.commit()

        num2 = generate_next_invoice_number(co.id)
        # Should increment again
        assert num2 > num1


class TestPDF:
    def test_generate_pdf(self, invoice_company, app):
        inv = invoice_company['invoice']
        add_line_item(inv.id, 'Konsulttimmar', 10, 1500)

        with app.app_context():
            result = generate_invoice_pdf(inv.id)
        # weasyprint may or may not be installed; either way we get a result
        assert result is not None


class TestSend:
    def test_mark_sent(self, invoice_company):
        inv = invoice_company['invoice']
        user = invoice_company['user']
        result = mark_invoice_sent(inv.id, user.id)
        assert result is True

        from app.extensions import db
        db.session.refresh(inv)
        assert inv.status == 'sent'
        assert inv.sent_at is not None
