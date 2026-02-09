"""Tests for year-end closing (årsbokslut) in accounting_service."""

from datetime import date
from decimal import Decimal
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.accounting_service import (
    create_verification,
    preview_closing,
    close_fiscal_year,
    get_trial_balance,
)


@pytest.fixture
def company(db):
    c = Company(name='TestAB', org_number='5566778899', company_type='AB')
    db.session.add(c)
    db.session.flush()
    return c


@pytest.fixture
def fiscal_year(db, company):
    fy = FiscalYear(
        company_id=company.id,
        year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.flush()
    return fy


@pytest.fixture
def accounts(db, company):
    """Create a set of accounts: assets, liabilities, equity, revenue, expenses."""
    accs = {}
    specs = [
        ('1930', 'Företagskonto', 'asset'),
        ('1510', 'Kundfordringar', 'asset'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('2099', 'Årets resultat', 'equity'),
        ('2081', 'Aktiekapital', 'equity'),
        ('3010', 'Försäljning varor', 'revenue'),
        ('3040', 'Försäljning tjänster', 'revenue'),
        ('4010', 'Inköp varor', 'expense'),
        ('5010', 'Lokalhyra', 'expense'),
        ('6110', 'Kontorsmaterial', 'expense'),
    ]
    for number, name, atype in specs:
        a = Account(company_id=company.id, account_number=number, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accs[number] = a
    return accs


@pytest.fixture
def sample_transactions(db, company, fiscal_year, accounts):
    """Create sample transactions for testing closing.

    Revenue: 3010 credit 100,000  (balance = -100,000)
             3040 credit 50,000   (balance = -50,000)
    Expenses: 4010 debit 40,000   (balance = +40,000)
              5010 debit 20,000   (balance = +20,000)
              6110 debit 10,000   (balance = +10,000)
    Net result: 150,000 - 70,000 = 80,000 profit

    Bank (1930) receives the cash.
    """
    # Sales verification
    create_verification(
        company.id, fiscal_year.id, date(2025, 3, 15),
        'Försäljning', [
            {'account_id': accounts['1930'].id, 'debit': 100000, 'credit': 0},
            {'account_id': accounts['3010'].id, 'debit': 0, 'credit': 100000},
        ],
    )
    create_verification(
        company.id, fiscal_year.id, date(2025, 6, 15),
        'Tjänsteintäkt', [
            {'account_id': accounts['1930'].id, 'debit': 50000, 'credit': 0},
            {'account_id': accounts['3040'].id, 'debit': 0, 'credit': 50000},
        ],
    )
    # Expense verifications
    create_verification(
        company.id, fiscal_year.id, date(2025, 4, 1),
        'Inköp', [
            {'account_id': accounts['4010'].id, 'debit': 40000, 'credit': 0},
            {'account_id': accounts['1930'].id, 'debit': 0, 'credit': 40000},
        ],
    )
    create_verification(
        company.id, fiscal_year.id, date(2025, 7, 1),
        'Hyra', [
            {'account_id': accounts['5010'].id, 'debit': 20000, 'credit': 0},
            {'account_id': accounts['1930'].id, 'debit': 0, 'credit': 20000},
        ],
    )
    create_verification(
        company.id, fiscal_year.id, date(2025, 9, 1),
        'Kontorsmaterial', [
            {'account_id': accounts['6110'].id, 'debit': 10000, 'credit': 0},
            {'account_id': accounts['1930'].id, 'debit': 0, 'credit': 10000},
        ],
    )


class TestPreviewClosing:
    def test_preview_closing(self, db, company, fiscal_year, accounts, sample_transactions):
        data = preview_closing(company.id, fiscal_year.id)

        assert data['fiscal_year'].id == fiscal_year.id
        assert data['year_result'] == pytest.approx(80000.0)
        assert data['revenue'] == pytest.approx(150000.0)
        assert data['expenses'] == pytest.approx(70000.0)

        # Balance accounts should include 1930 (bank)
        ba_numbers = {a['account_number'] for a in data['balance_accounts']}
        assert '1930' in ba_numbers

        # Result accounts should include all revenue and expense accounts
        ra_numbers = {a['account_number'] for a in data['result_accounts']}
        assert '3010' in ra_numbers
        assert '4010' in ra_numbers
        assert '5010' in ra_numbers
        assert '6110' in ra_numbers

    def test_year_result_calculation(self, db, company, fiscal_year, accounts, sample_transactions):
        """Year result should be correct: revenue 150k - expenses 70k = 80k profit."""
        data = preview_closing(company.id, fiscal_year.id)
        assert data['year_result'] == pytest.approx(80000.0)


class TestCloseFiscalYear:
    def test_close_fiscal_year(self, db, company, fiscal_year, accounts, sample_transactions):
        result = close_fiscal_year(company.id, fiscal_year.id)

        # FY should be closed
        db.session.refresh(fiscal_year)
        assert fiscal_year.status == 'closed'

        # Should have created closing and opening verifications
        assert result['closing_verification'] is not None
        assert result['opening_verification'] is not None
        assert result['year_result'] == pytest.approx(80000.0)

    def test_close_creates_next_fy(self, db, company, fiscal_year, accounts, sample_transactions):
        result = close_fiscal_year(company.id, fiscal_year.id)

        next_fy = result['next_fiscal_year']
        assert next_fy.year == 2026
        assert next_fy.start_date == date(2026, 1, 1)
        assert next_fy.end_date == date(2026, 12, 31)
        assert next_fy.status == 'open'

    def test_close_uses_existing_next_fy(self, db, company, fiscal_year, accounts, sample_transactions):
        """If next FY already exists, don't create a duplicate."""
        existing = FiscalYear(
            company_id=company.id, year=2026,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        db.session.add(existing)
        db.session.flush()

        result = close_fiscal_year(company.id, fiscal_year.id)
        assert result['next_fiscal_year'].id == existing.id

    def test_close_already_closed_raises(self, db, company, fiscal_year, accounts, sample_transactions):
        close_fiscal_year(company.id, fiscal_year.id)
        with pytest.raises(ValueError, match='redan stängt'):
            close_fiscal_year(company.id, fiscal_year.id)

    def test_closing_verification_balanced(self, db, company, fiscal_year, accounts, sample_transactions):
        result = close_fiscal_year(company.id, fiscal_year.id)
        closing_ver = result['closing_verification']
        assert closing_ver.is_balanced

    def test_opening_balances_correct(self, db, company, fiscal_year, accounts, sample_transactions):
        """Opening balances in next FY should match closing balances."""
        result = close_fiscal_year(company.id, fiscal_year.id)
        next_fy = result['next_fiscal_year']

        # Get trial balance for next FY (only opening balances)
        tb = get_trial_balance(company.id, next_fy.id)
        tb_by_num = {t['account_number']: t for t in tb}

        # Bank: received 150k, paid 70k = 80k debit balance
        assert '1930' in tb_by_num
        assert tb_by_num['1930']['balance'] == pytest.approx(80000.0)

        # 2099 should have the year result as credit balance (negative in debit-credit)
        assert '2099' in tb_by_num
        assert tb_by_num['2099']['balance'] == pytest.approx(-80000.0)

    def test_opening_verification_balanced(self, db, company, fiscal_year, accounts, sample_transactions):
        result = close_fiscal_year(company.id, fiscal_year.id)
        opening_ver = result['opening_verification']
        assert opening_ver.is_balanced

    def test_result_accounts_zeroed(self, db, company, fiscal_year, accounts, sample_transactions):
        """After closing, result accounts should have zero balance."""
        close_fiscal_year(company.id, fiscal_year.id)
        tb = get_trial_balance(company.id, fiscal_year.id)
        for t in tb:
            if t['account_number'][0] in ('3', '4', '5', '6', '7', '8'):
                assert abs(t['balance']) < 0.01, f"Account {t['account_number']} not zeroed: {t['balance']}"


class TestFiscalYearLock:
    def test_create_verification_blocked_on_closed_fy(self, db, company, fiscal_year, accounts, sample_transactions):
        close_fiscal_year(company.id, fiscal_year.id)

        with pytest.raises(ValueError, match='stängt räkenskapsår'):
            create_verification(
                company.id, fiscal_year.id, date(2025, 12, 31),
                'Should fail', [
                    {'account_id': accounts['1930'].id, 'debit': 100, 'credit': 0},
                    {'account_id': accounts['4010'].id, 'debit': 0, 'credit': 100},
                ],
            )
