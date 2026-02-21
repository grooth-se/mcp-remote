"""Tests for Phase 10F: Tax Planning Recommendations."""

import pytest
from datetime import date, datetime
from decimal import Decimal

from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.salary import SalaryRun
from app.models.governance import DividendDecision
from app.models.tax import TaxReturn
from app.services.tax_planning_service import (
    get_tax_planning_suggestions, get_group_tax_overview,
    IBB, SALARY_THRESHOLD,
)


def _setup_company(db, name='Plan AB', company_type='AB'):
    company = Company(name=name, org_number='556700-0001', company_type=company_type)
    db.session.add(company)
    db.session.commit()
    fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.commit()
    return company, fy


# ---- Service tests ----

class TestGetTaxPlanningSuggestions:
    def test_returns_structure(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        assert 'recommendations' in result
        assert 'company_type' in result
        assert result['company_type'] == 'AB'

    def test_ab_gets_salary_vs_dividend(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        areas = [r['area'] for r in result['recommendations']]
        assert 'salary_vs_dividend' in areas

    def test_hb_no_salary_vs_dividend(self, db):
        company, fy = _setup_company(db, company_type='HB')
        result = get_tax_planning_suggestions(company.id, fy.id)
        areas = [r['area'] for r in result['recommendations']]
        assert 'salary_vs_dividend' not in areas

    def test_includes_loss_carryforward(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        areas = [r['area'] for r in result['recommendations']]
        assert 'loss_carryforward' in areas

    def test_includes_asset_timing(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        areas = [r['area'] for r in result['recommendations']]
        assert 'asset_timing' in areas

    def test_ab_includes_group_structure(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        areas = [r['area'] for r in result['recommendations']]
        assert 'group_structure' in areas

    def test_invalid_company(self, db):
        result = get_tax_planning_suggestions(9999, 9999)
        assert result['recommendations'] == []
        assert result['company_type'] is None

    def test_ibb_in_result(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        assert result['ibb'] == float(IBB)


class TestSalaryVsDividend:
    def test_no_salary_red(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'salary_vs_dividend')
        assert rec['status'] == 'red'
        assert 'Ingen lön' in rec['summary']

    def test_partial_salary_yellow(self, db):
        company, fy = _setup_company(db)
        sr = SalaryRun(company_id=company.id, fiscal_year_id=fy.id, period_year=2025, period_month=1,
                       status='paid', total_gross=Decimal('50000'))
        db.session.add(sr)
        db.session.commit()
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'salary_vs_dividend')
        assert rec['status'] == 'yellow'
        assert 'Ytterligare' in rec['summary']

    def test_full_salary_green(self, db):
        company, fy = _setup_company(db)
        sr = SalaryRun(company_id=company.id, fiscal_year_id=fy.id, period_year=2025, period_month=1,
                       status='paid', total_gross=SALARY_THRESHOLD + Decimal('1'))
        db.session.add(sr)
        db.session.commit()
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'salary_vs_dividend')
        assert rec['status'] == 'green'
        assert 'uppfyller' in rec['summary']

    def test_includes_dividend_data(self, db):
        company, fy = _setup_company(db)
        div = DividendDecision(company_id=company.id, fiscal_year_id=fy.id,
                               decision_date=date(2025, 6, 1),
                               total_amount=Decimal('100000'), status='beslutad')
        db.session.add(div)
        db.session.commit()
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'salary_vs_dividend')
        assert rec['details']['total_dividends'] == 100000.0


class TestLossCarryforward:
    def test_no_returns(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'loss_carryforward')
        assert rec['status'] == 'green'
        assert rec['details']['available_deficit'] == 0

    def test_with_deficit(self, db):
        company, fy = _setup_company(db)
        tr = TaxReturn(company_id=company.id, fiscal_year_id=fy.id,
                       return_type='ink2', tax_year=2025,
                       taxable_income=Decimal('-100000'))
        db.session.add(tr)
        db.session.commit()
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'loss_carryforward')
        assert rec['status'] == 'yellow'
        assert rec['details']['available_deficit'] == 100000.0


class TestAssetTiming:
    def test_months_remaining(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'asset_timing')
        assert 'months_remaining' in rec['details']
        assert 'depreciation_pct' in rec['details']

    def test_has_status(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'asset_timing')
        assert rec['status'] in ('green', 'yellow', 'red')


class TestGroupStructure:
    def test_standalone_company(self, db):
        company, fy = _setup_company(db)
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'group_structure')
        assert rec['details']['in_group'] is False

    def test_high_dividend_yellow(self, db):
        company, fy = _setup_company(db)
        div = DividendDecision(company_id=company.id, fiscal_year_id=fy.id,
                               decision_date=date(2025, 6, 1),
                               total_amount=Decimal('250000'), status='beslutad')
        db.session.add(div)
        db.session.commit()
        result = get_tax_planning_suggestions(company.id, fy.id)
        rec = next(r for r in result['recommendations'] if r['area'] == 'group_structure')
        assert rec['status'] == 'yellow'
        assert 'holdingbolag' in rec['summary']


class TestGroupTaxOverview:
    def test_returns_list(self, db):
        _setup_company(db)
        overview = get_group_tax_overview()
        assert len(overview) >= 1

    def test_includes_company(self, db):
        company, fy = _setup_company(db)
        overview = get_group_tax_overview()
        names = [item['company'].name for item in overview]
        assert company.name in names


# ---- Route tests ----

class TestTaxPlanningRoute:
    def test_planning_no_company(self, logged_in_client, db):
        resp = logged_in_client.get('/tax/planning', follow_redirects=True)
        assert resp.status_code == 200

    def test_planning_renders(self, logged_in_client, db):
        company = Company(name='Plan AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/tax/planning')
        assert resp.status_code == 200
        assert 'Skatteplanering' in resp.get_data(as_text=True)

    def test_planning_group_renders(self, logged_in_client, db):
        resp = logged_in_client.get('/tax/planning/group')
        assert resp.status_code == 200
        assert 'Alla bolag' in resp.get_data(as_text=True)

    def test_planning_no_fy(self, logged_in_client, db):
        company = Company(name='Plan AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/tax/planning', follow_redirects=True)
        assert resp.status_code == 200
