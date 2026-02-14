"""Tests for financial ratio analysis (Phase 6A)."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.ratio_service import (
    get_financial_ratios, get_multi_year_ratios, get_ratio_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ratio_company(db):
    """Company with P&L and BS data for ratio tests."""
    co = Company(name='Ratio AB', org_number='556600-0080', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    # Create accounts
    accounts = {}
    acct_defs = [
        ('1220', 'Inventarier', 'asset'),
        ('1400', 'Varulager', 'asset'),
        ('1510', 'Kundfordringar', 'asset'),
        ('1930', 'Företagskonto', 'asset'),
        ('2081', 'Aktiekapital', 'equity'),
        ('2310', 'Banklån', 'liability'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('3010', 'Försäljning', 'revenue'),
        ('4010', 'Inköp', 'expense'),
        ('5010', 'Lokalhyra', 'expense'),
        ('7010', 'Löner', 'expense'),
        ('7810', 'Avskrivningar', 'expense'),
        ('8310', 'Ränteintäkter', 'revenue'),
        ('8410', 'Räntekostnader', 'expense'),
    ]
    for num, name, atype in acct_defs:
        a = Account(company_id=co.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accounts[num] = a

    # Create balanced verifications
    # V1: Revenue 200000 (credit 3010, debit 1930)
    v1 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=1, verification_date=date(2025, 3, 1))
    db.session.add(v1)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v1.id, account_id=accounts['1930'].id,
                        debit=Decimal('200000'), credit=Decimal('0')),
        VerificationRow(verification_id=v1.id, account_id=accounts['3010'].id,
                        debit=Decimal('0'), credit=Decimal('200000')),
    ])

    # V2: COGS 60000 (debit 4010, credit 1930)
    v2 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=2, verification_date=date(2025, 3, 15))
    db.session.add(v2)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v2.id, account_id=accounts['4010'].id,
                        debit=Decimal('60000'), credit=Decimal('0')),
        VerificationRow(verification_id=v2.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('60000')),
    ])

    # V3: External costs 20000 (debit 5010, credit 1930)
    v3 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=3, verification_date=date(2025, 4, 1))
    db.session.add(v3)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v3.id, account_id=accounts['5010'].id,
                        debit=Decimal('20000'), credit=Decimal('0')),
        VerificationRow(verification_id=v3.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('20000')),
    ])

    # V4: Salary 30000 (debit 7010, credit 1930)
    v4 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=4, verification_date=date(2025, 5, 1))
    db.session.add(v4)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v4.id, account_id=accounts['7010'].id,
                        debit=Decimal('30000'), credit=Decimal('0')),
        VerificationRow(verification_id=v4.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('30000')),
    ])

    # V5: Interest expense 5000 (debit 8410, credit 1930)
    v5 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=5, verification_date=date(2025, 6, 1))
    db.session.add(v5)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v5.id, account_id=accounts['8410'].id,
                        debit=Decimal('5000'), credit=Decimal('0')),
        VerificationRow(verification_id=v5.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('5000')),
    ])

    # V6: Interest income 2000 (debit 1930, credit 8310)
    v6 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=6, verification_date=date(2025, 6, 15))
    db.session.add(v6)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v6.id, account_id=accounts['1930'].id,
                        debit=Decimal('2000'), credit=Decimal('0')),
        VerificationRow(verification_id=v6.id, account_id=accounts['8310'].id,
                        debit=Decimal('0'), credit=Decimal('2000')),
    ])

    # V7: Inventory 40000 (debit 1400, credit 1930)
    v7 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=7, verification_date=date(2025, 1, 10))
    db.session.add(v7)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v7.id, account_id=accounts['1400'].id,
                        debit=Decimal('40000'), credit=Decimal('0')),
        VerificationRow(verification_id=v7.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('40000')),
    ])

    # V8: Fixed asset 100000 (debit 1220, credit 1930)
    v8 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=8, verification_date=date(2025, 1, 15))
    db.session.add(v8)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v8.id, account_id=accounts['1220'].id,
                        debit=Decimal('100000'), credit=Decimal('0')),
        VerificationRow(verification_id=v8.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('100000')),
    ])

    # V9: Equity 500000 (debit 1930, credit 2081)
    v9 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=9, verification_date=date(2025, 1, 1))
    db.session.add(v9)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v9.id, account_id=accounts['1930'].id,
                        debit=Decimal('500000'), credit=Decimal('0')),
        VerificationRow(verification_id=v9.id, account_id=accounts['2081'].id,
                        debit=Decimal('0'), credit=Decimal('500000')),
    ])

    # V10: Bank loan 200000 (debit 1930, credit 2310)
    v10 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                       verification_number=10, verification_date=date(2025, 1, 1))
    db.session.add(v10)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v10.id, account_id=accounts['1930'].id,
                        debit=Decimal('200000'), credit=Decimal('0')),
        VerificationRow(verification_id=v10.id, account_id=accounts['2310'].id,
                        debit=Decimal('0'), credit=Decimal('200000')),
    ])

    # V11: Accounts receivable 30000 (debit 1510, credit 1930)
    v11 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                       verification_number=11, verification_date=date(2025, 7, 1))
    db.session.add(v11)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v11.id, account_id=accounts['1510'].id,
                        debit=Decimal('30000'), credit=Decimal('0')),
        VerificationRow(verification_id=v11.id, account_id=accounts['1930'].id,
                        debit=Decimal('0'), credit=Decimal('30000')),
    ])

    # V12: Accounts payable 25000 (credit 2440, debit 5010) — another external cost
    v12 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                       verification_number=12, verification_date=date(2025, 8, 1))
    db.session.add(v12)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v12.id, account_id=accounts['5010'].id,
                        debit=Decimal('25000'), credit=Decimal('0')),
        VerificationRow(verification_id=v12.id, account_id=accounts['2440'].id,
                        debit=Decimal('0'), credit=Decimal('25000')),
    ])

    db.session.commit()

    # Summary of expected values:
    # Revenue (3010): 200000
    # COGS (4010): 60000
    # External (5010): 20000 + 25000 = 45000
    # Personnel (7010): 30000
    # Fin income (8310): 2000
    # Fin costs (8410): 5000
    # gross_profit = 200000 - 60000 = 140000
    # operating_result = 140000 - 45000 - 30000 = 65000
    # result_before_tax = 65000 + 2000 - 5000 = 62000
    # Cash (1930): 500000+200000+200000+2000-60000-20000-30000-5000-40000-100000-30000 = 617000
    # Fixed assets (1220): 100000
    # Inventory (1400): 40000
    # Receivables (1510): 30000
    # Current assets = 40000+30000+617000 = 687000
    # Total assets = 100000 + 687000 = 787000
    # Equity (2081): 500000
    # LT debt (2310): 200000
    # ST debt (2440): 25000
    # Total E+L = 500000+200000+25000 = 725000

    return {'company': co, 'fy': fy, 'accounts': accounts}


# ---------------------------------------------------------------------------
# Profitability Tests
# ---------------------------------------------------------------------------

class TestProfitabilityRatios:
    def test_gross_margin(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # gross_profit=140000, revenue=200000 → 70%
            assert ratios['profitability']['gross_margin']['value'] == 70.0

    def test_operating_margin(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # operating_result=65000, revenue=200000 → 32.5%
            assert ratios['profitability']['operating_margin']['value'] == 32.5

    def test_net_margin(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # result_before_tax=62000, revenue=200000 → 31.0%
            assert ratios['profitability']['net_margin']['value'] == 31.0

    def test_roe(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # result_before_tax=62000, equity=500000 → 12.4%
            assert ratios['profitability']['roe']['value'] == 12.4

    def test_roa(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # result_before_tax=62000, total_assets=787000 → 7.9%
            assert ratios['profitability']['roa']['value'] == 7.9


# ---------------------------------------------------------------------------
# Liquidity Tests
# ---------------------------------------------------------------------------

class TestLiquidityRatios:
    def test_current_ratio(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # current_assets=687000, st_liabilities=25000 → 27.48
            val = ratios['liquidity']['current_ratio']['value']
            assert val == 27.48

    def test_quick_ratio_excludes_inventory(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # (687000-40000)/25000 = 25.88
            val = ratios['liquidity']['quick_ratio']['value']
            assert val == 25.88

    def test_cash_ratio(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # cash_1930=617000, st=25000 → 24.68
            val = ratios['liquidity']['cash_ratio']['value']
            assert val == 24.68

    def test_working_capital(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # 687000 - 25000 = 662000
            assert ratios['liquidity']['working_capital']['value'] == 662000.0


# ---------------------------------------------------------------------------
# Solvency Tests
# ---------------------------------------------------------------------------

class TestSolvencyRatios:
    def test_debt_to_equity(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # total_debt=225000, equity=500000 → 0.45
            assert ratios['solvency']['debt_to_equity']['value'] == 0.45

    def test_equity_ratio(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # equity=500000, total_assets=787000 → 63.5%
            assert ratios['solvency']['equity_ratio']['value'] == 63.5

    def test_interest_coverage(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # operating_result=65000, fin_costs=5000 → 13.0
            assert ratios['solvency']['interest_coverage']['value'] == 13.0


# ---------------------------------------------------------------------------
# Efficiency Tests
# ---------------------------------------------------------------------------

class TestEfficiencyRatios:
    def test_asset_turnover(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            ratios = get_financial_ratios(co.id, fy.id)
            # revenue=200000, total_assets=787000 → 0.25
            assert ratios['efficiency']['asset_turnover']['value'] == 0.25


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_data_returns_nones(self, app, db):
        """Empty FY returns None for division-based ratios."""
        with app.app_context():
            co = Company(name='Empty AB', org_number='556600-0099', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.commit()

            ratios = get_financial_ratios(co.id, fy.id)
            assert ratios['profitability']['gross_margin']['value'] is None
            assert ratios['liquidity']['current_ratio']['value'] is None
            assert ratios['solvency']['debt_to_equity']['value'] is None

    def test_no_revenue_margin_is_none(self, app, db):
        """No revenue → margin ratios are None."""
        with app.app_context():
            co = Company(name='NoRev AB', org_number='556600-0098', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.flush()
            # Add only an expense
            exp = Account(company_id=co.id, account_number='5010', name='Hyra', account_type='expense')
            cash = Account(company_id=co.id, account_number='1930', name='Bank', account_type='asset')
            db.session.add_all([exp, cash])
            db.session.flush()
            v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                             verification_number=1, verification_date=date(2025, 3, 1))
            db.session.add(v)
            db.session.flush()
            db.session.add_all([
                VerificationRow(verification_id=v.id, account_id=exp.id,
                                debit=Decimal('10000'), credit=Decimal('0')),
                VerificationRow(verification_id=v.id, account_id=cash.id,
                                debit=Decimal('0'), credit=Decimal('10000')),
            ])
            db.session.commit()

            ratios = get_financial_ratios(co.id, fy.id)
            assert ratios['profitability']['gross_margin']['value'] is None
            assert ratios['profitability']['net_margin']['value'] is None

    def test_no_fin_costs_interest_coverage_none(self, app, db):
        """No financial costs → interest coverage is None."""
        with app.app_context():
            co = Company(name='NoFin AB', org_number='556600-0097', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.flush()
            rev = Account(company_id=co.id, account_number='3010', name='Rev', account_type='revenue')
            cash = Account(company_id=co.id, account_number='1930', name='Bank', account_type='asset')
            db.session.add_all([rev, cash])
            db.session.flush()
            v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                             verification_number=1, verification_date=date(2025, 3, 1))
            db.session.add(v)
            db.session.flush()
            db.session.add_all([
                VerificationRow(verification_id=v.id, account_id=cash.id,
                                debit=Decimal('50000'), credit=Decimal('0')),
                VerificationRow(verification_id=v.id, account_id=rev.id,
                                debit=Decimal('0'), credit=Decimal('50000')),
            ])
            db.session.commit()

            ratios = get_financial_ratios(co.id, fy.id)
            assert ratios['solvency']['interest_coverage']['value'] is None


# ---------------------------------------------------------------------------
# Multi-Year Tests
# ---------------------------------------------------------------------------

class TestMultiYear:
    def test_multi_year_two_fys(self, app, db):
        with app.app_context():
            co = Company(name='MultiY AB', org_number='556600-0096', company_type='AB')
            db.session.add(co)
            db.session.flush()

            for year in (2024, 2025):
                fy = FiscalYear(company_id=co.id, year=year,
                                start_date=date(year, 1, 1), end_date=date(year, 12, 31),
                                status='open')
                db.session.add(fy)
                db.session.flush()
                rev = Account(company_id=co.id, account_number='3010', name='Rev', account_type='revenue')
                cash = Account(company_id=co.id, account_number='1930', name='Bank', account_type='asset')
                # Avoid duplicate accounts
                existing = Account.query.filter_by(company_id=co.id, account_number='3010').first()
                if not existing:
                    db.session.add_all([rev, cash])
                    db.session.flush()
                else:
                    rev = existing
                    cash = Account.query.filter_by(company_id=co.id, account_number='1930').first()

                v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                                 verification_number=1, verification_date=date(year, 6, 1))
                db.session.add(v)
                db.session.flush()
                db.session.add_all([
                    VerificationRow(verification_id=v.id, account_id=cash.id,
                                    debit=Decimal(str(year * 100)), credit=Decimal('0')),
                    VerificationRow(verification_id=v.id, account_id=rev.id,
                                    debit=Decimal('0'), credit=Decimal(str(year * 100))),
                ])
            db.session.commit()

            result = get_multi_year_ratios(co.id, num_years=5)
            assert len(result['years']) == 2
            assert 2024 in result['years']
            assert 2025 in result['years']
            assert 'gross_margin' in result['ratios']
            assert len(result['ratios']['gross_margin']) == 2

    def test_multi_year_single_fy(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            result = get_multi_year_ratios(co.id, num_years=5)
            assert len(result['years']) == 1


# ---------------------------------------------------------------------------
# Traffic Light Tests
# ---------------------------------------------------------------------------

class TestTrafficLights:
    def test_summary_statuses(self, app, ratio_company):
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            summary = get_ratio_summary(co.id, fy.id)
            assert len(summary) > 0

            # All entries should have a valid status
            for item in summary:
                assert item['status'] in ('good', 'warning', 'danger', 'secondary')
                assert 'label' in item
                assert 'value' in item

    def test_high_equity_ratio_is_good(self, app, ratio_company):
        """63.5% equity ratio should be 'good' (benchmark high=40%)."""
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            summary = get_ratio_summary(co.id, fy.id)
            equity_item = next(i for i in summary if i['name'] == 'equity_ratio')
            assert equity_item['status'] == 'good'

    def test_low_debt_to_equity_is_good(self, app, ratio_company):
        """0.45 D/E ratio should be 'good' (inverted, benchmark low=1.0)."""
        with app.app_context():
            co = ratio_company['company']
            fy = ratio_company['fy']
            summary = get_ratio_summary(co.id, fy.id)
            de_item = next(i for i in summary if i['name'] == 'debt_to_equity')
            assert de_item['status'] == 'good'


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestRatioRoutes:
    def test_ratios_index(self, logged_in_client, ratio_company):
        co = ratio_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/ratios/')
        assert resp.status_code == 200
        assert 'Nyckeltal' in resp.data.decode()

    def test_ratios_api_multi_year(self, logged_in_client, ratio_company):
        co = ratio_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/ratios/api/multi-year')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'years' in data
        assert 'ratios' in data

    def test_ratios_no_company(self, logged_in_client):
        resp = logged_in_client.get('/ratios/', follow_redirects=False)
        assert resp.status_code == 302
