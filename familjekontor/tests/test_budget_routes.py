"""Tests for budget routes (Phase 4C)."""
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account


@pytest.fixture
def budget_route_setup(db, logged_in_client):
    """Company with FY, accounts, and active session."""
    co = Company(name='BudgetRoute AB', org_number='556600-0120', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    fy2 = FiscalYear(company_id=co.id, year=2026, start_date=date(2026, 1, 1),
                     end_date=date(2026, 12, 31), status='open')
    db.session.add_all([fy, fy2])
    db.session.flush()

    rev = Account(company_id=co.id, account_number='3010',
                  name='Försäljning', account_type='revenue')
    exp = Account(company_id=co.id, account_number='5010',
                  name='Lokalhyra', account_type='expense')
    db.session.add_all([rev, exp])
    db.session.commit()

    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id

    return {'company': co, 'fy': fy, 'fy2': fy2, 'revenue': rev, 'expense': exp}


def test_index_page(budget_route_setup, logged_in_client):
    response = logged_in_client.get('/budget/')
    assert response.status_code == 200


def test_grid_page(budget_route_setup, logged_in_client):
    fy = budget_route_setup['fy']
    response = logged_in_client.get(f'/budget/grid?fiscal_year_id={fy.id}')
    assert response.status_code == 200


def test_api_save_grid(budget_route_setup, logged_in_client):
    fy = budget_route_setup['fy']
    rev = budget_route_setup['revenue']

    response = logged_in_client.post('/budget/api/save-grid',
        data=json.dumps({
            'fiscal_year_id': fy.id,
            'grid': {str(rev.id): {'1': '100000'}},
        }),
        content_type='application/json',
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_variance_page(budget_route_setup, logged_in_client):
    fy = budget_route_setup['fy']
    response = logged_in_client.get(f'/budget/variance?fiscal_year_id={fy.id}')
    assert response.status_code == 200


def test_forecast_page(budget_route_setup, logged_in_client):
    fy = budget_route_setup['fy']
    response = logged_in_client.get(f'/budget/forecast?fiscal_year_id={fy.id}')
    assert response.status_code == 200


def test_copy_budget(budget_route_setup, logged_in_client):
    fy = budget_route_setup['fy']
    fy2 = budget_route_setup['fy2']
    response = logged_in_client.post('/budget/copy', data={
        'source_fiscal_year_id': fy.id,
        'target_fiscal_year_id': fy2.id,
    }, follow_redirects=True)
    assert response.status_code == 200


def test_redirect_without_company(logged_in_client):
    with logged_in_client.session_transaction() as sess:
        sess.pop('active_company_id', None)
    response = logged_in_client.get('/budget/')
    assert response.status_code == 302
