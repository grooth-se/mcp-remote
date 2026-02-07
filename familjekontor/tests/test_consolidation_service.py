"""Tests for consolidation service (Phase 4E) — includes bug fix verification."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.consolidation_service import (
    create_consolidation_group, add_member, remove_member,
    get_consolidated_pnl, get_consolidated_balance_sheet,
    create_elimination, export_consolidated_report,
)


@pytest.fixture
def consolidation_setup(db):
    """Two companies, FYs (same year), accounts, and verifications in each."""
    co1 = Company(name='Moder AB', org_number='556600-0040', company_type='AB')
    co2 = Company(name='Dotter AB', org_number='556600-0041', company_type='AB')
    db.session.add_all([co1, co2])
    db.session.flush()

    fy1 = FiscalYear(company_id=co1.id, year=2025, start_date=date(2025, 1, 1),
                     end_date=date(2025, 12, 31), status='open')
    fy2 = FiscalYear(company_id=co2.id, year=2025, start_date=date(2025, 1, 1),
                     end_date=date(2025, 12, 31), status='open')
    db.session.add_all([fy1, fy2])
    db.session.flush()

    def _add_accounts_and_verifications(co, fy, rev_amount, exp_amount, asset_amount):
        rev = Account(company_id=co.id, account_number='3010',
                      name='Försäljning', account_type='revenue')
        exp = Account(company_id=co.id, account_number='5010',
                      name='Lokalhyra', account_type='expense')
        cash = Account(company_id=co.id, account_number='1930',
                       name='Företagskonto', account_type='asset')
        equity = Account(company_id=co.id, account_number='2081',
                         name='Eget kapital', account_type='equity')
        db.session.add_all([rev, exp, cash, equity])
        db.session.flush()

        # Revenue verification
        v1 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                          verification_number=1, verification_date=date(2025, 3, 1))
        db.session.add(v1)
        db.session.flush()
        db.session.add_all([
            VerificationRow(verification_id=v1.id, account_id=cash.id,
                            debit=rev_amount, credit=Decimal('0')),
            VerificationRow(verification_id=v1.id, account_id=rev.id,
                            debit=Decimal('0'), credit=rev_amount),
        ])

        # Expense verification
        v2 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                          verification_number=2, verification_date=date(2025, 3, 15))
        db.session.add(v2)
        db.session.flush()
        db.session.add_all([
            VerificationRow(verification_id=v2.id, account_id=exp.id,
                            debit=exp_amount, credit=Decimal('0')),
            VerificationRow(verification_id=v2.id, account_id=cash.id,
                            debit=Decimal('0'), credit=exp_amount),
        ])

        return {'revenue': rev, 'expense': exp, 'cash': cash, 'equity': equity}

    accs1 = _add_accounts_and_verifications(co1, fy1, Decimal('200000'),
                                            Decimal('80000'), Decimal('120000'))
    accs2 = _add_accounts_and_verifications(co2, fy2, Decimal('100000'),
                                            Decimal('40000'), Decimal('60000'))
    db.session.commit()

    return {'co1': co1, 'co2': co2, 'fy1': fy1, 'fy2': fy2,
            'accounts1': accs1, 'accounts2': accs2}


class TestGroup:
    def test_create_group(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        group = create_consolidation_group('Test Koncern', co1.id, 'Test')
        assert group.id is not None
        assert group.name == 'Test Koncern'

    def test_add_member(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        group = create_consolidation_group('Koncern', co1.id)
        member = add_member(group.id, co2.id, ownership_pct=100)
        assert member.id is not None
        assert float(member.ownership_pct) == 100.0

    def test_add_member_update_pct(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        group = create_consolidation_group('Koncern', co1.id)
        add_member(group.id, co2.id, ownership_pct=100)
        updated = add_member(group.id, co2.id, ownership_pct=80)
        assert float(updated.ownership_pct) == 80.0

    def test_remove_member(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        group = create_consolidation_group('Koncern', co1.id)
        add_member(group.id, co2.id)
        result = remove_member(group.id, co2.id)
        assert result is True

    def test_remove_nonexistent(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        group = create_consolidation_group('Koncern', co1.id)
        result = remove_member(group.id, 9999)
        assert result is False


class TestReports:
    def test_consolidated_pnl(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        group = create_consolidation_group('Koncern', co1.id)
        add_member(group.id, co1.id, 100)
        add_member(group.id, co2.id, 100)

        pnl = get_consolidated_pnl(group.id, 2025)
        assert pnl is not None
        # co1: revenue 200k, expense 80k. co2: revenue 100k, expense 40k.
        # gross_profit = 300k (all revenue, no COGS)
        assert pnl['sections']['Nettoomsättning']['total'] == 300000.0
        assert pnl['sections']['Övriga externa kostnader']['total'] == 120000.0
        # operating = 300k - 120k = 180k
        assert pnl['operating_result'] == 180000.0

    def test_consolidated_balance(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        group = create_consolidation_group('BR Koncern', co1.id)
        add_member(group.id, co1.id, 100)
        add_member(group.id, co2.id, 100)

        bs = get_consolidated_balance_sheet(group.id, 2025)
        assert bs is not None
        # Cash: co1 = 200k-80k = 120k, co2 = 100k-40k = 60k -> 180k total
        assert bs['sections']['Omsättningstillgångar']['total'] == 180000.0

    def test_pnl_no_members(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        group = create_consolidation_group('Tom Koncern', co1.id)
        pnl = get_consolidated_pnl(group.id, 2025)
        assert pnl is not None
        assert pnl['gross_profit'] == 0


class TestEliminations:
    def test_create_elimination(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        fy1 = consolidation_setup['fy1']
        group = create_consolidation_group('Elim Koncern', co1.id)
        add_member(group.id, co1.id)
        add_member(group.id, co2.id)

        elim = create_elimination(
            group_id=group.id, fiscal_year_id=fy1.id,
            from_company_id=co1.id, to_company_id=co2.id,
            account_number='3010', amount=Decimal('50000'),
            description='Internförsäljning',
        )
        assert elim.id is not None
        assert float(elim.amount) == 50000.0


class TestExport:
    def test_export_pnl_excel(self, consolidation_setup):
        co1 = consolidation_setup['co1']
        co2 = consolidation_setup['co2']
        group = create_consolidation_group('Export Koncern', co1.id)
        add_member(group.id, co1.id, 100)
        add_member(group.id, co2.id, 100)

        output = export_consolidated_report(group.id, 2025, 'pnl')
        assert output is not None
        data = output.read()
        assert len(data) > 0
