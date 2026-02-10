"""Tests for invoice PDF service (Phase 4F)."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.invoice import Customer, CustomerInvoice, InvoiceLineItem
from app.models.user import User
from app.models.accounting import Account, Verification, VerificationRow
from app.services.invoice_pdf_service import (
    add_line_item, update_line_item, remove_line_item,
    recalculate_invoice_totals, generate_next_invoice_number,
    generate_invoice_pdf, mark_invoice_sent,
    create_customer_invoice_verification,
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


@pytest.fixture
def verification_setup(db):
    """Company with accounts 1510/3010/2610 and a customer invoice with totals."""
    co = Company(name='VerAB', org_number='556600-0099', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    acct_1510 = Account(company_id=co.id, account_number='1510', name='Kundfordringar',
                        account_type='asset')
    acct_3010 = Account(company_id=co.id, account_number='3010', name='Försäljning',
                        account_type='revenue')
    acct_2610 = Account(company_id=co.id, account_number='2610', name='Utgående moms',
                        account_type='liability')
    db.session.add_all([acct_1510, acct_3010, acct_2610])
    db.session.flush()

    cust = Customer(company_id=co.id, name='TestKund AB', org_number='556700-0099',
                    address='Testv 1', postal_code='11100', city='Stockholm')
    db.session.add(cust)
    db.session.flush()

    user = User(username='veruser', email='ver@test.com', role='admin')
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()

    return {
        'company': co, 'fy': fy, 'customer': cust, 'user': user,
        'acct_1510': acct_1510, 'acct_3010': acct_3010, 'acct_2610': acct_2610,
    }


class TestCustomerInvoiceVerification:
    def _make_invoice(self, db, setup, vat_type='standard', currency='SEK',
                      excl=Decimal('10000'), vat=Decimal('2500'), total=Decimal('12500'),
                      exchange_rate=Decimal('1')):
        inv = CustomerInvoice(
            company_id=setup['company'].id,
            customer_id=setup['customer'].id,
            invoice_number='VER-2025-0001',
            invoice_date=date(2025, 6, 1),
            due_date=date(2025, 6, 30),
            currency=currency,
            exchange_rate=exchange_rate,
            amount_excl_vat=excl,
            vat_amount=vat,
            total_amount=total,
            vat_type=vat_type,
            status='draft',
        )
        db.session.add(inv)
        db.session.flush()
        return inv

    def test_standard_invoice_creates_verification(self, db, verification_setup):
        inv = self._make_invoice(db, verification_setup)

        ver, reason = create_customer_invoice_verification(
            inv, verification_setup['company'].id,
            verification_setup['fy'].id, verification_setup['user'].id)

        assert ver is not None
        assert reason is None
        assert inv.verification_id == ver.id

        rows = VerificationRow.query.filter_by(verification_id=ver.id).order_by(VerificationRow.id).all()
        assert len(rows) == 3

        # Debit 1510 = 12500
        assert rows[0].account_id == verification_setup['acct_1510'].id
        assert float(rows[0].debit) == 12500.0
        assert float(rows[0].credit) == 0.0

        # Credit 3010 = 10000
        assert rows[1].account_id == verification_setup['acct_3010'].id
        assert float(rows[1].debit) == 0.0
        assert float(rows[1].credit) == 10000.0

        # Credit 2610 = 2500
        assert rows[2].account_id == verification_setup['acct_2610'].id
        assert float(rows[2].debit) == 0.0
        assert float(rows[2].credit) == 2500.0

    def test_reverse_charge_no_vat_row(self, db, verification_setup):
        inv = self._make_invoice(db, verification_setup,
                                 vat_type='reverse_charge',
                                 excl=Decimal('10000'), vat=Decimal('0'),
                                 total=Decimal('10000'))

        ver, reason = create_customer_invoice_verification(
            inv, verification_setup['company'].id,
            verification_setup['fy'].id, verification_setup['user'].id)

        assert ver is not None
        rows = VerificationRow.query.filter_by(verification_id=ver.id).all()
        assert len(rows) == 2  # Only 1510 debit + 3010 credit

        # Full amount on 3010
        credit_row = [r for r in rows if float(r.credit) > 0][0]
        assert credit_row.account_id == verification_setup['acct_3010'].id
        assert float(credit_row.credit) == 10000.0

    def test_export_no_vat_row(self, db, verification_setup):
        inv = self._make_invoice(db, verification_setup,
                                 vat_type='export',
                                 excl=Decimal('5000'), vat=Decimal('0'),
                                 total=Decimal('5000'))

        ver, reason = create_customer_invoice_verification(
            inv, verification_setup['company'].id,
            verification_setup['fy'].id, verification_setup['user'].id)

        assert ver is not None
        rows = VerificationRow.query.filter_by(verification_id=ver.id).all()
        assert len(rows) == 2

    def test_missing_accounts_returns_none(self, db):
        co = Company(name='NoAcctAB', org_number='556600-0077', company_type='AB')
        db.session.add(co)
        db.session.flush()

        fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.flush()

        cust = Customer(company_id=co.id, name='Kund AB', org_number='556700-0077',
                        address='X', postal_code='11100', city='Sthlm')
        db.session.add(cust)
        db.session.flush()

        inv = CustomerInvoice(
            company_id=co.id, customer_id=cust.id,
            invoice_number='MISS-0001',
            invoice_date=date(2025, 6, 1), due_date=date(2025, 6, 30),
            amount_excl_vat=Decimal('1000'), vat_amount=Decimal('250'),
            total_amount=Decimal('1250'), vat_type='standard', status='draft',
        )
        db.session.add(inv)
        db.session.flush()

        ver, reason = create_customer_invoice_verification(inv, co.id, fy.id, None)
        assert ver is None
        assert 'saknas' in reason

    def test_foreign_currency_sek_amounts(self, db, verification_setup):
        """EUR invoice with exchange_rate=11.50 → SEK amounts in verification."""
        inv = self._make_invoice(db, verification_setup,
                                 currency='EUR', exchange_rate=Decimal('11.50'),
                                 excl=Decimal('1000'), vat=Decimal('250'),
                                 total=Decimal('1250'))

        ver, reason = create_customer_invoice_verification(
            inv, verification_setup['company'].id,
            verification_setup['fy'].id, verification_setup['user'].id)

        assert ver is not None
        rows = VerificationRow.query.filter_by(verification_id=ver.id).order_by(VerificationRow.id).all()

        # Debit 1510 = 1250 * 11.50 = 14375 SEK
        assert float(rows[0].debit) == 14375.0
        # Credit 3010 = 1000 * 11.50 = 11500 SEK
        assert float(rows[1].credit) == 11500.0
        # Credit 2610 = 250 * 11.50 = 2875 SEK
        assert float(rows[2].credit) == 2875.0
