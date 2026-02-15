"""Tests for INK form service — Skatteverket INK2/INK4 tax form reporting."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.user import User
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.tax import TaxReturn
from app.services.deklaration_service import create_tax_return
from app.services.ink_form_service import (
    compute_ink2r, compute_ink2s, compute_ink2_main,
    compute_ink4r, compute_ink4s, compute_all_ink_data,
    generate_sru_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ink_company(db):
    """Company with diverse accounts and verifications for INK form testing.

    Creates accounts and transactions across key BAS ranges to populate
    both balance sheet and income statement INK fields.
    """
    co = Company(name='INK Test AB', org_number='556700-0070', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    # Accounts across key BAS ranges
    accounts = {}
    acct_defs = [
        # Assets (1xxx)
        ('1930', 'Företagskonto', 'asset'),
        ('1510', 'Kundfordringar', 'asset'),
        ('1210', 'Inventarier', 'asset'),
        ('1219', 'Ack avskrivning inventarier', 'asset'),
        # Equity & Liabilities (2xxx)
        ('2010', 'Aktiekapital', 'equity'),
        ('2091', 'Balanserat resultat', 'equity'),
        ('2099', 'Årets resultat', 'equity'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('2610', 'Utgående moms', 'liability'),
        ('2910', 'Upplupna löner', 'liability'),
        # Revenue (3xxx)
        ('3010', 'Försäljning varor', 'revenue'),
        ('3910', 'Hyresintäkter', 'revenue'),
        # COGS (4xxx)
        ('4010', 'Varuinköp', 'expense'),
        # External costs (5xxx-6xxx)
        ('5010', 'Lokalhyra', 'expense'),
        ('6210', 'Telefon', 'expense'),
        # Personnel (7xxx)
        ('7010', 'Löner', 'expense'),
        ('7510', 'Arbetsgivaravgifter', 'expense'),
        # Depreciation (78xx)
        ('7832', 'Avskrivning inventarier', 'expense'),
        # Financial (8xxx)
        ('8310', 'Ränteintäkter', 'revenue'),
        ('8410', 'Räntekostnader', 'expense'),
    ]

    for num, name, atype in acct_defs:
        a = Account(company_id=co.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        accounts[num] = a
    db.session.flush()

    def _ver(nr, dt, rows):
        v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                         verification_number=nr, verification_date=dt)
        db.session.add(v)
        db.session.flush()
        for acct_nr, debit, credit in rows:
            db.session.add(VerificationRow(
                verification_id=v.id, account_id=accounts[acct_nr].id,
                debit=Decimal(str(debit)), credit=Decimal(str(credit)),
            ))

    # Revenue: 800k sales + 50k other = 850k
    _ver(1, date(2025, 1, 15), [
        ('1510', 800000, 0), ('3010', 0, 800000),
    ])
    _ver(2, date(2025, 2, 1), [
        ('1930', 50000, 0), ('3910', 0, 50000),
    ])
    # Cash receipt from customers
    _ver(3, date(2025, 3, 1), [
        ('1930', 800000, 0), ('1510', 0, 800000),
    ])
    # COGS: 200k
    _ver(4, date(2025, 3, 15), [
        ('4010', 200000, 0), ('1930', 0, 200000),
    ])
    # External costs: 60k rent + 15k phone = 75k
    _ver(5, date(2025, 4, 1), [
        ('5010', 60000, 0), ('1930', 0, 60000),
    ])
    _ver(6, date(2025, 4, 15), [
        ('6210', 15000, 0), ('1930', 0, 15000),
    ])
    # Personnel: 120k salaries + 40k employer tax = 160k
    _ver(7, date(2025, 5, 1), [
        ('7010', 120000, 0), ('1930', 0, 120000),
    ])
    _ver(8, date(2025, 5, 15), [
        ('7510', 40000, 0), ('1930', 0, 40000),
    ])
    # Depreciation: 30k
    _ver(9, date(2025, 6, 1), [
        ('7832', 30000, 0), ('1219', 0, 30000),
    ])
    # Financial: 5k interest income, 12k interest expense
    _ver(10, date(2025, 7, 1), [
        ('1930', 5000, 0), ('8310', 0, 5000),
    ])
    _ver(11, date(2025, 7, 15), [
        ('8410', 12000, 0), ('1930', 0, 12000),
    ])
    # Equipment purchase: 300k
    _ver(12, date(2025, 1, 10), [
        ('1210', 300000, 0), ('1930', 0, 300000),
    ])
    # Equity: aktiekapital 100k, balanserat resultat 200k
    _ver(13, date(2025, 1, 1), [
        ('1930', 300000, 0), ('2010', 0, 100000), ('2091', 0, 200000),
    ])
    # Accounts payable: 45k
    _ver(14, date(2025, 8, 1), [
        ('5010', 45000, 0), ('2440', 0, 45000),
    ])
    # VAT liability: 20k
    _ver(15, date(2025, 9, 1), [
        ('1930', 0, 20000), ('2610', 0, 20000),
    ])
    # Accrued salaries: 25k
    _ver(16, date(2025, 12, 31), [
        ('7010', 25000, 0), ('2910', 0, 25000),
    ])

    db.session.commit()

    # Create a tax return
    tr = create_tax_return(co.id, fy.id)

    return {
        'company': co,
        'fy': fy,
        'tr': db.session.get(TaxReturn, tr.id),
        'accounts': accounts,
    }


@pytest.fixture
def ink_hb_company(db):
    """HB company for INK4 testing."""
    co = Company(name='INK Test HB', org_number='969700-0071', company_type='HB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    rev = Account(company_id=co.id, account_number='3010', name='Försäljning', account_type='revenue')
    cash = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')
    db.session.add_all([rev, cash])
    db.session.flush()

    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 6, 1))
    db.session.add(v)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v.id, account_id=cash.id, debit=Decimal('100000'), credit=Decimal('0')),
        VerificationRow(verification_id=v.id, account_id=rev.id, debit=Decimal('0'), credit=Decimal('100000')),
    ])
    db.session.commit()

    tr = create_tax_return(co.id, fy.id)
    return {'company': co, 'fy': fy, 'tr': db.session.get(TaxReturn, tr.id)}


def _set_company(client, company):
    with client.session_transaction() as sess:
        sess['active_company_id'] = company.id


# ---------------------------------------------------------------------------
# INK2R Balance Sheet Tests
# ---------------------------------------------------------------------------

class TestINK2RBalanceSheet:
    def test_cash_and_bank_field_2_26(self, ink_company):
        """BAS 19xx accounts map to field 2.26."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        # Cash balance: 300k equity + 800k + 50k + 5k - 200k - 60k - 15k - 120k - 40k - 12k - 300k - 20k = 388k
        assert bs['2.26']['value'] != Decimal('0')
        assert bs['2.26']['sru_code'] == '7281'

    def test_accounts_receivable_field_2_19(self, ink_company):
        """BAS 151x accounts map to field 2.19."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        # 800k debit - 800k credit = 0 (fully collected)
        assert bs['2.19']['value'] == Decimal('0')
        assert bs['2.19']['sru_code'] == '7251'

    def test_machinery_field_2_4(self, ink_company):
        """BAS 12xx accounts map to field 2.4."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        # 300k equipment - 30k depreciation = 270k
        assert bs['2.4']['value'] == Decimal('270000')

    def test_accounts_payable_field_2_45(self, ink_company):
        """BAS 244x accounts map to field 2.45 (credit side)."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        assert bs['2.45']['value'] == Decimal('45000')
        assert bs['2.45']['sru_code'] == '7361'

    def test_equity_bundet(self, ink_company):
        """BAS 201x accounts map to field 2.27 (credit side)."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        assert bs['2.27']['value'] == Decimal('100000')
        assert bs['2.27']['sru_code'] == '7301'

    def test_equity_fritt(self, ink_company):
        """BAS 207-209 accounts map to field 2.28."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        # 2091 balanserat resultat = 200k (credit)
        assert bs['2.28']['value'] == Decimal('200000')

    def test_subtotals_sum_correctly(self, ink_company):
        """Subtotals should sum their component fields."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']

        # sum_fixed_assets = sum_intangible + sum_tangible + sum_financial
        assert bs['sum_fixed_assets']['value'] == (
            bs['sum_intangible']['value'] + bs['sum_tangible']['value'] + bs['sum_financial_fixed']['value']
        )

    def test_all_fields_have_sru_codes(self, ink_company):
        """Every non-section, non-subtotal field should have an SRU code."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        for key, field in result['balance_sheet'].items():
            if not field.get('is_section') and not key.startswith('sum_'):
                assert field['sru_code'] is not None, f"Field {key} missing SRU code"

    def test_empty_accounts_return_zero(self, ink_company):
        """Fields for unused account ranges should return zero."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        bs = result['balance_sheet']
        # No intangible assets in test data
        assert bs['2.1']['value'] == Decimal('0')
        # No buildings
        assert bs['2.3']['value'] == Decimal('0')


