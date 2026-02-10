"""Tests for currency routes and FX invoice handling."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.exchange_rate import ExchangeRate
from app.models.bank import BankAccount
from app.services.exchange_rate_service import save_rate_to_db
from app.services.accounting_service import create_verification
from app.utils.currency import calculate_fx_gain_loss, SUPPORTED_CURRENCIES


# === Currency utility tests ===

class TestCurrencyUtils:
    def test_supported_currencies_include_all(self):
        assert 'SEK' in SUPPORTED_CURRENCIES
        assert 'EUR' in SUPPORTED_CURRENCIES
        assert 'USD' in SUPPORTED_CURRENCIES
        assert 'NOK' in SUPPORTED_CURRENCIES
        assert 'DKK' in SUPPORTED_CURRENCIES
        assert 'GBP' in SUPPORTED_CURRENCIES

    def test_fx_gain_loss_zero(self):
        assert calculate_fx_gain_loss(Decimal('1000'), Decimal('1000')) == Decimal('0')

    def test_fx_loss(self):
        # Paid more SEK than booked
        result = calculate_fx_gain_loss(Decimal('11230'), Decimal('11500'))
        assert result == Decimal('270')
        assert result > 0  # positive = loss

    def test_fx_gain(self):
        # Paid less SEK than booked
        result = calculate_fx_gain_loss(Decimal('11230'), Decimal('11000'))
        assert result == Decimal('-230')
        assert result < 0  # negative = gain


# === Fixtures ===

@pytest.fixture
def setup_company(db):
    """Create company with FY and accounts for testing."""
    company = Company(name='TestAB', org_number='5566778899', company_type='AB')
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(
        company_id=company.id, year=2026,
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
    )
    db.session.add(fy)
    db.session.flush()

    accounts = {}
    for num, name, atype in [
        ('1510', 'Kundfordringar', 'asset'),
        ('1930', 'Företagskonto/checkkonto', 'asset'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('2640', 'Ingående moms', 'liability'),
        ('3000', 'Försäljning', 'revenue'),
        ('3960', 'Valutakursvinster', 'revenue'),
        ('4000', 'Inköp varor', 'expense'),
        ('6991', 'Valutakursförluster', 'expense'),
    ]:
        acct = Account(company_id=company.id, account_number=num, name=name, account_type=atype)
        db.session.add(acct)
        accounts[num] = acct

    db.session.flush()

    bank = BankAccount(
        company_id=company.id, bank_name='SEB',
        account_number='12345', ledger_account='1930',
    )
    db.session.add(bank)
    db.session.commit()

    return company, fy, accounts


# === Supplier invoice FX tests ===

class TestSupplierInvoiceFX:
    def test_eur_supplier_invoice_creates_sek_verification(self, db, logged_in_client, setup_company):
        company, fy, accounts = setup_company

        # Pre-populate exchange rate
        save_rate_to_db('EUR', date(2026, 2, 1), Decimal('11.23'), Decimal('0.089'), 'manual')

        supplier = Supplier(company_id=company.id, name='EU Supplier', default_account='4000')
        db.session.add(supplier)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post('/invoices/supplier-invoices/new', data={
            'supplier_id': supplier.id,
            'invoice_number': 'EUR-001',
            'invoice_date': '2026-02-01',
            'due_date': '2026-03-01',
            'amount_excl_vat': '1000.00',
            'vat_amount': '0.00',
            'total_amount': '1000.00',
            'currency': 'EUR',
            'exchange_rate': '11.230000',
        }, follow_redirects=True)

        assert resp.status_code == 200

        invoice = SupplierInvoice.query.filter_by(invoice_number='EUR-001').first()
        assert invoice is not None
        assert invoice.currency == 'EUR'
        assert invoice.exchange_rate == Decimal('11.230000')
        assert invoice.amount_sek == Decimal('11230.00')

        # Verification should be in SEK
        if invoice.verification_id:
            ver = db.session.get(Verification, invoice.verification_id)
            assert ver is not None
            # Debit side (expense) should be in SEK
            expense_row = next(r for r in ver.rows if r.account_id == accounts['4000'].id)
            assert expense_row.debit == Decimal('11230.00')
            # Foreign amount metadata
            assert expense_row.currency == 'EUR'
            assert expense_row.foreign_amount_debit == Decimal('1000.00')

    def test_sek_supplier_invoice_unchanged(self, db, logged_in_client, setup_company):
        company, fy, accounts = setup_company
        supplier = Supplier(company_id=company.id, name='Svensk Lev', default_account='4000')
        db.session.add(supplier)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post('/invoices/supplier-invoices/new', data={
            'supplier_id': supplier.id,
            'invoice_number': 'SEK-001',
            'invoice_date': '2026-02-01',
            'due_date': '2026-03-01',
            'amount_excl_vat': '8000.00',
            'vat_amount': '2000.00',
            'total_amount': '10000.00',
            'currency': 'SEK',
            'exchange_rate': '1.000000',
        }, follow_redirects=True)

        assert resp.status_code == 200
        invoice = SupplierInvoice.query.filter_by(invoice_number='SEK-001').first()
        assert invoice is not None
        assert invoice.amount_sek == Decimal('10000.00')

        if invoice.verification_id:
            ver = db.session.get(Verification, invoice.verification_id)
            expense_row = next(r for r in ver.rows if r.account_id == accounts['4000'].id)
            assert expense_row.currency is None  # No FX metadata for SEK


class TestSupplierPaymentFX:
    def test_fx_loss_on_payment(self, db, logged_in_client, setup_company):
        """EUR invoice booked at 11.23, paid when rate is 11.50 → loss of 270 SEK."""
        company, fy, accounts = setup_company

        save_rate_to_db('EUR', date(2026, 2, 1), Decimal('11.23'), Decimal('0.089'), 'manual')

        supplier = Supplier(company_id=company.id, name='EU Supplier', default_account='4000')
        db.session.add(supplier)
        db.session.flush()

        invoice = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='EUR-PAY-001', invoice_date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            amount_excl_vat=Decimal('1000'), vat_amount=Decimal('0'),
            total_amount=Decimal('1000'), currency='EUR',
            exchange_rate=Decimal('11.23'), amount_sek=Decimal('11230.00'),
            status='approved',
        )
        db.session.add(invoice)
        db.session.commit()

        # Set up payment-date rate (higher = loss)
        save_rate_to_db('EUR', date.today(), Decimal('11.50'), Decimal('0.087'), 'manual')

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post(
            f'/invoices/supplier-invoices/{invoice.id}/pay',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        invoice = db.session.get(SupplierInvoice, invoice.id)
        assert invoice.status == 'paid'
        assert invoice.payment_verification_id is not None

        ver = db.session.get(Verification, invoice.payment_verification_id)
        # Should have 3 rows: payable debit, bank credit, FX loss debit
        assert len(ver.rows) == 3

        fx_row = next(r for r in ver.rows if r.account_id == accounts['6991'].id)
        assert fx_row.debit == Decimal('270.00')

    def test_fx_gain_on_payment(self, db, logged_in_client, setup_company):
        """EUR invoice booked at 11.50, paid when rate is 11.23 → gain of 270 SEK."""
        company, fy, accounts = setup_company

        supplier = Supplier(company_id=company.id, name='EU Supplier', default_account='4000')
        db.session.add(supplier)
        db.session.flush()

        invoice = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='EUR-PAY-002', invoice_date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            amount_excl_vat=Decimal('1000'), vat_amount=Decimal('0'),
            total_amount=Decimal('1000'), currency='EUR',
            exchange_rate=Decimal('11.50'), amount_sek=Decimal('11500.00'),
            status='approved',
        )
        db.session.add(invoice)
        db.session.commit()

        # Lower rate at payment = gain
        save_rate_to_db('EUR', date.today(), Decimal('11.23'), Decimal('0.089'), 'manual')

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post(
            f'/invoices/supplier-invoices/{invoice.id}/pay',
            follow_redirects=True,
        )

        invoice = db.session.get(SupplierInvoice, invoice.id)
        ver = db.session.get(Verification, invoice.payment_verification_id)
        assert len(ver.rows) == 3

        fx_row = next(r for r in ver.rows if r.account_id == accounts['3960'].id)
        assert fx_row.credit == Decimal('270.00')

    def test_sek_payment_no_fx_row(self, db, logged_in_client, setup_company):
        """SEK invoice payment should have 2 rows, no FX."""
        company, fy, accounts = setup_company

        supplier = Supplier(company_id=company.id, name='Svensk Lev', default_account='4000')
        db.session.add(supplier)
        db.session.flush()

        invoice = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='SEK-PAY-001', invoice_date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            amount_excl_vat=Decimal('8000'), vat_amount=Decimal('2000'),
            total_amount=Decimal('10000'), currency='SEK',
            exchange_rate=Decimal('1.0'), amount_sek=Decimal('10000.00'),
            status='approved',
        )
        db.session.add(invoice)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post(
            f'/invoices/supplier-invoices/{invoice.id}/pay',
            follow_redirects=True,
        )

        invoice = db.session.get(SupplierInvoice, invoice.id)
        ver = db.session.get(Verification, invoice.payment_verification_id)
        assert len(ver.rows) == 2  # No FX row


# === Customer invoice FX tests ===

class TestCustomerPaymentFX:
    def test_customer_fx_gain(self, db, logged_in_client, setup_company):
        """EUR customer invoice booked at 11.23, received at 11.50 → gain (received more SEK)."""
        company, fy, accounts = setup_company

        customer = Customer(company_id=company.id, name='EU Customer', default_currency='EUR')
        db.session.add(customer)
        db.session.flush()

        invoice = CustomerInvoice(
            company_id=company.id, customer_id=customer.id,
            invoice_number='CINV-001', invoice_date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            amount_excl_vat=Decimal('1000'), vat_amount=Decimal('0'),
            total_amount=Decimal('1000'), currency='EUR',
            exchange_rate=Decimal('11.23'), amount_sek=Decimal('11230.00'),
            status='sent',
        )
        db.session.add(invoice)
        db.session.commit()

        # Higher rate at payment = gain for customer invoice
        save_rate_to_db('EUR', date.today(), Decimal('11.50'), Decimal('0.087'), 'manual')

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post(
            f'/invoices/customer-invoices/{invoice.id}/mark-paid',
            follow_redirects=True,
        )

        invoice = db.session.get(CustomerInvoice, invoice.id)
        ver = db.session.get(Verification, invoice.payment_verification_id)
        assert len(ver.rows) == 3

        fx_row = next(r for r in ver.rows if r.account_id == accounts['3960'].id)
        assert fx_row.credit == Decimal('270.00')

    def test_customer_fx_loss(self, db, logged_in_client, setup_company):
        """EUR customer invoice booked at 11.50, received at 11.23 → loss."""
        company, fy, accounts = setup_company

        customer = Customer(company_id=company.id, name='EU Customer', default_currency='EUR')
        db.session.add(customer)
        db.session.flush()

        invoice = CustomerInvoice(
            company_id=company.id, customer_id=customer.id,
            invoice_number='CINV-002', invoice_date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            amount_excl_vat=Decimal('1000'), vat_amount=Decimal('0'),
            total_amount=Decimal('1000'), currency='EUR',
            exchange_rate=Decimal('11.50'), amount_sek=Decimal('11500.00'),
            status='sent',
        )
        db.session.add(invoice)
        db.session.commit()

        save_rate_to_db('EUR', date.today(), Decimal('11.23'), Decimal('0.089'), 'manual')

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post(
            f'/invoices/customer-invoices/{invoice.id}/mark-paid',
            follow_redirects=True,
        )

        invoice = db.session.get(CustomerInvoice, invoice.id)
        ver = db.session.get(Verification, invoice.payment_verification_id)
        assert len(ver.rows) == 3

        fx_row = next(r for r in ver.rows if r.account_id == accounts['6991'].id)
        assert fx_row.debit == Decimal('270.00')


# === Currency route tests ===

class TestCurrencyRoutes:
    def test_rates_page(self, db, logged_in_client):
        resp = logged_in_client.get('/currency/rates')
        assert resp.status_code == 200
        assert 'Växelkurser' in resp.data.decode()

    def test_manual_rate_entry(self, db, logged_in_client):
        resp = logged_in_client.post('/currency/rates/new', data={
            'currency_code': 'EUR',
            'rate_date': '2026-02-01',
            'rate': '11.230000',
        }, follow_redirects=True)
        assert resp.status_code == 200

        er = ExchangeRate.query.filter_by(currency_code='EUR', rate_date=date(2026, 2, 1)).first()
        assert er is not None
        assert er.rate == Decimal('11.230000')
        assert er.source == 'manual'

    def test_api_rate_endpoint(self, db, logged_in_client):
        save_rate_to_db('EUR', date(2026, 2, 1), Decimal('11.23'), Decimal('0.089'), 'manual')

        resp = logged_in_client.get('/currency/api/rate/EUR/2026-02-01')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['rate'] == '11.230000'

    def test_api_rate_not_found(self, db, logged_in_client):
        with patch('app.routes.currency.get_rate', side_effect=ValueError('Ingen kurs')):
            resp = logged_in_client.get('/currency/api/rate/GBP/2020-01-01')
            assert resp.status_code == 404
