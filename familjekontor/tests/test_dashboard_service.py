"""Tests for dashboard analytics service (Phase 4A)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Customer, CustomerInvoice
from app.services.dashboard_service import (
    get_multi_company_overview, get_kpi_data, get_revenue_expense_trend,
    get_cash_flow_data, get_invoice_aging, get_fiscal_year_progress,
    get_salary_overview,
)


@pytest.fixture
def dashboard_company(db):
    """Company with FY, accounts, and verifications across 2 months."""
    co = Company(name='Dashboard AB', org_number='556600-0001', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    revenue = Account(company_id=co.id, account_number='3010',
                      name='Försäljning', account_type='revenue')
    expense = Account(company_id=co.id, account_number='5010',
                      name='Lokalhyra', account_type='expense')
    cash = Account(company_id=co.id, account_number='1930',
                   name='Företagskonto', account_type='asset')
    db.session.add_all([revenue, expense, cash])
    db.session.flush()

    # Jan verification: 100k revenue
    v1 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=1, verification_date=date(2025, 1, 15),
                      description='Jan försäljning')
    db.session.add(v1)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v1.id, account_id=cash.id,
                        debit=Decimal('100000'), credit=Decimal('0')),
        VerificationRow(verification_id=v1.id, account_id=revenue.id,
                        debit=Decimal('0'), credit=Decimal('100000')),
    ])

    # Feb verification: 50k expense
    v2 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=2, verification_date=date(2025, 2, 10),
                      description='Feb hyra')
    db.session.add(v2)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v2.id, account_id=expense.id,
                        debit=Decimal('50000'), credit=Decimal('0')),
        VerificationRow(verification_id=v2.id, account_id=cash.id,
                        debit=Decimal('0'), credit=Decimal('50000')),
    ])

    db.session.commit()
    return {'company': co, 'fy': fy, 'revenue': revenue, 'expense': expense, 'cash': cash}


class TestMultiCompany:
    def test_overview_returns_companies(self, dashboard_company):
        overview = get_multi_company_overview()
        assert len(overview) >= 1
        names = [o['company'].name for o in overview]
        assert 'Dashboard AB' in names

    def test_overview_empty(self, db):
        overview = get_multi_company_overview()
        assert isinstance(overview, list)


class TestKPI:
    def test_kpi_with_data(self, dashboard_company):
        co = dashboard_company['company']
        fy = dashboard_company['fy']
        kpi = get_kpi_data(co.id, fy.id)
        assert kpi is not None
        assert kpi['revenue'] == 100000.0
        assert kpi['expenses'] == 50000.0
        assert kpi['cash_balance'] == 50000.0

    def test_kpi_no_verifications(self, db):
        co = Company(name='Tom AB', org_number='556600-0099', company_type='AB')
        db.session.add(co)
        db.session.flush()
        fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        kpi = get_kpi_data(co.id, fy.id)
        assert kpi['revenue'] == 0
        assert kpi['expenses'] == 0


class TestTrends:
    def test_revenue_expense_trend(self, dashboard_company):
        co = dashboard_company['company']
        fy = dashboard_company['fy']
        data = get_revenue_expense_trend(co.id, fy.id)
        assert len(data['labels']) == 12
        assert data['revenue'][0] == 100000.0  # Jan
        assert data['expenses'][1] == 50000.0  # Feb

    def test_cash_flow_data(self, dashboard_company):
        co = dashboard_company['company']
        fy = dashboard_company['fy']
        data = get_cash_flow_data(co.id, fy.id)
        assert len(data['labels']) == 12
        assert data['cash_flow'][0] == 100000.0  # Jan: +100k
        assert data['cash_flow'][1] == -50000.0  # Feb: -50k
        assert data['balance'][1] == 50000.0  # running balance


class TestAging:
    def test_aging_buckets(self, dashboard_company, db):
        co = dashboard_company['company']
        cust = Customer(company_id=co.id, name='Kund AB', org_number='556700-0001')
        db.session.add(cust)
        db.session.flush()
        inv = CustomerInvoice(
            company_id=co.id, customer_id=cust.id, invoice_number='F-2025-001',
            invoice_date=date(2025, 1, 1), due_date=date(2024, 12, 1),
            total_amount=Decimal('10000'), status='overdue',
        )
        db.session.add(inv)
        db.session.commit()

        aging = get_invoice_aging(co.id)
        assert aging['90_plus'] == 10000.0

    def test_aging_empty(self, dashboard_company):
        co = dashboard_company['company']
        aging = get_invoice_aging(co.id)
        total = sum(aging.values())
        assert total == 0


class TestProgress:
    def test_fiscal_year_progress(self, dashboard_company):
        co = dashboard_company['company']
        fy = dashboard_company['fy']
        progress = get_fiscal_year_progress(co.id, fy.id)
        assert progress is not None
        assert 'progress_pct' in progress
        assert 'days_remaining' in progress


class TestSalary:
    def test_salary_overview_none(self, dashboard_company):
        co = dashboard_company['company']
        result = get_salary_overview(co.id)
        assert result is None