# ---------------------------------------------------------------------------
# INK2R Income Statement Tests
# ---------------------------------------------------------------------------

class TestINK2RIncomeStatement:
    def test_net_revenue_field_3_1(self, ink_company):
        """BAS 30-37xx accounts map to field 3.1."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        inc = result['income_statement']
        assert inc['3.1']['value'] == Decimal('800000')
        assert inc['3.1']['sru_code'] == '7410'

    def test_other_operating_income_field_3_4(self, ink_company):
        """BAS 39xx accounts map to field 3.4."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        inc = result['income_statement']
        assert inc['3.4']['value'] == Decimal('50000')

    def test_personnel_costs_field_3_8(self, ink_company):
        """BAS 70-76xx accounts map to field 3.8."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        inc = result['income_statement']
        # 120k + 25k salaries + 40k employer tax = 185k
        assert inc['3.8']['value'] == Decimal('185000')

    def test_depreciation_field_3_9(self, ink_company):
        """BAS 77-78xx accounts map to field 3.9."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        inc = result['income_statement']
        assert inc['3.9']['value'] == Decimal('30000')

    def test_operating_result_computed(self, ink_company):
        """Rörelseresultat = revenue - costs."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        inc = result['income_statement']
        expected = inc['sum_revenue']['value'] - inc['sum_costs']['value']
        assert inc['operating_result']['value'] == expected

    def test_annual_result_positive(self, ink_company):
        """Positive result goes to field 3.26, 3.27 = 0."""
        co, fy = ink_company['company'], ink_company['fy']
        result = compute_ink2r(co.id, fy.id)
        inc = result['income_statement']
        annual = result['totals']['annual_result']
        if annual >= 0:
            assert inc['3.26']['value'] == annual
            assert inc['3.27']['value'] == Decimal('0')
        else:
            assert inc['3.26']['value'] == Decimal('0')
            assert inc['3.27']['value'] == abs(annual)


# ---------------------------------------------------------------------------
# INK2S Tests
# ---------------------------------------------------------------------------

class TestINK2S:
    def test_annual_result_in_4_1_or_4_2(self, ink_company):
        """Net income goes to field 4.1 (profit) or 4.2 (loss)."""
        tr = ink_company['tr']
        fields = compute_ink2s(tr)
        net = tr.net_income or Decimal('0')
        if net >= 0:
            assert fields['4.1']['value'] == net
            assert fields['4.2']['value'] == Decimal('0')
        else:
            assert fields['4.1']['value'] == Decimal('0')
            assert fields['4.2']['value'] == abs(net)

    def test_non_deductible_field_4_3c(self, db, ink_company):
        """Non-deductible expenses map to field 4.3c."""
        tr = ink_company['tr']
        tr.non_deductible_expenses = Decimal('15000')
        db.session.commit()
        tr = db.session.get(TaxReturn, tr.id)
        fields = compute_ink2s(tr)
        assert fields['4.3c']['value'] == Decimal('15000')

    def test_non_taxable_field_4_5c(self, db, ink_company):
        """Non-taxable income maps to field 4.5c."""
        tr = ink_company['tr']
        tr.non_taxable_income = Decimal('8000')
        db.session.commit()
        tr = db.session.get(TaxReturn, tr.id)
        fields = compute_ink2s(tr)
        assert fields['4.5c']['value'] == Decimal('8000')

    def test_surplus_field_4_15(self, ink_company):
        """Positive taxable income goes to field 4.15."""
        tr = ink_company['tr']
        fields = compute_ink2s(tr)
        # With positive net income and no adjustments, should have surplus
        if tr.net_income and tr.net_income > 0:
            assert fields['4.15']['value'] > 0

    def test_all_fields_have_sru(self, ink_company):
        """All non-section fields should have SRU codes."""
        tr = ink_company['tr']
        fields = compute_ink2s(tr)
        for key, field in fields.items():
            if not field.get('is_section'):
                assert field['sru_code'] is not None, f"Field {key} missing SRU"


# ---------------------------------------------------------------------------
# INK2 Main Tests
# ---------------------------------------------------------------------------

class TestINK2Main:
    def test_surplus_field_1_1(self, ink_company):
        """Positive taxable income flows to field 1.1."""
        tr = ink_company['tr']
        ink_s = compute_ink2s(tr)
        main = compute_ink2_main(ink_s)
        surplus = ink_s['4.15']['value']
        assert main['1.1']['value'] == surplus
        assert main['1.1']['sru_code'] == '7011'

    def test_deficit_field_1_2(self, ink_company):
        """Deficit flows to field 1.2."""
        tr = ink_company['tr']
        ink_s = compute_ink2s(tr)
        main = compute_ink2_main(ink_s)
        deficit = ink_s['4.16']['value']
        assert main['1.2']['value'] == deficit
        assert main['1.2']['sru_code'] == '7012'


# ---------------------------------------------------------------------------
# SRU Export Tests
# ---------------------------------------------------------------------------

class TestSRUExport:
    def test_sru_file_format(self, ink_company):
        """SRU file should have correct header structure."""
        output = generate_sru_file(ink_company['tr'].id)
        assert output is not None
        content = output.read().decode('iso-8859-1')
        assert '#DATABESKRIVNING_START' in content
        assert '#PRODUKT SRU' in content
        assert '#DATABESKRIVNING_SLUT' in content
        assert '#MEDESSION_START' in content
        assert '#MEDESSION_SLUT' in content
        assert '#PROGRAM PsalmGears' in content

    def test_sru_org_number_no_dash(self, ink_company):
        """Org number in SRU should be without dash."""
        output = generate_sru_file(ink_company['tr'].id)
        content = output.read().decode('iso-8859-1')
        assert '#UPPGIFTSLAMNARE 5567000070' in content

    def test_sru_field_values(self, ink_company):
        """SRU file should contain #FLT lines with SRU codes and values."""
        output = generate_sru_file(ink_company['tr'].id)
        content = output.read().decode('iso-8859-1')
        # Should contain field lines
        assert '#FLT' in content
        # Net revenue (SRU 7410) should be present
        assert '#FLT 7410 800000' in content

    def test_sru_blankett_names(self, ink_company):
        """Blankett names should include form type and year."""
        output = generate_sru_file(ink_company['tr'].id)
        content = output.read().decode('iso-8859-1')
        assert '#BLANKETT INK2R-2025P4' in content
        assert '#BLANKETT INK2S-2025P4' in content
        assert '#BLANKETT INK2-2025P4' in content


