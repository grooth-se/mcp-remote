"""Tests for input validation hardening (Phase 5C)."""
from datetime import date
from decimal import Decimal

import pytest

from werkzeug.datastructures import MultiDict
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import SupplierInvoice, CustomerInvoice, Supplier, Customer
from app.models.bank import BankAccount, BankTransaction
from app.models.tax import Deadline


@pytest.fixture
def filter_setup(db, logged_in_client):
    """Company with various entities for filter testing."""
    co = Company(name='FilterCo', org_number='556600-0200', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    supplier = Supplier(company_id=co.id, name='TestLev')
    customer = Customer(company_id=co.id, name='TestKund')
    db.session.add_all([supplier, customer])
    db.session.flush()

    si = SupplierInvoice(company_id=co.id, supplier_id=supplier.id,
                         invoice_number='F-001', invoice_date=date(2025, 3, 1),
                         due_date=date(2025, 4, 1), amount_excl_vat=Decimal('1000'),
                         vat_amount=Decimal('250'), total_amount=Decimal('1250'),
                         status='pending')
    ci = CustomerInvoice(company_id=co.id, customer_id=customer.id,
                         invoice_number='KF-001', invoice_date=date(2025, 3, 1),
                         due_date=date(2025, 4, 1), amount_excl_vat=Decimal('2000'),
                         vat_amount=Decimal('500'), total_amount=Decimal('2500'),
                         status='draft')
    db.session.add_all([si, ci])
    db.session.flush()

    ba = BankAccount(company_id=co.id, bank_name='TestBank', account_number='1234',
                     currency='SEK')
    db.session.add(ba)
    db.session.flush()

    bt = BankTransaction(company_id=co.id, bank_account_id=ba.id,
                         transaction_date=date(2025, 3, 1), amount=Decimal('500'),
                         description='Test txn', status='unmatched')
    db.session.add(bt)
    db.session.flush()

    dl = Deadline(company_id=co.id, deadline_type='vat', description='Moms Q1',
                  due_date=date(2025, 4, 12), status='pending')
    db.session.add(dl)

    db.session.commit()

    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id

    return {'co': co, 'fy': fy}


class TestRouteFilterWhitelists:
    def test_supplier_invoice_invalid_status_ignored(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/invoices/supplier-invoices?status=INJECTED')
        assert response.status_code == 200

    def test_supplier_invoice_valid_status(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/invoices/supplier-invoices?status=pending')
        assert response.status_code == 200

    def test_customer_invoice_invalid_status_ignored(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/invoices/customer-invoices?status=INJECTED')
        assert response.status_code == 200

    def test_customer_invoice_valid_status(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/invoices/customer-invoices?status=draft')
        assert response.status_code == 200

    def test_bank_invalid_status_defaults(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/bank/reconciliation?status=INJECTED')
        assert response.status_code == 200

    def test_deadline_invalid_status_defaults(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/tax/deadlines/?status=INJECTED')
        assert response.status_code == 200

    def test_document_invalid_type_ignored(self, filter_setup, logged_in_client):
        response = logged_in_client.get('/documents/?doc_type=INJECTED')
        assert response.status_code == 200


class TestFormValidators:
    def _validate_field(self, app, form_cls, field_name, data, **form_kwargs):
        with app.test_request_context():
            form = form_cls(formdata=MultiDict(data), **form_kwargs)
            field = getattr(form, field_name)
            field.validate(form)
            return field.errors

    def test_payment_terms_rejects_negative(self, app):
        from app.forms.invoice import SupplierForm
        with app.test_request_context():
            form = SupplierForm(formdata=MultiDict({
                'name': 'Test', 'payment_terms': '-1',
            }))
            form.payment_terms.validate(form)
            assert len(form.payment_terms.errors) > 0

    def test_payment_terms_accepts_valid(self, app):
        from app.forms.invoice import SupplierForm
        with app.test_request_context():
            form = SupplierForm(formdata=MultiDict({
                'name': 'Test', 'payment_terms': '30',
            }))
            form.payment_terms.validate(form)
            assert len(form.payment_terms.errors) == 0

    def test_quantity_rejects_negative(self, app):
        from app.forms.invoice import InvoiceLineItemForm
        with app.test_request_context():
            form = InvoiceLineItemForm(formdata=MultiDict({
                'description': 'Test', 'quantity': '-5',
                'unit_price': '100', 'unit': 'st', 'vat_rate': '25',
            }))
            form.quantity.validate(form)
            assert len(form.quantity.errors) > 0

    def test_fiscal_year_rejects_invalid(self, app):
        from app.forms.company import FiscalYearForm
        with app.test_request_context():
            form = FiscalYearForm(formdata=MultiDict({
                'year': '1800', 'start_date': '2025-01-01',
                'end_date': '2025-12-31',
            }))
            form.year.validate(form)
            assert len(form.year.errors) > 0

    def test_fiscal_year_accepts_valid(self, app):
        from app.forms.company import FiscalYearForm
        with app.test_request_context():
            form = FiscalYearForm(formdata=MultiDict({
                'year': '2025', 'start_date': '2025-01-01',
                'end_date': '2025-12-31',
            }))
            form.year.validate(form)
            assert len(form.year.errors) == 0

    def test_theme_color_rejects_invalid(self, app):
        from app.forms.company import CompanyForm
        with app.test_request_context():
            form = CompanyForm(formdata=MultiDict({
                'name': 'Test', 'org_number': '5566001234',
                'theme_color': 'notahex',
            }))
            form.theme_color.validate(form)
            assert len(form.theme_color.errors) > 0

    def test_theme_color_accepts_valid(self, app):
        from app.forms.company import CompanyForm
        with app.test_request_context():
            form = CompanyForm(formdata=MultiDict({
                'name': 'Test', 'org_number': '5566001234',
                'theme_color': '#ff0000',
            }))
            form.theme_color.validate(form)
            assert len(form.theme_color.errors) == 0

    def test_theme_color_accepts_empty(self, app):
        from app.forms.company import CompanyForm
        with app.test_request_context():
            form = CompanyForm(formdata=MultiDict({
                'name': 'Test', 'org_number': '5566001234',
            }))
            form.theme_color.validate(form)
            assert len(form.theme_color.errors) == 0

    def test_employer_tax_year_rejects_invalid(self, app):
        from app.forms.tax import EmployerTaxPeriodForm
        with app.test_request_context():
            form = EmployerTaxPeriodForm(formdata=MultiDict({
                'year': '1900',
            }))
            form.year.validate(form)
            assert len(form.year.errors) > 0

    def test_recurring_payment_terms_rejects_negative(self, app):
        from app.forms.recurring_invoice import RecurringInvoiceTemplateForm
        with app.test_request_context():
            form = RecurringInvoiceTemplateForm(formdata=MultiDict({
                'name': 'Test', 'payment_terms': '-10',
                'interval': 'monthly', 'start_date': '2025-01-01',
            }))
            form.payment_terms.validate(form)
            assert len(form.payment_terms.errors) > 0
