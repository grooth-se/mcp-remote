"""Tests for Deklaration (yearly tax return / inkomstdeklaration) feature."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.tax import TaxReturn, TaxReturnAdjustment
from app.services.deklaration_service import (
    create_tax_return, get_tax_return, get_tax_returns,
    update_adjustments, add_adjustment_line, remove_adjustment_line,
    refresh_from_accounting, submit_tax_return, approve_tax_return,
    export_tax_return_excel, get_deklaration_summary,
)


@pytest.fixture
def deklaration_data(db):
    """Company with FY, accounts, and verification data for tax return."""
    co = Company(name='Skatt AB', org_number='556600-0060', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    # Revenue: 500,000 (credit on 3010)
    rev = Account(company_id=co.id, account_number='3010', name='Försäljning', account_type='revenue')
    # COGS: 150,000 (debit on 4010)
    cogs = Account(company_id=co.id, account_number='4010', name='Varuinköp', account_type='expense')
    # External costs: 80,000 (debit on 5010)
    ext = Account(company_id=co.id, account_number='5010', name='Lokalhyra', account_type='expense')
    # Personnel: 100,000 (debit on 7010)
    pers = Account(company_id=co.id, account_number='7010', name='Löner', account_type='expense')
    # Depreciation: 20,000 (debit on 7832)
    depr = Account(company_id=co.id, account_number='7832', name='Avskrivning inventarier', account_type='expense')
    # Financial income: 5,000 (credit on 8310)
    fin_inc = Account(company_id=co.id, account_number='8310', name='Ränteintäkter', account_type='revenue')
    # Financial expense: 10,000 (debit on 8410)
    fin_exp = Account(company_id=co.id, account_number='8410', name='Räntekostnader', account_type='expense')
    # Cash: 1930
    cash = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')

    db.session.add_all([rev, cogs, ext, pers, depr, fin_inc, fin_exp, cash])
    db.session.flush()

    # Create verifications
    v1 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=1, verification_date=date(2025, 3, 1))
    db.session.add(v1)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v1.id, account_id=cash.id, debit=Decimal('500000'), credit=Decimal('0')),
        VerificationRow(verification_id=v1.id, account_id=rev.id, debit=Decimal('0'), credit=Decimal('500000')),
    ])

    v2 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=2, verification_date=date(2025, 3, 15))
    db.session.add(v2)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v2.id, account_id=cogs.id, debit=Decimal('150000'), credit=Decimal('0')),
        VerificationRow(verification_id=v2.id, account_id=cash.id, debit=Decimal('0'), credit=Decimal('150000')),
    ])

    v3 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=3, verification_date=date(2025, 4, 1))
    db.session.add(v3)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v3.id, account_id=ext.id, debit=Decimal('80000'), credit=Decimal('0')),
        VerificationRow(verification_id=v3.id, account_id=cash.id, debit=Decimal('0'), credit=Decimal('80000')),
    ])

    v4 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=4, verification_date=date(2025, 5, 1))
    db.session.add(v4)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v4.id, account_id=pers.id, debit=Decimal('100000'), credit=Decimal('0')),
        VerificationRow(verification_id=v4.id, account_id=cash.id, debit=Decimal('0'), credit=Decimal('100000')),
    ])

    v5 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=5, verification_date=date(2025, 6, 1))
    db.session.add(v5)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v5.id, account_id=depr.id, debit=Decimal('20000'), credit=Decimal('0')),
        VerificationRow(verification_id=v5.id, account_id=cash.id, debit=Decimal('0'), credit=Decimal('20000')),
    ])

    v6 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=6, verification_date=date(2025, 7, 1))
    db.session.add(v6)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v6.id, account_id=cash.id, debit=Decimal('5000'), credit=Decimal('0')),
        VerificationRow(verification_id=v6.id, account_id=fin_inc.id, debit=Decimal('0'), credit=Decimal('5000')),
    ])

    v7 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=7, verification_date=date(2025, 8, 1))
    db.session.add(v7)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v7.id, account_id=fin_exp.id, debit=Decimal('10000'), credit=Decimal('0')),
        VerificationRow(verification_id=v7.id, account_id=cash.id, debit=Decimal('0'), credit=Decimal('10000')),
    ])

    db.session.commit()
    return {'company': co, 'fy': fy}


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestCreateTaxReturn:
    def test_create_for_ab(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']

        tr = create_tax_return(co.id, fy.id)
        assert tr is not None
        assert tr.return_type == 'ink2'
        assert tr.tax_year == 2025
        assert tr.status == 'draft'

    def test_auto_populate_pnl(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']

        tr = create_tax_return(co.id, fy.id)
        # Revenue: 500k
        assert float(tr.net_revenue) == 500000.0
        # Operating expenses: 150k + 80k + 100k = 330k
        assert float(tr.operating_expenses) == 330000.0
        # Depreciation: 20k
        assert float(tr.depreciation_booked) == 20000.0
        # Financial income: 5k
        assert float(tr.financial_income) == 5000.0
        # Financial expense: 10k
        assert float(tr.financial_expenses) == 10000.0
        # Net income: 500k - 330k - 20k + 5k - 10k = 145k
        assert float(tr.net_income) == 145000.0

    def test_calculate_tax(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']

        tr = create_tax_return(co.id, fy.id)
        # Taxable income = 145k, tax = 145k * 0.206 = 29870
        assert float(tr.taxable_income) == 145000.0
        assert float(tr.calculated_tax) == 29870.0
        assert float(tr.tax_rate) == 0.206

    def test_idempotent_create(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']

        tr1 = create_tax_return(co.id, fy.id)
        tr2 = create_tax_return(co.id, fy.id)
        assert tr1.id == tr2.id

    def test_hb_return_type(self, db):
        co = Company(name='Familj HB', org_number='969600-0001', company_type='HB')
        db.session.add(co)
        db.session.flush()
        fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        tr = create_tax_return(co.id, fy.id)
        assert tr.return_type == 'ink4'
        assert float(tr.tax_rate) == 0.0
        assert float(tr.calculated_tax) == 0.0


class TestAdjustments:
    def test_update_manual_adjustments(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        updated = update_adjustments(tr.id, {
            'non_deductible_expenses': Decimal('15000'),
            'non_taxable_income': Decimal('5000'),
        })
        # Taxable = 145k + 15k - 5k = 155k
        assert float(updated.taxable_income) == 155000.0
        # Tax = 155k * 0.206 = 31930
        assert float(updated.calculated_tax) == 31930.0

    def test_depreciation_diff(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        update_adjustments(tr.id, {
            'depreciation_tax_diff': Decimal('-5000'),  # Higher tax depreciation
        })
        tr = get_tax_return(tr.id)
        # Taxable = 145k - 5k = 140k
        assert float(tr.taxable_income) == 140000.0

    def test_previous_deficit(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        update_adjustments(tr.id, {
            'previous_deficit': Decimal('50000'),
        })
        tr = get_tax_return(tr.id)
        # Taxable = 145k - 50k deficit = 95k
        assert float(tr.taxable_income) == 95000.0
        assert float(tr.calculated_tax) == 19570.0

    def test_add_adjustment_line(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        adj = add_adjustment_line(tr.id, 'add', 'Representation ej avdragsgill', 3000)
        assert adj is not None
        assert adj.adjustment_type == 'add'

        tr = get_tax_return(tr.id)
        assert float(tr.other_adjustments_add) == 3000.0
        # Taxable = 145k + 3k = 148k
        assert float(tr.taxable_income) == 148000.0

    def test_remove_adjustment_line(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        adj = add_adjustment_line(tr.id, 'add', 'Test', 10000)
        assert float(get_tax_return(tr.id).other_adjustments_add) == 10000.0

        result = remove_adjustment_line(adj.id)
        assert result is True
        tr = get_tax_return(tr.id)
        assert float(tr.other_adjustments_add) == 0.0
        assert float(tr.taxable_income) == 145000.0

    def test_multiple_adjustment_lines(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        add_adjustment_line(tr.id, 'add', 'Böter', 5000)
        add_adjustment_line(tr.id, 'deduct', 'Koncernbidrag', 20000)

        tr = get_tax_return(tr.id)
        assert float(tr.other_adjustments_add) == 5000.0
        assert float(tr.other_adjustments_deduct) == 20000.0
        # Taxable = 145k + 5k - 20k = 130k
        assert float(tr.taxable_income) == 130000.0


class TestLifecycle:
    def test_submit(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        result = submit_tax_return(tr.id)
        assert result.status == 'submitted'
        assert result.submitted_at is not None

    def test_submit_prevents_edit(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)
        submit_tax_return(tr.id)

        result = update_adjustments(tr.id, {'non_deductible_expenses': Decimal('999')})
        assert result is None  # Can't edit submitted return

    def test_approve(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)
        submit_tax_return(tr.id)

        result = approve_tax_return(tr.id)
        assert result.status == 'approved'

    def test_approve_requires_submitted(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        result = approve_tax_return(tr.id)
        assert result is None  # Can't approve draft

    def test_refresh_from_accounting(self, deklaration_data, db):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)
        original_revenue = float(tr.net_revenue)

        # Add more revenue
        rev_acct = Account.query.filter_by(company_id=co.id, account_number='3010').first()
        cash_acct = Account.query.filter_by(company_id=co.id, account_number='1930').first()
        v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                         verification_number=100, verification_date=date(2025, 12, 1))
        db.session.add(v)
        db.session.flush()
        db.session.add_all([
            VerificationRow(verification_id=v.id, account_id=cash_acct.id,
                            debit=Decimal('50000'), credit=Decimal('0')),
            VerificationRow(verification_id=v.id, account_id=rev_acct.id,
                            debit=Decimal('0'), credit=Decimal('50000')),
        ])
        db.session.commit()

        refreshed = refresh_from_accounting(tr.id)
        assert float(refreshed.net_revenue) == original_revenue + 50000.0

    def test_list_returns(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        create_tax_return(co.id, fy.id)

        returns = get_tax_returns(co.id)
        assert len(returns) == 1
        assert returns[0].tax_year == 2025


class TestExport:
    def test_excel_export(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        output = export_tax_return_excel(tr.id)
        assert output is not None
        data = output.read()
        assert len(data) > 0

    def test_summary(self, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        create_tax_return(co.id, fy.id)

        summary = get_deklaration_summary(co.id, 2025)
        assert summary is not None
        assert summary['tax_year'] == 2025
        assert summary['return_type'] == 'ink2'
        assert summary['net_income'] == 145000.0
        assert summary['calculated_tax'] == 29870.0


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestDeklarationRoutes:
    def test_deklaration_index(self, logged_in_client, deklaration_data):
        co = deklaration_data['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/tax/deklaration/')
        assert resp.status_code == 200
        assert 'Inkomstdeklaration' in resp.data.decode()

    def test_deklaration_new_page(self, logged_in_client, deklaration_data):
        co = deklaration_data['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/tax/deklaration/new')
        assert resp.status_code == 200
        assert 'INK2' in resp.data.decode()

    def test_create_and_view(self, logged_in_client, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/tax/deklaration/new',
                                     data={'fiscal_year_id': fy.id},
                                     follow_redirects=True)
        assert resp.status_code == 200
        assert 'Deklaration' in resp.data.decode()
        assert '500' in resp.data.decode()  # Net revenue 500,000

    def test_edit_adjustments(self, logged_in_client, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(f'/tax/deklaration/{tr.id}/edit')
        assert resp.status_code == 200
        assert 'avdragsgilla' in resp.data.decode().lower()

    def test_export_excel(self, logged_in_client, deklaration_data):
        co = deklaration_data['company']
        fy = deklaration_data['fy']
        tr = create_tax_return(co.id, fy.id)

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get(f'/tax/deklaration/{tr.id}/export')
        assert resp.status_code == 200
        assert resp.content_type.startswith('application/vnd.openxmlformats')
