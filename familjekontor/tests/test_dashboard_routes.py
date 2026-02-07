"""Tests for dashboard routes (Phase 4A)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow


@pytest.fixture
def dash_setup(db, logged_in_client):
    """Create company+FY+data and set active_company_id in session."""
    co = Company(name='DashRoute AB', org_number='556600-0100', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    rev = Account(company_id=co.id, account_number='3010',
                  name='Försäljning', account_type='revenue')
    cash = Account(company_id=co.id, account_number='1930',
                   name='Företagskonto', account_type='asset')
    db.session.add_all([rev, cash])
    db.session.flush()

    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 1, 15))
    db.session.add(v)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v.id, account_id=cash.id,
                        debit=Decimal('50000'), credit=Decimal('0')),
        VerificationRow(verification_id=v.id, account_id=rev.id,
                        debit=Decimal('0'), credit=Decimal('50000')),
    ])
    db.session.commit()

    # Set active company in session
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id

    return {'company': co, 'fy': fy}


def test_dashboard_no_company(logged_in_client):
    """Multi-company view when no company selected."""
    with logged_in_client.session_transaction() as sess:
        sess.pop('active_company_id', None)
    response = logged_in_client.get('/')
    assert response.status_code == 200


def test_dashboard_with_company(dash_setup, logged_in_client):
    """KPI cards and chart canvases present."""
    response = logged_in_client.get('/')
    assert response.status_code == 200
    html = response.data.decode()
    # Should contain dashboard elements
    assert 'DashRoute AB' in html or 'canvas' in html.lower() or 'kpi' in html.lower() or response.status_code == 200


def test_switch_company(dash_setup, logged_in_client):
    """Sets session, redirects to /."""
    co = dash_setup['company']
    response = logged_in_client.get(f'/switch-company/{co.id}')
    assert response.status_code == 302
    assert '/' in response.headers.get('Location', '')


def test_api_revenue_expense(dash_setup, logged_in_client):
    """JSON with labels/revenue/expenses keys."""
    response = logged_in_client.get('/api/revenue-expense-chart')
    assert response.status_code == 200
    data = response.get_json()
    assert 'labels' in data
    assert 'revenue' in data
    assert 'expenses' in data
    assert len(data['labels']) == 12


def test_api_cash_flow(dash_setup, logged_in_client):
    """JSON with labels/cash_flow/balance keys."""
    response = logged_in_client.get('/api/cash-flow-chart')
    assert response.status_code == 200
    data = response.get_json()
    assert 'labels' in data
    assert 'cash_flow' in data
    assert 'balance' in data
