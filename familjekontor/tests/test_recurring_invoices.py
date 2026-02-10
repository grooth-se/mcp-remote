"""Tests for recurring invoices (Phase 4K)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.invoice import Customer, CustomerInvoice, InvoiceLineItem
from app.models.recurring_invoice import RecurringInvoiceTemplate, RecurringLineItem
from app.models.user import User
from app.services.recurring_invoice_service import (
    get_due_templates, get_due_count, advance_next_date,
    generate_invoice_from_template, generate_all_due,
)


@pytest.fixture
def recurring_setup(db):
    """Company, customer, fiscal year, and user for recurring invoice tests."""
    co = Company(name='RecAB', org_number='5566001122', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2026, start_date=date(2026, 1, 1),
                    end_date=date(2026, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    cust = Customer(company_id=co.id, name='Kund Nordic AB', org_number='5577001122',
                    address='Nordvägen 1', postal_code='11100', city='Stockholm')
    db.session.add(cust)
    db.session.flush()

    user = User(username='recuser', email='rec@test.com', role='admin')
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()

    return {'company': co, 'fy': fy, 'customer': cust, 'user': user}


@pytest.fixture
def template_with_lines(db, recurring_setup):
    """Create a recurring template with 2 line items, next_date = today."""
    co = recurring_setup['company']
    cust = recurring_setup['customer']

    t = RecurringInvoiceTemplate(
        company_id=co.id,
        customer_id=cust.id,
        name='Månadsavgift',
        currency='SEK',
        vat_type='standard',
        interval='monthly',
        payment_terms=30,
        start_date=date.today(),
        next_date=date.today(),
    )
    db.session.add(t)
    db.session.flush()

    li1 = RecurringLineItem(
        template_id=t.id, line_number=1,
        description='Konsulttjänster', quantity=Decimal('10'),
        unit='tim', unit_price=Decimal('1500'), vat_rate=Decimal('25'),
    )
    li2 = RecurringLineItem(
        template_id=t.id, line_number=2,
        description='Reseersättning', quantity=Decimal('1'),
        unit='st', unit_price=Decimal('2000'), vat_rate=Decimal('25'),
    )
    db.session.add_all([li1, li2])
    db.session.commit()
    return t


class TestModel:
    def test_create_template(self, db, recurring_setup):
        co = recurring_setup['company']
        cust = recurring_setup['customer']

        t = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=cust.id,
            name='Test Mall', interval='monthly',
            start_date=date(2026, 3, 1), next_date=date(2026, 3, 1),
        )
        db.session.add(t)
        db.session.commit()

        assert t.id is not None
        assert t.active is True
        assert t.invoices_generated == 0
        assert t.currency == 'SEK'

    def test_create_line_item(self, db, recurring_setup):
        co = recurring_setup['company']
        cust = recurring_setup['customer']

        t = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=cust.id,
            name='Med rader', interval='quarterly',
            start_date=date(2026, 1, 1), next_date=date(2026, 1, 1),
        )
        db.session.add(t)
        db.session.flush()

        li = RecurringLineItem(
            template_id=t.id, line_number=1,
            description='Licens', quantity=Decimal('1'),
            unit_price=Decimal('5000'), vat_rate=Decimal('25'),
        )
        db.session.add(li)
        db.session.commit()

        assert len(t.line_items) == 1
        assert t.line_items[0].description == 'Licens'

    def test_cascade_delete(self, db, template_with_lines):
        t = template_with_lines
        tid = t.id
        assert RecurringLineItem.query.filter_by(template_id=tid).count() == 2

        db.session.delete(t)
        db.session.commit()
        assert RecurringLineItem.query.filter_by(template_id=tid).count() == 0


class TestDateAdvancement:
    def test_monthly(self):
        result = advance_next_date(date(2026, 1, 15), 'monthly')
        assert result == date(2026, 2, 15)

    def test_monthly_year_boundary(self):
        result = advance_next_date(date(2026, 12, 1), 'monthly')
        assert result == date(2027, 1, 1)

    def test_monthly_end_of_month(self):
        # Jan 31 → Feb 28 (clamp)
        result = advance_next_date(date(2026, 1, 31), 'monthly')
        assert result == date(2026, 2, 28)

    def test_quarterly(self):
        result = advance_next_date(date(2026, 1, 1), 'quarterly')
        assert result == date(2026, 4, 1)

    def test_quarterly_year_boundary(self):
        result = advance_next_date(date(2026, 11, 1), 'quarterly')
        assert result == date(2027, 2, 1)

    def test_yearly(self):
        result = advance_next_date(date(2026, 3, 15), 'yearly')
        assert result == date(2027, 3, 15)

    def test_leap_year(self):
        # Feb 29 in leap year → Feb 28 in non-leap year (yearly)
        result = advance_next_date(date(2024, 2, 29), 'yearly')
        assert result == date(2025, 2, 28)


class TestDueTemplates:
    def test_due_count(self, db, template_with_lines):
        co_id = template_with_lines.company_id
        assert get_due_count(co_id) == 1

    def test_due_count_future(self, db, recurring_setup):
        co = recurring_setup['company']
        cust = recurring_setup['customer']

        # Template with next_date in the future → not due
        t = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=cust.id,
            name='Framtida', interval='monthly',
            start_date=date.today() + timedelta(days=30),
            next_date=date.today() + timedelta(days=30),
        )
        db.session.add(t)
        db.session.commit()
        assert get_due_count(co.id) == 0

    def test_due_count_inactive(self, db, template_with_lines):
        t = template_with_lines
        t.active = False
        db.session.commit()
        assert get_due_count(t.company_id) == 0

    def test_due_count_past_end_date(self, db, recurring_setup):
        co = recurring_setup['company']
        cust = recurring_setup['customer']

        t = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=cust.id,
            name='Avslutad', interval='monthly',
            start_date=date(2025, 1, 1), next_date=date.today(),
            end_date=date.today() - timedelta(days=1),
        )
        db.session.add(t)
        db.session.commit()
        assert get_due_count(co.id) == 0

    def test_due_templates_returns_list(self, db, template_with_lines):
        co_id = template_with_lines.company_id
        templates = get_due_templates(co_id)
        assert len(templates) == 1
        assert templates[0].name == 'Månadsavgift'


class TestGeneration:
    def test_generate_invoice(self, db, template_with_lines, recurring_setup):
        t = template_with_lines
        original_next = t.next_date

        invoice = generate_invoice_from_template(t.id)

        assert invoice is not None
        assert invoice.status == 'draft'
        assert invoice.customer_id == recurring_setup['customer'].id
        assert invoice.company_id == recurring_setup['company'].id
        assert invoice.currency == 'SEK'
        assert invoice.invoice_date == original_next

    def test_generates_invoice_number(self, db, template_with_lines):
        invoice = generate_invoice_from_template(template_with_lines.id)
        assert invoice.invoice_number is not None
        assert 'REC-' in invoice.invoice_number or '-' in invoice.invoice_number

    def test_copies_line_items(self, db, template_with_lines):
        invoice = generate_invoice_from_template(template_with_lines.id)
        items = InvoiceLineItem.query.filter_by(customer_invoice_id=invoice.id).all()
        assert len(items) == 2
        assert items[0].description == 'Konsulttjänster'
        assert items[1].description == 'Reseersättning'

    def test_calculates_totals(self, db, template_with_lines):
        invoice = generate_invoice_from_template(template_with_lines.id)

        from app.extensions import db as _db
        _db.session.refresh(invoice)

        # Line 1: 10 * 1500 = 15000, vat = 3750
        # Line 2: 1 * 2000 = 2000, vat = 500
        # Total excl = 17000, vat = 4250, total = 21250
        assert float(invoice.amount_excl_vat) == 17000.0
        assert float(invoice.vat_amount) == 4250.0
        assert float(invoice.total_amount) == 21250.0

    def test_advances_next_date(self, db, template_with_lines):
        t = template_with_lines
        original_next = t.next_date

        generate_invoice_from_template(t.id)

        from app.extensions import db as _db
        _db.session.refresh(t)

        expected = advance_next_date(original_next, 'monthly')
        assert t.next_date == expected

    def test_increments_counter(self, db, template_with_lines):
        t = template_with_lines
        assert t.invoices_generated == 0

        generate_invoice_from_template(t.id)

        from app.extensions import db as _db
        _db.session.refresh(t)
        assert t.invoices_generated == 1

    def test_sets_due_date(self, db, template_with_lines):
        t = template_with_lines
        invoice = generate_invoice_from_template(t.id)
        expected_due = t.start_date + timedelta(days=30)
        assert invoice.due_date == expected_due

    def test_generate_all_due(self, db, recurring_setup):
        co = recurring_setup['company']
        cust = recurring_setup['customer']

        # Create 2 due templates
        for i in range(2):
            t = RecurringInvoiceTemplate(
                company_id=co.id, customer_id=cust.id,
                name=f'Mall {i+1}', interval='monthly',
                start_date=date.today(), next_date=date.today(),
            )
            db.session.add(t)
            db.session.flush()
            li = RecurringLineItem(
                template_id=t.id, line_number=1,
                description=f'Rad {i+1}', quantity=Decimal('1'),
                unit_price=Decimal('1000'), vat_rate=Decimal('25'),
            )
            db.session.add(li)
        db.session.commit()

        count = generate_all_due(co.id)
        assert count == 2

        # Templates should have advanced
        templates = RecurringInvoiceTemplate.query.filter_by(company_id=co.id).all()
        for t in templates:
            assert t.next_date > date.today()
            assert t.invoices_generated == 1


class TestForeignCurrency:
    def test_foreign_currency_template(self, db, recurring_setup):
        co = recurring_setup['company']
        cust = recurring_setup['customer']

        t = RecurringInvoiceTemplate(
            company_id=co.id, customer_id=cust.id,
            name='EUR Mall', currency='EUR',
            vat_type='reverse_charge', interval='monthly',
            start_date=date.today(), next_date=date.today(),
            payment_terms=30,
        )
        db.session.add(t)
        db.session.flush()

        li = RecurringLineItem(
            template_id=t.id, line_number=1,
            description='Consulting', quantity=Decimal('1'),
            unit_price=Decimal('5000'), vat_rate=Decimal('0'),
        )
        db.session.add(li)
        db.session.commit()

        invoice = generate_invoice_from_template(t.id)
        assert invoice.currency == 'EUR'
        assert invoice.vat_type == 'reverse_charge'


class TestRoutes:
    def test_recurring_list_requires_login(self, client):
        resp = client.get('/invoices/recurring/')
        assert resp.status_code in (302, 308)

    def test_recurring_list_authenticated(self, logged_in_client, db):
        co = Company(name='RouteTestAB', org_number='5566009999', company_type='AB')
        db.session.add(co)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/invoices/recurring/')
        assert resp.status_code == 200
        assert 'Återkommande fakturor' in resp.data.decode()

    def test_generate_all_route(self, logged_in_client, db):
        co = Company(name='GenTestAB', org_number='5566008888', company_type='AB')
        db.session.add(co)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/invoices/recurring/generate-all', follow_redirects=True)
        assert resp.status_code == 200