# ---------------------------------------------------------------------------
# INK4 Tests
# ---------------------------------------------------------------------------

class TestINK4:
    def test_hb_gets_ink4(self, ink_hb_company):
        """HB company should produce INK4 data."""
        data = compute_all_ink_data(ink_hb_company['tr'].id)
        assert data['ink_type'] == 'INK4'

    def test_hb_no_corporate_tax(self, ink_hb_company):
        """HB tax return has 0% tax rate."""
        tr = ink_hb_company['tr']
        assert tr.return_type == 'ink4'
        assert float(tr.tax_rate) == 0.0


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestINKRoutes:
    def test_ink_view_page(self, logged_in_client, ink_company):
        """INK form view page should load successfully."""
        _set_company(logged_in_client, ink_company['company'])
        resp = logged_in_client.get(f'/tax/deklaration/{ink_company["tr"].id}/ink-form')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'INK2' in html
        assert 'Balansräkning' in html
        assert 'Resultaträkning' in html

    def test_ink_view_requires_login(self, client, ink_company):
        """INK form view requires login."""
        resp = client.get(f'/tax/deklaration/{ink_company["tr"].id}/ink-form')
        assert resp.status_code == 302

    def test_ink_view_requires_company(self, logged_in_client, ink_company):
        """INK form view requires active company in session."""
        resp = logged_in_client.get(f'/tax/deklaration/{ink_company["tr"].id}/ink-form')
        assert resp.status_code == 302

    def test_sru_download(self, logged_in_client, ink_company):
        """SRU file should be downloadable."""
        _set_company(logged_in_client, ink_company['company'])
        resp = logged_in_client.get(f'/tax/deklaration/{ink_company["tr"].id}/sru')
        assert resp.status_code == 200
        assert 'text/plain' in resp.content_type

    def test_deklaration_view_has_ink_buttons(self, logged_in_client, ink_company):
        """Deklaration view should have INK form buttons."""
        _set_company(logged_in_client, ink_company['company'])
        resp = logged_in_client.get(f'/tax/deklaration/{ink_company["tr"].id}')
        html = resp.data.decode()
        assert 'INK-formulär' in html
        assert 'INK PDF' in html
        assert 'SRU-fil' in html
