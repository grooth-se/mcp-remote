"""Integration tests for tax routes."""

from datetime import date
from decimal import Decimal
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.tax import VATReport, Deadline, TaxPayment
from app.services.tax_service import seed_deadlines_for_year, create_vat_report


@pytest.fixture
def setup_company(db):
    """Create a company with fiscal year and VAT accounts."""
    from app.models.user import User
    user = User(username='taxuser', email='tax@test.com', role='admin')
    user.set_password('testpass')
    db.session.add(user)

    company = Company(
        name='SkattAB',
        org_number='5566001122',
        company_type='AB',
        vat_period='quarterly',
    )
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(
        company_id=company.id,
        year=2026,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.flush()

    # VAT accounts
    for num, name, atype in [
        ('2610', 'Utgående moms 25%', 'liability'),
        ('2640', 'Ingående moms', 'asset'),
    ]:
        db.session.add(Account(
            company_id=company.id, account_number=num, name=name, account_type=atype
        ))

    db.session.commit()
    return company, fy, user


@pytest.fixture
def tax_client(client, setup_company):
    """Client logged in with active company set."""
    company, fy, user = setup_company
    client.post('/login', data={'username': 'taxuser', 'password': 'testpass'},
                follow_redirects=True)
    with client.session_transaction() as sess:
        sess['active_company_id'] = company.id
    return client, company, fy


class TestTaxOverview:
    def test_index(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/')
        assert resp.status_code == 200
        assert 'Skatt' in resp.data.decode()

    def test_index_redirects_without_company(self, client, setup_company):
        _, _, user = setup_company
        client.post('/login', data={'username': 'taxuser', 'password': 'testpass'},
                    follow_redirects=True)
        # Don't set active_company_id
        with client.session_transaction() as sess:
            sess.pop('active_company_id', None)
        resp = client.get('/tax/', follow_redirects=False)
        assert resp.status_code == 302


class TestVATRoutes:
    def test_vat_index(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/vat/')
        assert resp.status_code == 200
        assert 'Momsrapporter' in resp.data.decode()

    def test_vat_generate_get(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/vat/generate')
        assert resp.status_code == 200
        assert 'Q1 2026' in resp.data.decode()

    def test_vat_generate_post(self, db, tax_client):
        client, company, fy = tax_client
        resp = client.post('/tax/vat/generate', data={'period': '0'},
                           follow_redirects=True)
        assert resp.status_code == 200
        assert VATReport.query.filter_by(company_id=company.id).count() == 1


class TestDeadlineRoutes:
    def test_deadlines_index(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/deadlines/')
        assert resp.status_code == 200

    def test_seed_deadlines(self, db, tax_client):
        client, company, fy = tax_client
        resp = client.post('/tax/deadlines/seed', data={'year': 2026},
                           follow_redirects=True)
        assert resp.status_code == 200
        assert Deadline.query.filter_by(company_id=company.id).count() > 0

    def test_complete_deadline(self, db, tax_client):
        client, company, fy = tax_client
        deadlines = seed_deadlines_for_year(company.id, 2026)
        dl = deadlines[0]
        resp = client.post(f'/tax/deadlines/{dl.id}/complete',
                           follow_redirects=True)
        assert resp.status_code == 200
        updated = db.session.get(Deadline, dl.id)
        assert updated.status == 'completed'


class TestPaymentRoutes:
    def test_payments_index(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/payments/')
        assert resp.status_code == 200

    def test_payment_new_get(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/payments/new')
        assert resp.status_code == 200

    def test_payment_new_post(self, db, tax_client):
        client, company, fy = tax_client
        resp = client.post('/tax/payments/new', data={
            'payment_type': 'vat',
            'amount': '4000.00',
            'payment_date': '2026-05-12',
            'reference': 'OCR123',
            'deadline_id': '0',
            'notes': '',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert TaxPayment.query.filter_by(company_id=company.id).count() == 1

    def test_payments_summary(self, tax_client):
        client, company, fy = tax_client
        resp = client.get('/tax/payments/summary?year=2026')
        assert resp.status_code == 200
