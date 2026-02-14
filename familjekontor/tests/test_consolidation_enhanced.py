"""Tests for consolidation enhancements (Phase 5E) —
intercompany detection, minority interest, goodwill, cash flow."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.consolidation import IntercompanyMatch, AcquisitionGoodwill
from app.services.consolidation_service import (
    create_consolidation_group, add_member,
    get_consolidated_pnl, get_consolidated_balance_sheet,
    calculate_effective_ownership, calculate_minority_interest,
    detect_intercompany_transactions, confirm_match, reject_match,
    get_pending_matches,
    register_acquisition, calculate_goodwill_amortization,
    get_total_remaining_goodwill, get_goodwill_entries,
    get_consolidated_cash_flow, export_consolidated_report,
)


@pytest.fixture
def consol_data(db):
    """Two companies with accounting data for 2024 and 2025."""
    parent = Company(name='Moder AB', org_number='556600-0050', company_type='AB')
    sub = Company(name='Dotter AB', org_number='556600-0051', company_type='AB')
    db.session.add_all([parent, sub])
    db.session.flush()

    # Fiscal years for two years (for cash flow comparison)
    fy_p_24 = FiscalYear(company_id=parent.id, year=2024, start_date=date(2024, 1, 1),
                         end_date=date(2024, 12, 31), status='closed')
    fy_p_25 = FiscalYear(company_id=parent.id, year=2025, start_date=date(2025, 1, 1),
                         end_date=date(2025, 12, 31), status='open')
    fy_s_24 = FiscalYear(company_id=sub.id, year=2024, start_date=date(2024, 1, 1),
                         end_date=date(2024, 12, 31), status='closed')
    fy_s_25 = FiscalYear(company_id=sub.id, year=2025, start_date=date(2025, 1, 1),
                         end_date=date(2025, 12, 31), status='open')
    db.session.add_all([fy_p_24, fy_p_25, fy_s_24, fy_s_25])
    db.session.flush()

    def _create_accounts(co, include_ic=False):
        """Create accounts once per company."""
        rev = Account(company_id=co.id, account_number='3010', name='Försäljning', account_type='revenue')
        exp = Account(company_id=co.id, account_number='5010', name='Lokalhyra', account_type='expense')
        cash = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')
        equity = Account(company_id=co.id, account_number='2081', name='Eget kapital', account_type='equity')
        accts = [rev, exp, cash, equity]
        result = {'rev': rev, 'exp': exp, 'cash': cash, 'equity': equity}
        if include_ic:
            recv = Account(company_id=co.id, account_number='1660', name='Koncernfordran', account_type='asset')
            pay = Account(company_id=co.id, account_number='2360', name='Koncernskuld', account_type='liability')
            accts.extend([recv, pay])
            result['receivable'] = recv
            result['payable'] = pay
        db.session.add_all(accts)
        db.session.flush()
        return result

    def _add_verifications(co, fy, accts, rev_amt, exp_amt, equity_amt=0,
                           receivable_amt=0, payable_amt=0):
        """Add verifications for a fiscal year."""
        ver_num = 1
        # Revenue
        v1 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                          verification_number=ver_num, verification_date=date(fy.year, 3, 1))
        db.session.add(v1)
        db.session.flush()
        db.session.add_all([
            VerificationRow(verification_id=v1.id, account_id=accts['cash'].id,
                            debit=Decimal(str(rev_amt)), credit=Decimal('0')),
            VerificationRow(verification_id=v1.id, account_id=accts['rev'].id,
                            debit=Decimal('0'), credit=Decimal(str(rev_amt))),
        ])
        ver_num += 1

        # Expense
        v2 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                          verification_number=ver_num, verification_date=date(fy.year, 3, 15))
        db.session.add(v2)
        db.session.flush()
        db.session.add_all([
            VerificationRow(verification_id=v2.id, account_id=accts['exp'].id,
                            debit=Decimal(str(exp_amt)), credit=Decimal('0')),
            VerificationRow(verification_id=v2.id, account_id=accts['cash'].id,
                            debit=Decimal('0'), credit=Decimal(str(exp_amt))),
        ])
        ver_num += 1

        if equity_amt:
            v3 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                              verification_number=ver_num, verification_date=date(fy.year, 1, 1))
            db.session.add(v3)
            db.session.flush()
            db.session.add_all([
                VerificationRow(verification_id=v3.id, account_id=accts['cash'].id,
                                debit=Decimal(str(equity_amt)), credit=Decimal('0')),
                VerificationRow(verification_id=v3.id, account_id=accts['equity'].id,
                                debit=Decimal('0'), credit=Decimal(str(equity_amt))),
            ])
            ver_num += 1

        if receivable_amt > 0 and 'receivable' in accts:
            v4 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                              verification_number=ver_num, verification_date=date(fy.year, 6, 1))
            db.session.add(v4)
            db.session.flush()
            db.session.add_all([
                VerificationRow(verification_id=v4.id, account_id=accts['receivable'].id,
                                debit=Decimal(str(receivable_amt)), credit=Decimal('0')),
                VerificationRow(verification_id=v4.id, account_id=accts['cash'].id,
                                debit=Decimal('0'), credit=Decimal(str(receivable_amt))),
            ])
            ver_num += 1

        if payable_amt > 0 and 'payable' in accts:
            v5 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                              verification_number=ver_num, verification_date=date(fy.year, 6, 1))
            db.session.add(v5)
            db.session.flush()
            db.session.add_all([
                VerificationRow(verification_id=v5.id, account_id=accts['cash'].id,
                                debit=Decimal(str(payable_amt)), credit=Decimal('0')),
                VerificationRow(verification_id=v5.id, account_id=accts['payable'].id,
                                debit=Decimal('0'), credit=Decimal(str(payable_amt))),
            ])

    # Create accounts once per company (parent with receivable, sub with payable)
    p_accts = _create_accounts(parent, include_ic=True)
    s_accts = _create_accounts(sub, include_ic=True)

    # 2024 data (for cash flow comparison)
    _add_verifications(parent, fy_p_24, p_accts, 150000, 60000, equity_amt=100000)
    _add_verifications(sub, fy_s_24, s_accts, 80000, 30000, equity_amt=50000)

    # 2025 data with intercompany balances
    _add_verifications(parent, fy_p_25, p_accts, 200000, 80000, equity_amt=100000,
                       receivable_amt=25000)
    _add_verifications(sub, fy_s_25, s_accts, 100000, 40000, equity_amt=50000,
                       payable_amt=25000)

    db.session.commit()

    return {
        'parent': parent, 'sub': sub,
        'fy_p_24': fy_p_24, 'fy_p_25': fy_p_25,
        'fy_s_24': fy_s_24, 'fy_s_25': fy_s_25,
    }


# ---------------------------------------------------------------------------
# Minority Interest
# ---------------------------------------------------------------------------

class TestMinorityInterest:
    def test_effective_ownership_direct(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Koncern', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        pct = calculate_effective_ownership(group.id, sub.id)
        assert float(pct) == 80.0

    def test_effective_ownership_chain(self, consol_data, db):
        """Parent owns 80% of Sub, Sub owns 60% of GrandSub → 48%."""
        parent = consol_data['parent']
        sub = consol_data['sub']
        grand = Company(name='Dotdot AB', org_number='556600-0052', company_type='AB')
        db.session.add(grand)
        db.session.flush()
        db.session.commit()

        group = create_consolidation_group('Kedja', parent.id)
        add_member(group.id, parent.id, 100)
        sub_member = add_member(group.id, sub.id, 80)
        add_member(group.id, grand.id, 60, parent_member_id=sub_member.id)

        pct = calculate_effective_ownership(group.id, grand.id)
        assert abs(float(pct) - 48.0) < 0.01

    def test_minority_interest_calc(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('MI Koncern', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        minority = calculate_minority_interest(group.id, 2025)
        assert len(minority) == 1
        assert minority[0]['company'].id == sub.id
        assert minority[0]['minority_pct'] == 20.0

    def test_no_minority_at_100pct(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Full Koncern', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 100)

        minority = calculate_minority_interest(group.id, 2025)
        assert len(minority) == 0

    def test_minority_in_pnl(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('PNL Koncern', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        pnl = get_consolidated_pnl(group.id, 2025)
        assert pnl['minority_pnl'] > 0
        assert len(pnl['minority_details']) == 1


# ---------------------------------------------------------------------------
# Consolidation Method
# ---------------------------------------------------------------------------

class TestConsolidationMethod:
    def test_full_consolidation_weight_100pct(self, consol_data):
        """Full consolidation includes 100% of subsidiary P&L."""
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Full', parent.id)
        add_member(group.id, parent.id, 100, consolidation_method='full')
        add_member(group.id, sub.id, 80, consolidation_method='full')

        pnl = get_consolidated_pnl(group.id, 2025)
        # Full: 200k + 100k = 300k revenue (weight = 1.0 for both)
        assert pnl['sections']['Nettoomsättning']['total'] == 300000.0

    def test_equity_method_proportional(self, consol_data):
        """Equity method includes proportional share."""
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Equity', parent.id)
        add_member(group.id, parent.id, 100, consolidation_method='full')
        add_member(group.id, sub.id, 30, consolidation_method='equity')

        pnl = get_consolidated_pnl(group.id, 2025)
        # Parent full: 200k, Sub equity 30%: 100k*0.3 = 30k → total 230k
        assert abs(pnl['sections']['Nettoomsättning']['total'] - 230000.0) < 0.01


# ---------------------------------------------------------------------------
# Intercompany Detection
# ---------------------------------------------------------------------------

class TestIntercompanyDetection:
    def test_detect_matching_balances(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('IC Koncern', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        matches = detect_intercompany_transactions(group.id, consol_data['fy_p_25'].id)
        # Should find the 25k receivable/payable match
        loan_matches = [m for m in matches if m.match_type == 'loan']
        assert len(loan_matches) >= 1
        assert any(float(m.amount) == 25000.0 for m in loan_matches)

    def test_confirm_match_creates_elimination(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Confirm', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        matches = detect_intercompany_transactions(group.id, consol_data['fy_p_25'].id)
        loan_match = next((m for m in matches if m.match_type == 'loan'), None)
        assert loan_match is not None

        confirmed = confirm_match(loan_match.id)
        assert confirmed.status == 'confirmed'
        assert confirmed.elimination_id is not None

    def test_reject_match(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Reject', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        matches = detect_intercompany_transactions(group.id, consol_data['fy_p_25'].id)
        if matches:
            rejected = reject_match(matches[0].id)
            assert rejected.status == 'rejected'

    def test_pending_matches(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Pending', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        detect_intercompany_transactions(group.id, consol_data['fy_p_25'].id)
        pending = get_pending_matches(group.id)
        assert len(pending) > 0


# ---------------------------------------------------------------------------
# Goodwill
# ---------------------------------------------------------------------------

class TestGoodwill:
    def test_register_acquisition(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('GW Koncern', parent.id)
        add_member(group.id, sub.id, 80)

        gw = register_acquisition(
            group_id=group.id, company_id=sub.id,
            acquisition_date=date(2025, 1, 1),
            purchase_price=800000, net_assets_at_acquisition=500000,
            amortization_period_months=60,
        )
        # Goodwill = 800k - (500k * 80%) = 800k - 400k = 400k
        assert float(gw.goodwill_amount) == 400000.0
        assert gw.amortization_period_months == 60

    def test_goodwill_amortization(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('GW Avskr', parent.id)
        add_member(group.id, sub.id, 80)

        gw = register_acquisition(
            group_id=group.id, company_id=sub.id,
            acquisition_date=date(2025, 1, 1),
            purchase_price=800000, net_assets_at_acquisition=500000,
            amortization_period_months=60,
        )

        amount = calculate_goodwill_amortization(gw.id, months=12)
        # Monthly: 400k / 60 = 6666.67, annual: 80000.0
        assert abs(amount - 80000.0) < 1

    def test_remaining_goodwill(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('GW Remain', parent.id)
        add_member(group.id, sub.id, 80)

        gw = register_acquisition(
            group_id=group.id, company_id=sub.id,
            acquisition_date=date(2025, 1, 1),
            purchase_price=800000, net_assets_at_acquisition=500000,
            amortization_period_months=60,
        )
        calculate_goodwill_amortization(gw.id, months=12)

        remaining = get_total_remaining_goodwill(group.id)
        assert abs(remaining - 320000.0) < 1

    def test_goodwill_entries_list(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('GW List', parent.id)
        add_member(group.id, sub.id, 80)

        register_acquisition(
            group_id=group.id, company_id=sub.id,
            acquisition_date=date(2025, 1, 1),
            purchase_price=800000, net_assets_at_acquisition=500000,
        )

        entries = get_goodwill_entries(group.id)
        assert len(entries) == 1

    def test_goodwill_in_balance_sheet(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('GW BS', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        register_acquisition(
            group_id=group.id, company_id=sub.id,
            acquisition_date=date(2025, 1, 1),
            purchase_price=800000, net_assets_at_acquisition=500000,
        )

        bs = get_consolidated_balance_sheet(group.id, 2025)
        assert bs['remaining_goodwill'] > 0


# ---------------------------------------------------------------------------
# Cash Flow
# ---------------------------------------------------------------------------

class TestCashFlow:
    def test_cash_flow_basic(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('CF Koncern', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 100)

        cf = get_consolidated_cash_flow(group.id, 2025)
        assert cf is not None
        assert 'operating' in cf
        assert 'investing' in cf
        assert 'financing' in cf
        assert 'total_cash_flow' in cf

    def test_cash_flow_no_data(self, consol_data):
        """Cash flow for year with no data should return None."""
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('CF NoPrior', parent.id)
        # Don't add any members → no data
        cf = get_consolidated_cash_flow(group.id, 2030)
        assert cf is None

    def test_cash_flow_components(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('CF Detail', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 100)

        cf = get_consolidated_cash_flow(group.id, 2025)
        assert cf['result_before_tax'] != 0
        assert cf['fy_year'] == 2025


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestEnhancedExport:
    def test_export_cash_flow(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Export CF', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 100)

        output = export_consolidated_report(group.id, 2025, 'cash_flow')
        assert output is not None
        data = output.read()
        assert len(data) > 0

    def test_export_pnl_with_minority(self, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        group = create_consolidation_group('Export MI', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 80)

        output = export_consolidated_report(group.id, 2025, 'pnl')
        assert output is not None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestConsolidationRoutes:
    def test_matches_page(self, logged_in_client, consol_data):
        parent = consol_data['parent']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = parent.id

        group = create_consolidation_group('Route Test', parent.id)
        add_member(group.id, parent.id, 100)

        resp = logged_in_client.get(f'/consolidation/groups/{group.id}/matches')
        assert resp.status_code == 200
        assert 'matchningar' in resp.data.decode().lower()

    def test_goodwill_form_page(self, logged_in_client, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = parent.id

        group = create_consolidation_group('GW Route', parent.id)
        add_member(group.id, sub.id, 80)

        resp = logged_in_client.get(f'/consolidation/groups/{group.id}/goodwill/new')
        assert resp.status_code == 200
        assert 'Registrera' in resp.data.decode()

    def test_report_cash_flow(self, logged_in_client, consol_data):
        parent = consol_data['parent']
        sub = consol_data['sub']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = parent.id

        group = create_consolidation_group('CF Route', parent.id)
        add_member(group.id, parent.id, 100)
        add_member(group.id, sub.id, 100)

        resp = logged_in_client.post(f'/consolidation/groups/{group.id}/report',
                                     data={'fiscal_year_year': 2025, 'report_type': 'cash_flow'})
        assert resp.status_code == 200
        assert 'Kassaflöde' in resp.data.decode()
