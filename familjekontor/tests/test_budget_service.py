"""Tests for budget & forecast service (Phase 4C)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.user import User
from app.services.budget_service import (
    get_budget_grid, save_budget_grid, get_variance_analysis,
    get_forecast, copy_budget_from_year, export_budget_to_excel,
    export_variance_to_excel,
)


@pytest.fixture
def budget_company(db):
    """Company with FY, expense/revenue accounts, verifications for actuals."""
    co = Company(name='Budget AB', org_number='556600-0020', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    fy2 = FiscalYear(company_id=co.id, year=2026, start_date=date(2026, 1, 1),
                     end_date=date(2026, 12, 31), status='open')
    db.session.add_all([fy, fy2])
    db.session.flush()

    revenue = Account(company_id=co.id, account_number='3010',
                      name='Försäljning', account_type='revenue')
    expense = Account(company_id=co.id, account_number='5010',
                      name='Lokalhyra', account_type='expense')
    cash = Account(company_id=co.id, account_number='1930',
                   name='Företagskonto', account_type='asset')
    db.session.add_all([revenue, expense, cash])
    db.session.flush()

    # Jan actual: revenue 80k, expense 30k
    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 1, 15),
                     description='Jan')
    db.session.add(v)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v.id, account_id=cash.id,
                        debit=Decimal('80000'), credit=Decimal('0')),
        VerificationRow(verification_id=v.id, account_id=revenue.id,
                        debit=Decimal('0'), credit=Decimal('80000')),
    ])
    v2 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=2, verification_date=date(2025, 1, 20),
                      description='Jan hyra')
    db.session.add(v2)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v2.id, account_id=expense.id,
                        debit=Decimal('30000'), credit=Decimal('0')),
        VerificationRow(verification_id=v2.id, account_id=cash.id,
                        debit=Decimal('0'), credit=Decimal('30000')),
    ])

    user = User(username='budgetuser', email='budget@test.com', role='admin')
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()

    return {'company': co, 'fy': fy, 'fy2': fy2, 'revenue': revenue,
            'expense': expense, 'user': user}


class TestBudgetGrid:
    def test_get_empty_grid(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        grid = get_budget_grid(co.id, fy.id)
        # Should contain P&L accounts (3xxx-7xxx) with zero budgets
        assert isinstance(grid, dict)
        for acc_id, data in grid.items():
            assert data['total'] == 0

    def test_save_and_get_grid(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        revenue = budget_company['revenue']

        grid_data = {str(revenue.id): {'1': '100000', '2': '90000'}}
        count = save_budget_grid(co.id, fy.id, grid_data, budget_company['user'].id)
        assert count == 2

        grid = get_budget_grid(co.id, fy.id)
        assert grid[revenue.id]['months'][1] == 100000.0
        assert grid[revenue.id]['months'][2] == 90000.0

    def test_save_updates_existing(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        revenue = budget_company['revenue']

        grid_data = {str(revenue.id): {'1': '100000'}}
        save_budget_grid(co.id, fy.id, grid_data, budget_company['user'].id)

        # Update to new value
        grid_data2 = {str(revenue.id): {'1': '120000'}}
        count = save_budget_grid(co.id, fy.id, grid_data2, budget_company['user'].id)
        assert count == 1

        grid = get_budget_grid(co.id, fy.id)
        assert grid[revenue.id]['months'][1] == 120000.0


class TestVariance:
    def test_variance_with_budget(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        expense = budget_company['expense']

        grid_data = {str(expense.id): {'1': '25000'}}
        save_budget_grid(co.id, fy.id, grid_data, budget_company['user'].id)

        variance = get_variance_analysis(co.id, fy.id)
        # Find expense entry
        exp_row = [v for v in variance if v['number'] == '5010']
        assert len(exp_row) == 1
        # Actual expense in Jan was 30000, budget 25000 -> variance +5000
        assert exp_row[0]['months'][0]['budget'] == 25000.0
        assert exp_row[0]['months'][0]['actual'] == 30000.0

    def test_variance_no_budget(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        variance = get_variance_analysis(co.id, fy.id)
        assert isinstance(variance, list)


class TestForecast:
    def test_forecast_data(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        forecast = get_forecast(co.id, fy.id)
        assert forecast is not None
        assert len(forecast['labels']) == 12
        assert 'actual' in forecast
        assert 'forecast' in forecast


class TestCopy:
    def test_copy_budget(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        fy2 = budget_company['fy2']
        revenue = budget_company['revenue']

        grid_data = {str(revenue.id): {'1': '100000', '6': '150000'}}
        save_budget_grid(co.id, fy.id, grid_data, budget_company['user'].id)

        count = copy_budget_from_year(co.id, fy.id, fy2.id, budget_company['user'].id)
        assert count == 2

        grid = get_budget_grid(co.id, fy2.id)
        assert grid[revenue.id]['months'][1] == 100000.0
        assert grid[revenue.id]['months'][6] == 150000.0

    def test_copy_empty(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        fy2 = budget_company['fy2']
        count = copy_budget_from_year(co.id, fy.id, fy2.id, budget_company['user'].id)
        assert count == 0


class TestExport:
    def test_export_budget_excel(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        output = export_budget_to_excel(co.id, fy.id, co.name)
        assert output is not None
        data = output.read()
        assert len(data) > 0

    def test_export_variance_excel(self, budget_company):
        co = budget_company['company']
        fy = budget_company['fy']
        output = export_variance_to_excel(co.id, fy.id, co.name)
        assert output is not None
        data = output.read()
        assert len(data) > 0
