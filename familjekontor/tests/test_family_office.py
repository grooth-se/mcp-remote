"""Tests for Family Office / Multi-Company Features (Phase 8)."""

import pytest
from datetime import date, timedelta

from app.models.user import User
from app.models.company import Company
from app.models.accounting import Account, FiscalYear, Verification, VerificationRow
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.tax import Deadline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def family_user(db):
    """User for family office tests."""
    user = User(username='family_admin', email='family@test.com', role='admin')
    user.set_password('testpass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def multi_company(db, family_user):
    """Create 2 companies with open FYs, accounts, and verifications."""
    # Company 1: AB
    co1 = Company(name='Familj AB', org_number='556100-0001', company_type='AB')
    db.session.add(co1)
    db.session.flush()

    fy1 = FiscalYear(company_id=co1.id, year=2025,
                     start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
                     status='open')
    db.session.add(fy1)
    db.session.flush()

    # Accounts for co1
    accts1 = {}
    for num, name, atype in [
        ('1930', 'Bankkonto', 'asset'),
        ('3000', 'Försäljning', 'revenue'),
        ('4000', 'Inköp', 'expense'),
        ('5000', 'Lokalkostnad', 'expense'),
        ('2080', 'Eget kapital', 'equity'),
    ]:
        a = Account(company_id=co1.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accts1[num] = a

    # Verification: revenue 100000 to bank
    v1 = Verification(company_id=co1.id, fiscal_year_id=fy1.id,
                      verification_number=1, verification_date=date(2025, 3, 15),
                      description='Försäljning mars')
    db.session.add(v1)
    db.session.flush()
    db.session.add(VerificationRow(verification_id=v1.id, account_id=accts1['1930'].id,
                                   debit=100000, credit=0))
    db.session.add(VerificationRow(verification_id=v1.id, account_id=accts1['3000'].id,
                                   debit=0, credit=100000))

    # Verification: expense 40000
    v2 = Verification(company_id=co1.id, fiscal_year_id=fy1.id,
                      verification_number=2, verification_date=date(2025, 3, 20),
                      description='Inköp mars')
    db.session.add(v2)
    db.session.flush()
    db.session.add(VerificationRow(verification_id=v2.id, account_id=accts1['4000'].id,
                                   debit=40000, credit=0))
    db.session.add(VerificationRow(verification_id=v2.id, account_id=accts1['1930'].id,
                                   debit=0, credit=40000))

    # Company 2: HB
    co2 = Company(name='Familj HB', org_number='916200-0002', company_type='HB')
    db.session.add(co2)
    db.session.flush()

    fy2 = FiscalYear(company_id=co2.id, year=2025,
                     start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
                     status='open')
    db.session.add(fy2)
    db.session.flush()

    accts2 = {}
    for num, name, atype in [
        ('1930', 'Bankkonto', 'asset'),
        ('3000', 'Försäljning', 'revenue'),
        ('4000', 'Inköp', 'expense'),
        ('2080', 'Eget kapital', 'equity'),
    ]:
        a = Account(company_id=co2.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accts2[num] = a

    # Verification: revenue 50000
    v3 = Verification(company_id=co2.id, fiscal_year_id=fy2.id,
                      verification_number=1, verification_date=date(2025, 4, 10),
                      description='Försäljning april')
    db.session.add(v3)
    db.session.flush()
    db.session.add(VerificationRow(verification_id=v3.id, account_id=accts2['1930'].id,
                                   debit=50000, credit=0))
    db.session.add(VerificationRow(verification_id=v3.id, account_id=accts2['3000'].id,
                                   debit=0, credit=50000))

    # Verification: expense 20000
    v4 = Verification(company_id=co2.id, fiscal_year_id=fy2.id,
                      verification_number=2, verification_date=date(2025, 4, 15),
                      description='Inköp april')
    db.session.add(v4)
    db.session.flush()
    db.session.add(VerificationRow(verification_id=v4.id, account_id=accts2['4000'].id,
                                   debit=20000, credit=0))
    db.session.add(VerificationRow(verification_id=v4.id, account_id=accts2['1930'].id,
                                   debit=0, credit=20000))

    db.session.commit()

    return {
        'co1': co1, 'co2': co2,
        'fy1': fy1, 'fy2': fy2,
        'accts1': accts1, 'accts2': accts2,
    }


@pytest.fixture
def family_client(app, family_user):
    """Logged-in client for family routes (no active_company_id needed)."""
    client = app.test_client()
    client.post('/login', data={
        'username': 'family_admin',
        'password': 'testpass123',
    }, follow_redirects=True)
    return client


# ---------------------------------------------------------------------------
# Service Tests — Dashboard (8A)
# ---------------------------------------------------------------------------

class TestFamilyDashboardService:
    def test_empty_no_companies(self, app, db):
        """No active companies → zeros."""
        with app.app_context():
            from app.services.family_service import get_family_dashboard_data
            data = get_family_dashboard_data()
            assert data['total_cash'] == 0.0
            assert data['total_revenue_ytd'] == 0.0
            assert data['total_expenses_ytd'] == 0.0
            assert data['company_count'] == 0
            assert data['per_company'] == []

    def test_single_company(self, app, db, multi_company):
        """Deactivate co2 → only co1 data."""
        with app.app_context():
            from app.services.family_service import get_family_dashboard_data
            co2 = db.session.get(Company, multi_company['co2'].id)
            co2.active = False
            db.session.commit()

            data = get_family_dashboard_data()
            assert data['company_count'] == 1
            assert data['per_company'][0]['company'].name == 'Familj AB'
            # Revenue should be 100000
            assert data['total_revenue_ytd'] > 0

    def test_multiple_companies_aggregation(self, app, db, multi_company):
        """Both companies active → aggregated totals."""
        with app.app_context():
            from app.services.family_service import get_family_dashboard_data
            data = get_family_dashboard_data()
            assert data['company_count'] == 2
            assert len(data['per_company']) == 2
            # Total revenue: 100000 + 50000 = 150000
            assert data['total_revenue_ytd'] == pytest.approx(150000, abs=1)
            # Total expenses: 40000 + 20000 = 60000
            assert data['total_expenses_ytd'] == pytest.approx(60000, abs=1)

    def test_revenue_trend(self, app, db, multi_company):
        """Revenue trend returns datasets per company."""
        with app.app_context():
            from app.services.family_service import get_family_revenue_trend
            data = get_family_revenue_trend()
            assert 'labels' in data
            assert 'datasets' in data
            assert 'totals' in data
            assert len(data['datasets']) == 2

    def test_health_indicators(self, app, db, multi_company):
        """Health indicators return per-company status."""
        with app.app_context():
            from app.services.family_service import get_family_health_indicators
            health = get_family_health_indicators()
            assert len(health) == 2
            for h in health:
                assert 'overall_status' in h
                assert h['overall_status'] in ('good', 'warning', 'danger')
                assert 'ratios' in h


# ---------------------------------------------------------------------------
# Service Tests — Cash Flow (8B)
# ---------------------------------------------------------------------------

class TestCrossCompanyCashflow:
    def test_empty(self, app, db):
        """No companies → empty."""
        with app.app_context():
            from app.services.family_service import get_cross_company_cashflow
            data = get_cross_company_cashflow()
            assert data['labels'] == []
            assert data['per_company'] == []

    def test_with_data(self, app, db, multi_company):
        """Returns per-company cash flow data."""
        with app.app_context():
            from app.services.family_service import get_cross_company_cashflow
            data = get_cross_company_cashflow()
            assert len(data['per_company']) == 2
            for pc in data['per_company']:
                assert 'company_name' in pc
                assert 'cash_flow' in pc
                assert 'balance' in pc

    def test_totals_sum_correctly(self, app, db, multi_company):
        """Totals are sum of per-company values."""
        with app.app_context():
            from app.services.family_service import get_cross_company_cashflow
            data = get_cross_company_cashflow()
            if data['labels']:
                for i in range(len(data['labels'])):
                    expected_cf = sum(
                        float(pc['cash_flow'][i]) if i < len(pc['cash_flow']) else 0
                        for pc in data['per_company']
                    )
                    assert data['totals']['cash_flow'][i] == pytest.approx(expected_cf, abs=0.01)


# ---------------------------------------------------------------------------
# Service Tests — Wealth (8C)
# ---------------------------------------------------------------------------

class TestFamilyWealthSummary:
    def test_basic_equity(self, app, db, multi_company):
        """Wealth summary includes equity from balance sheets."""
        with app.app_context():
            from app.services.family_service import get_family_wealth_summary
            data = get_family_wealth_summary()
            assert 'net_worth' in data
            assert 'allocation' in data
            assert 'per_company' in data
            assert len(data['per_company']) == 2

    def test_cash_aggregated(self, app, db, multi_company):
        """Cash balance is aggregated from KPI data."""
        with app.app_context():
            from app.services.family_service import get_family_wealth_summary
            data = get_family_wealth_summary()
            # co1: 100000 - 40000 = 60000 in bank, co2: 50000 - 20000 = 30000
            assert data['total_cash'] == pytest.approx(90000, abs=1)

    def test_asset_allocation_percentages(self, app, db, multi_company):
        """Allocation percentages sum to ~100%."""
        with app.app_context():
            from app.services.family_service import get_family_wealth_summary
            data = get_family_wealth_summary()
            alloc = data['allocation']
            total = alloc['kassa'] + alloc['värdepapper'] + alloc['fastigheter']
            if total > 0:
                assert total == pytest.approx(100.0, abs=1)

    def test_empty_wealth(self, app, db):
        """No companies → zeros."""
        with app.app_context():
            from app.services.family_service import get_family_wealth_summary
            data = get_family_wealth_summary()
            assert data['net_worth'] == 0.0
            assert data['total_cash'] == 0.0
            assert data['per_company'] == []


# ---------------------------------------------------------------------------
# Service Tests — Alerts (8D)
# ---------------------------------------------------------------------------

class TestCrossCompanyAlerts:
    def test_empty_alerts(self, app, db, family_user):
        """No notifications → empty list."""
        with app.app_context():
            from app.services.family_service import get_cross_company_alerts
            data = get_cross_company_alerts(family_user.id)
            assert data['total_unread'] == 0
            assert len(data['notifications']) == 0

    def test_deadlines_across_companies(self, app, db, multi_company):
        """Deadlines from different companies are merged."""
        with app.app_context():
            from app.services.family_service import get_upcoming_deadlines_all
            # Create deadlines
            today = date.today()
            d1 = Deadline(
                company_id=multi_company['co1'].id,
                deadline_type='vat', description='Moms Q1',
                due_date=today + timedelta(days=10), status='pending',
            )
            d2 = Deadline(
                company_id=multi_company['co2'].id,
                deadline_type='employer_tax', description='Arbetsgivaravgift',
                due_date=today - timedelta(days=5), status='pending',
            )
            db.session.add_all([d1, d2])
            db.session.commit()

            data = get_upcoming_deadlines_all()
            assert len(data['upcoming']) == 1
            assert data['upcoming'][0].description == 'Moms Q1'
            assert len(data['overdue']) == 1
            assert data['overdue'][0].description == 'Arbetsgivaravgift'

    def test_activity_feed(self, app, db, multi_company, family_user):
        """Activity feed returns recent audit entries."""
        with app.app_context():
            from app.services.family_service import get_activity_feed
            log1 = AuditLog(
                company_id=multi_company['co1'].id,
                user_id=family_user.id,
                action='create', entity_type='verification', entity_id=1,
            )
            log2 = AuditLog(
                company_id=multi_company['co2'].id,
                user_id=family_user.id,
                action='update', entity_type='invoice', entity_id=2,
            )
            db.session.add_all([log1, log2])
            db.session.commit()

            feed = get_activity_feed()
            assert len(feed) == 2
            company_names = {f['company_name'] for f in feed}
            assert 'Familj AB' in company_names
            assert 'Familj HB' in company_names


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestFamilyRoutes:
    def test_dashboard_page(self, app, db, family_client, multi_company):
        """Family dashboard loads."""
        resp = family_client.get('/family/')
        assert resp.status_code == 200
        assert 'Familjeöversikt' in resp.data.decode()

    def test_cashflow_page(self, app, db, family_client, multi_company):
        """Cash flow page loads."""
        resp = family_client.get('/family/cashflow')
        assert resp.status_code == 200
        assert 'Kassaflöde' in resp.data.decode()

    def test_wealth_page(self, app, db, family_client, multi_company):
        """Wealth page loads."""
        resp = family_client.get('/family/wealth')
        assert resp.status_code == 200
        assert 'rmögenhet' in resp.data.decode()

    def test_alerts_page(self, app, db, family_client, multi_company):
        """Alerts page loads."""
        resp = family_client.get('/family/alerts')
        assert resp.status_code == 200
        assert 'Notiser' in resp.data.decode()

    def test_api_revenue_trend(self, app, db, family_client, multi_company):
        """Revenue trend API returns JSON."""
        resp = family_client.get('/family/api/revenue-trend')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data
        assert 'datasets' in data

    def test_api_cash_position(self, app, db, family_client, multi_company):
        """Cash position API returns JSON."""
        resp = family_client.get('/family/api/cash-position')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data
        assert 'per_company' in data

    def test_api_cashflow_comparison(self, app, db, family_client, multi_company):
        """Cash flow comparison API returns JSON."""
        resp = family_client.get('/family/api/cashflow-comparison')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data
        assert 'totals' in data

    def test_unauthenticated_redirect(self, app, db):
        """Unauthenticated user redirected to login."""
        client = app.test_client()
        resp = client.get('/family/')
        assert resp.status_code == 302
        assert '/login' in resp.headers.get('Location', '')
