"""Tests for cash flow statement service (Phase 6B)."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.cashflow_service import (
    get_cash_flow_statement, get_monthly_cash_flow,
    get_cash_flow_forecast, export_cashflow_to_excel, _classify_counterparts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cf_company(db):
    """Company with two fiscal years and accounting data for CF tests."""
    co = Company(name='CF AB', org_number='556600-0081', company_type='AB')
    db.session.add(co)
    db.session.flush()

    # Prior year (2024)
    fy24 = FiscalYear(company_id=co.id, year=2024, start_date=date(2024, 1, 1),
                      end_date=date(2024, 12, 31), status='closed')
    db.session.add(fy24)
    db.session.flush()

    # Current year (2025)
    fy25 = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                      end_date=date(2025, 12, 31), status='open')
    db.session.add(fy25)
    db.session.flush()

    # Accounts
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
        ('1229', 'Ack avskrivningar inventarier', 'asset'),
        ('7810', 'Avskrivningar', 'expense'),
        ('8410', 'Räntekostnader', 'expense'),
    ]
    for num, name, atype in acct_defs:
        a = Account(company_id=co.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accounts[num] = a

    # --- PRIOR YEAR (2024) ---
    # Opening equity 300000
    _add_ver(db, co.id, fy24.id, 1, date(2024, 1, 1), [
        (accounts['1930'], Decimal('300000'), Decimal('0')),
        (accounts['2081'], Decimal('0'), Decimal('300000')),
    ])
    # Receivables 20000
    _add_ver(db, co.id, fy24.id, 2, date(2024, 6, 1), [
        (accounts['1510'], Decimal('20000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('20000')),
    ])
    # Inventory 15000
    _add_ver(db, co.id, fy24.id, 3, date(2024, 3, 1), [
        (accounts['1400'], Decimal('15000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('15000')),
    ])
    # Fixed asset 50000
    _add_ver(db, co.id, fy24.id, 4, date(2024, 2, 1), [
        (accounts['1220'], Decimal('50000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('50000')),
    ])

    # --- CURRENT YEAR (2025) ---
    # Revenue 150000 (March)
    _add_ver(db, co.id, fy25.id, 1, date(2025, 3, 1), [
        (accounts['1930'], Decimal('150000'), Decimal('0')),
        (accounts['3010'], Decimal('0'), Decimal('150000')),
    ])
    # COGS 40000 (March)
    _add_ver(db, co.id, fy25.id, 2, date(2025, 3, 15), [
        (accounts['4010'], Decimal('40000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('40000')),
    ])
    # Rent 10000 (April)
    _add_ver(db, co.id, fy25.id, 3, date(2025, 4, 1), [
        (accounts['5010'], Decimal('10000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('10000')),
    ])
    # Depreciation 5000 (June) — debit 7810, credit 1229
    _add_ver(db, co.id, fy25.id, 4, date(2025, 6, 1), [
        (accounts['7810'], Decimal('5000'), Decimal('0')),
        (accounts['1229'], Decimal('0'), Decimal('5000')),
    ])
    # Receivables 35000 (July)
    _add_ver(db, co.id, fy25.id, 5, date(2025, 7, 1), [
        (accounts['1510'], Decimal('35000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('35000')),
    ])
    # Inventory 25000 (Feb)
    _add_ver(db, co.id, fy25.id, 6, date(2025, 2, 1), [
        (accounts['1400'], Decimal('25000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('25000')),
    ])
    # Payables 18000 (May)
    _add_ver(db, co.id, fy25.id, 7, date(2025, 5, 1), [
        (accounts['5010'], Decimal('18000'), Decimal('0')),
        (accounts['2440'], Decimal('0'), Decimal('18000')),
    ])
    # New fixed asset 30000 (Aug)
    _add_ver(db, co.id, fy25.id, 8, date(2025, 8, 1), [
        (accounts['1220'], Decimal('30000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('30000')),
    ])
    # Bank loan 100000 (Jan)
    _add_ver(db, co.id, fy25.id, 9, date(2025, 1, 15), [
        (accounts['1930'], Decimal('100000'), Decimal('0')),
        (accounts['2310'], Decimal('0'), Decimal('100000')),
    ])
    # Interest 3000 (Sep)
    _add_ver(db, co.id, fy25.id, 10, date(2025, 9, 1), [
        (accounts['8410'], Decimal('3000'), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal('3000')),
    ])

    db.session.commit()

    return {'company': co, 'fy24': fy24, 'fy25': fy25, 'accounts': accounts}


def _add_ver(db, company_id, fy_id, num, ver_date, rows):
    """Helper to add a verification with rows."""
    v = Verification(company_id=company_id, fiscal_year_id=fy_id,
                     verification_number=num, verification_date=ver_date)
    db.session.add(v)
    db.session.flush()
    for account, debit, credit in rows:
        db.session.add(VerificationRow(
            verification_id=v.id, account_id=account.id,
            debit=debit, credit=credit))


# ---------------------------------------------------------------------------
# Cash Flow Statement Tests
# ---------------------------------------------------------------------------

class TestCashFlowStatement:
    def test_basic_structure(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            assert 'operating' in cf
            assert 'investing' in cf
            assert 'financing' in cf
            assert 'total_cash_flow' in cf
            assert 'opening_cash' in cf
            assert 'closing_cash' in cf

    def test_operating_includes_result(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            # Revenue 150000 - COGS 40000 - Rent 10000 - Personnel_rent 18000 - Depreciation 5000 - Interest 3000
            # = operating 65000 + fin -3000 = 62000... let me check P&L
            # gross = 150000 - 40000 = 110000
            # ext costs: 10000 + 18000 = 28000, personnel (7810): 5000
            # operating = 110000 - 28000 - 5000 = 77000
            # fin costs = 3000
            # result_before_tax = 77000 - 3000 = 74000
            assert cf['operating']['result_before_tax'] == 74000.0

    def test_depreciation_adjustment(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            depr_adj = next((a for a in cf['operating']['adjustments']
                             if 'Avskrivningar' in a['label']), None)
            # 7810 has debit 5000, balance = 5000 (debit - credit)
            assert depr_adj is not None
            assert depr_adj['amount'] == 5000.0

    def test_receivables_change(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            recv_adj = next((a for a in cf['operating']['adjustments']
                             if 'kundfordringar' in a['label'].lower()), None)
            # Prior: 20000, Current: 35000, change = -(35000-20000) = -15000
            assert recv_adj is not None
            assert recv_adj['amount'] == -15000.0

    def test_inventory_change(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            inv_adj = next((a for a in cf['operating']['adjustments']
                            if 'varulager' in a['label'].lower()), None)
            # Prior: 15000, Current: 25000, change = -(25000-15000) = -10000
            assert inv_adj is not None
            assert inv_adj['amount'] == -10000.0

    def test_payables_change(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            pay_adj = next((a for a in cf['operating']['adjustments']
                            if 'leverantörsskulder' in a['label'].lower()), None)
            # Prior: 0, Current payable (2440): 18000, change = 18000
            assert pay_adj is not None
            assert pay_adj['amount'] == 18000.0

    def test_financing_lt_debt(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            lt_item = next((i for i in cf['financing']['line_items']
                            if 'långfristiga' in i['label'].lower()), None)
            # Prior LT debt (2310): 0, Current: 100000, change = 100000
            assert lt_item is not None
            assert lt_item['amount'] == 100000.0

    def test_opening_closing_cash(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            # Prior cash (1930): 300000-20000-15000-50000 = 215000
            assert cf['opening_cash'] == 215000.0
            # Current cash: verify it's positive
            assert cf['closing_cash'] > 0

    def test_no_prior_year(self, app, db):
        """First FY: opening cash = 0, no working capital changes."""
        with app.app_context():
            co = Company(name='NewCF AB', org_number='556600-0082', company_type='AB')
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

            cf = get_cash_flow_statement(co.id, fy.id)
            assert cf['opening_cash'] == 0.0
            assert cf['closing_cash'] == 50000.0

    def test_empty_fy(self, app, db):
        with app.app_context():
            co = Company(name='EmptyCF AB', org_number='556600-0083', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.commit()

            cf = get_cash_flow_statement(co.id, fy.id)
            assert cf['total_cash_flow'] == 0.0


# ---------------------------------------------------------------------------
# Monthly Cash Flow Tests
# ---------------------------------------------------------------------------

class TestMonthlyCashFlow:
    def test_structure(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            monthly = get_monthly_cash_flow(co.id, fy.id)
            assert len(monthly['labels']) == 12
            assert len(monthly['operating']) == 12
            assert len(monthly['investing']) == 12
            assert len(monthly['financing']) == 12
            assert len(monthly['net']) == 12
            assert len(monthly['cumulative']) == 12

    def test_cumulative_running_total(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            monthly = get_monthly_cash_flow(co.id, fy.id)
            # Verify cumulative is running sum of net
            running = 0
            for i, net_val in enumerate(monthly['net']):
                running += net_val
                assert abs(monthly['cumulative'][i] - running) < 0.01

    def test_classify_counterparts_operating(self):
        assert _classify_counterparts(['3010', '5010']) == 'operating'

    def test_classify_counterparts_investing(self):
        assert _classify_counterparts(['1220']) == 'investing'

    def test_classify_counterparts_financing(self):
        assert _classify_counterparts(['2310']) == 'financing'


# ---------------------------------------------------------------------------
# Forecast Tests
# ---------------------------------------------------------------------------

class TestForecast:
    def test_forecast_structure(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            forecast = get_cash_flow_forecast(co.id, fy.id)
            assert len(forecast['actual']) == 12
            assert len(forecast['forecast']) == 12
            assert 'avg_monthly_cf' in forecast

    def test_forecast_no_data(self, app, db):
        with app.app_context():
            co = Company(name='NoDataCF AB', org_number='556600-0084', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                            end_date=date(2025, 12, 31), status='open')
            db.session.add(fy)
            db.session.commit()

            forecast = get_cash_flow_forecast(co.id, fy.id)
            assert forecast['avg_monthly_cf'] == 0.0


# ---------------------------------------------------------------------------
# Excel Export Test
# ---------------------------------------------------------------------------

class TestExcelExport:
    def test_export(self, app, cf_company):
        with app.app_context():
            co = cf_company['company']
            fy = cf_company['fy25']
            cf = get_cash_flow_statement(co.id, fy.id)
            output = export_cashflow_to_excel(cf, co.name, fy)
            assert output is not None
            assert output.getbuffer().nbytes > 0


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestCashFlowRoutes:
    def test_cashflow_index(self, logged_in_client, cf_company):
        co = cf_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/cashflow/')
        assert resp.status_code == 200
        assert 'Kassaflödesanalys' in resp.data.decode()

    def test_cashflow_api_monthly(self, logged_in_client, cf_company):
        co = cf_company['company']
        fy = cf_company['fy25']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(f'/cashflow/api/monthly?fiscal_year_id={fy.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'monthly' in data
        assert 'forecast' in data

    def test_cashflow_excel(self, logged_in_client, cf_company):
        co = cf_company['company']
        fy = cf_company['fy25']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(f'/cashflow/excel?fiscal_year_id={fy.id}')
        assert resp.status_code == 200
        assert 'spreadsheet' in resp.content_type

    def test_cashflow_no_company(self, logged_in_client):
        resp = logged_in_client.get('/cashflow/', follow_redirects=False)
        assert resp.status_code == 302
