"""Tests for period comparison and account drill-down (Phase 6C)."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.comparison_service import (
    compare_periods, get_yoy_analysis, get_account_drilldown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cmp_company(db):
    """Company with three fiscal years for comparison tests."""
    co = Company(name='Cmp AB', org_number='556700-0091', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fys = {}
    for year in (2023, 2024, 2025):
        fy = FiscalYear(company_id=co.id, year=year,
                        start_date=date(year, 1, 1),
                        end_date=date(year, 12, 31),
                        status='closed' if year < 2025 else 'open')
        db.session.add(fy)
        db.session.flush()
        fys[year] = fy

    # Accounts
    accounts = {}
    for num, name, atype in [
        ('1930', 'Företagskonto', 'asset'),
        ('1510', 'Kundfordringar', 'asset'),
        ('2081', 'Aktiekapital', 'equity'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('3010', 'Försäljning', 'revenue'),
        ('4010', 'Inköp', 'expense'),
        ('5010', 'Lokalhyra', 'expense'),
        ('7010', 'Löner', 'expense'),
        ('8410', 'Räntekostnader', 'expense'),
    ]:
        a = Account(company_id=co.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accounts[num] = a

    # --- 2023: Revenue 100k, COGS 30k, Rent 10k, Salary 20k, Interest 2k ---
    _create_fy_data(db, co.id, fys[2023].id, 2023, accounts, {
        'revenue': 100000, 'cogs': 30000, 'rent': 10000, 'salary': 20000, 'interest': 2000,
    })

    # --- 2024: Revenue 120k, COGS 35k, Rent 12k, Salary 25k, Interest 3k ---
    _create_fy_data(db, co.id, fys[2024].id, 2024, accounts, {
        'revenue': 120000, 'cogs': 35000, 'rent': 12000, 'salary': 25000, 'interest': 3000,
    })

    # --- 2025: Revenue 150k, COGS 40k, Rent 15k, Salary 30k, Interest 4k ---
    _create_fy_data(db, co.id, fys[2025].id, 2025, accounts, {
        'revenue': 150000, 'cogs': 40000, 'rent': 15000, 'salary': 30000, 'interest': 4000,
    })

    db.session.commit()
    return {'company': co, 'fys': fys, 'accounts': accounts}


def _create_fy_data(db, company_id, fy_id, year, accounts, amounts):
    """Helper to create standard P&L verifications for a FY."""
    ver_num = 1

    # Revenue (cash sale)
    _add_ver(db, company_id, fy_id, ver_num, date(year, 3, 1), [
        (accounts['1930'], Decimal(str(amounts['revenue'])), Decimal('0')),
        (accounts['3010'], Decimal('0'), Decimal(str(amounts['revenue']))),
    ])
    ver_num += 1

    # COGS
    _add_ver(db, company_id, fy_id, ver_num, date(year, 3, 15), [
        (accounts['4010'], Decimal(str(amounts['cogs'])), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal(str(amounts['cogs']))),
    ])
    ver_num += 1

    # Rent
    _add_ver(db, company_id, fy_id, ver_num, date(year, 4, 1), [
        (accounts['5010'], Decimal(str(amounts['rent'])), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal(str(amounts['rent']))),
    ])
    ver_num += 1

    # Salary
    _add_ver(db, company_id, fy_id, ver_num, date(year, 5, 1), [
        (accounts['7010'], Decimal(str(amounts['salary'])), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal(str(amounts['salary']))),
    ])
    ver_num += 1

    # Interest
    _add_ver(db, company_id, fy_id, ver_num, date(year, 6, 1), [
        (accounts['8410'], Decimal(str(amounts['interest'])), Decimal('0')),
        (accounts['1930'], Decimal('0'), Decimal(str(amounts['interest']))),
    ])


def _add_ver(db, company_id, fy_id, num, ver_date, rows):
    v = Verification(company_id=company_id, fiscal_year_id=fy_id,
                     verification_number=num, verification_date=ver_date)
    db.session.add(v)
    db.session.flush()
    for account, debit, credit in rows:
        db.session.add(VerificationRow(
            verification_id=v.id, account_id=account.id,
            debit=debit, credit=credit))


# ---------------------------------------------------------------------------
# Period Comparison Tests
# ---------------------------------------------------------------------------

class TestComparePeriods:
    def test_pnl_comparison(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            result = compare_periods(co.id, fys[2025].id, fys[2024].id, 'pnl')
            assert 'sections' in result
            assert 'Nettoomsättning' in result['sections']
            assert result['report_type'] == 'pnl'

    def test_pnl_change_amounts(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            result = compare_periods(co.id, fys[2025].id, fys[2024].id, 'pnl')
            rev = result['sections']['Nettoomsättning']
            # 2025: 150k, 2024: 120k, change = 30k
            assert rev['total_a'] == 150000.0
            assert rev['total_b'] == 120000.0
            assert rev['total_change'] == 30000.0

    def test_pnl_change_pct(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            result = compare_periods(co.id, fys[2025].id, fys[2024].id, 'pnl')
            rev = result['sections']['Nettoomsättning']
            # (30000 / 120000) * 100 = 25.0%
            assert rev['total_change_pct'] == 25.0

    def test_balance_comparison(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            result = compare_periods(co.id, fys[2025].id, fys[2024].id, 'balance')
            assert result['report_type'] == 'balance'
            assert 'total_assets' in result

    def test_result_summaries(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            result = compare_periods(co.id, fys[2025].id, fys[2024].id, 'pnl')
            # 2025: gross = 150k - 40k = 110k, 2024: 120k - 35k = 85k
            assert result['gross_profit']['amount_a'] == 110000.0
            assert result['gross_profit']['amount_b'] == 85000.0
            assert result['gross_profit']['change'] == 25000.0

    def test_division_by_zero(self, app, db):
        """When period B has zero, change_pct should be None."""
        with app.app_context():
            co = Company(name='Zero AB', org_number='556700-0092', company_type='AB')
            db.session.add(co)
            db.session.flush()
            fy_a = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                              end_date=date(2025, 12, 31), status='open')
            fy_b = FiscalYear(company_id=co.id, year=2024, start_date=date(2024, 1, 1),
                              end_date=date(2024, 12, 31), status='closed')
            db.session.add_all([fy_a, fy_b])
            db.session.flush()

            rev = Account(company_id=co.id, account_number='3010', name='Rev', account_type='revenue')
            cash = Account(company_id=co.id, account_number='1930', name='Bank', account_type='asset')
            db.session.add_all([rev, cash])
            db.session.flush()

            # Only data in fy_a, none in fy_b
            v = Verification(company_id=co.id, fiscal_year_id=fy_a.id,
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

            result = compare_periods(co.id, fy_a.id, fy_b.id, 'pnl')
            rev_sec = result['sections']['Nettoomsättning']
            assert rev_sec['total_change_pct'] is None  # division by zero


# ---------------------------------------------------------------------------
# Year-over-Year Tests
# ---------------------------------------------------------------------------

class TestYoYAnalysis:
    def test_three_years(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            yoy = get_yoy_analysis(co.id, fys[2025].id, num_years=3)
            assert len(yoy['years']) == 3
            assert yoy['years'][0].year == 2023
            assert yoy['years'][2].year == 2025

    def test_section_values(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            yoy = get_yoy_analysis(co.id, fys[2025].id, num_years=3)
            revenue = yoy['sections']['Nettoomsättning']
            assert revenue == [100000.0, 120000.0, 150000.0]

    def test_change_percentages(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            yoy = get_yoy_analysis(co.id, fys[2025].id, num_years=3)
            rev_changes = yoy['section_changes']['Nettoomsättning']
            assert rev_changes[0] is None  # first year
            assert rev_changes[1] == 20.0  # (120k-100k)/100k * 100
            assert rev_changes[2] == 25.0  # (150k-120k)/120k * 100

    def test_single_year(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            yoy = get_yoy_analysis(co.id, fys[2023].id, num_years=1)
            assert len(yoy['years']) == 1

    def test_summaries(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            yoy = get_yoy_analysis(co.id, fys[2025].id, num_years=3)
            # gross_profit: 2023=70k, 2024=85k, 2025=110k
            assert yoy['summaries']['gross_profit'] == [70000.0, 85000.0, 110000.0]


# ---------------------------------------------------------------------------
# Account Drilldown Tests
# ---------------------------------------------------------------------------

class TestAccountDrilldown:
    def test_basic_drilldown(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            data = get_account_drilldown(co.id, fys[2025].id, '3010')
            assert data is not None
            assert data['account'].account_number == '3010'
            assert len(data['transactions']) > 0

    def test_running_balance(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            data = get_account_drilldown(co.id, fys[2025].id, '1930')
            # Verify running balance increases after each transaction
            for i, t in enumerate(data['transactions']):
                if i == 0:
                    expected = data['opening_balance'] + t['debit'] - t['credit']
                else:
                    expected = data['transactions'][i - 1]['balance'] + t['debit'] - t['credit']
                assert abs(t['balance'] - expected) < 0.01

    def test_closing_balance(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            data = get_account_drilldown(co.id, fys[2025].id, '1930')
            # Closing balance = last transaction balance
            if data['transactions']:
                assert data['closing_balance'] == data['transactions'][-1]['balance']

    def test_date_filter(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            # Only get March transactions
            data = get_account_drilldown(
                co.id, fys[2025].id, '1930',
                start_date=date(2025, 3, 1), end_date=date(2025, 3, 31))
            # Should only have March transactions (revenue + COGS)
            for t in data['transactions']:
                assert t['date'].month == 3

    def test_opening_balance_with_filter(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            # Filter from April — opening balance should include Jan-Mar
            data = get_account_drilldown(
                co.id, fys[2025].id, '1930',
                start_date=date(2025, 4, 1))
            # Before April: revenue 150000, COGS -40000 => net 110000 on 1930
            assert data['opening_balance'] == 110000.0

    def test_monthly_summary(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            data = get_account_drilldown(co.id, fys[2025].id, '1930')
            assert len(data['monthly']) == 12
            # March should have activity
            march = data['monthly'][2]  # index 2 = March
            assert march['debit'] > 0 or march['credit'] > 0

    def test_nonexistent_account(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            data = get_account_drilldown(co.id, fys[2025].id, '9999')
            assert data is None

    def test_total_debit_credit(self, app, cmp_company):
        with app.app_context():
            co = cmp_company['company']
            fys = cmp_company['fys']
            data = get_account_drilldown(co.id, fys[2025].id, '1930')
            total_d = sum(t['debit'] for t in data['transactions'])
            total_c = sum(t['credit'] for t in data['transactions'])
            assert abs(data['total_debit'] - total_d) < 0.01
            assert abs(data['total_credit'] - total_c) < 0.01


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestComparisonRoutes:
    def test_comparison_index(self, logged_in_client, cmp_company):
        co = cmp_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/comparison/')
        assert resp.status_code == 200
        assert 'Periodjämförelse' in resp.data.decode()

    def test_comparison_with_params(self, logged_in_client, cmp_company):
        co = cmp_company['company']
        fys = cmp_company['fys']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(
            f'/comparison/?fy_a={fys[2025].id}&fy_b={fys[2024].id}&report_type=pnl')
        assert resp.status_code == 200
        assert 'Nettoomsättning' in resp.data.decode()

    def test_yoy_page(self, logged_in_client, cmp_company):
        co = cmp_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/comparison/yoy')
        assert resp.status_code == 200
        assert 'Flerårsöversikt' in resp.data.decode()

    def test_yoy_api(self, logged_in_client, cmp_company):
        co = cmp_company['company']
        fys = cmp_company['fys']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(f'/comparison/api/yoy-chart?fiscal_year_id={fys[2025].id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data
        assert 'sections' in data

    def test_drilldown_page(self, logged_in_client, cmp_company):
        co = cmp_company['company']
        fys = cmp_company['fys']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(
            f'/comparison/drilldown/3010?fiscal_year_id={fys[2025].id}')
        assert resp.status_code == 200
        assert 'Kontoanalys' in resp.data.decode()

    def test_no_company_redirect(self, logged_in_client):
        resp = logged_in_client.get('/comparison/', follow_redirects=False)
        assert resp.status_code == 302
