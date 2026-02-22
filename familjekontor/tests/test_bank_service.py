"""Tests for bank integration service (Phase 4B)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.bank import BankAccount, BankTransaction
from app.models.user import User
from app.services.bank_service import (
    create_bank_account, parse_bank_csv, import_bank_transactions,
    auto_match_transactions, manual_match_transaction, unmatch_transaction,
    ignore_transaction, get_reconciliation_summary, get_unmatched_transactions,
    get_candidate_verifications,
)


@pytest.fixture
def bank_company(db):
    """Company with FY, bank account (1930), and a verification for matching."""
    co = Company(name='Bank AB', org_number='556600-0010', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    cash = Account(company_id=co.id, account_number='1930',
                   name='Företagskonto', account_type='asset')
    expense = Account(company_id=co.id, account_number='5010',
                      name='Lokalhyra', account_type='expense')
    db.session.add_all([cash, expense])
    db.session.flush()

    # A verification worth 5000
    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 3, 15),
                     description='Hyra mars')
    db.session.add(v)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v.id, account_id=expense.id,
                        debit=Decimal('5000'), credit=Decimal('0')),
        VerificationRow(verification_id=v.id, account_id=cash.id,
                        debit=Decimal('0'), credit=Decimal('5000')),
    ])

    user = User(username='bankuser', email='bank@test.com', role='admin')
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()

    return {'company': co, 'fy': fy, 'cash': cash, 'expense': expense,
            'verification': v, 'user': user}


class TestBankAccount:
    def test_create_account(self, bank_company):
        co = bank_company['company']
        acc = create_bank_account(co.id, 'SEB', '12345678901', clearing_number='5001')
        assert acc.id is not None
        assert acc.bank_name == 'SEB'
        assert acc.ledger_account == '1930'


class TestCSVParsing:
    def test_parse_seb_csv(self):
        csv = 'Bokförd;Valutadatum;Text;Typ;Insättningar;Uttag;Bokfört saldo\n' \
              '2025-03-15;2025-03-15;Hyra;Betalning (bg/pg);;-5 000,00;95 000,00\n'
        txns = parse_bank_csv(csv, 'seb')
        assert len(txns) == 1
        assert txns[0]['transaction_date'] == date(2025, 3, 15)
        assert txns[0]['amount'] == Decimal('-5000.00')

    def test_parse_seb_csv_deposit(self):
        csv = 'Bokförd;Valutadatum;Text;Typ;Insättningar;Uttag;Bokfört saldo\n' \
              '2025-03-20;2025-03-20;Kundbetalning;Bankgirobetalning;10 000,00;;105 000,00\n'
        txns = parse_bank_csv(csv, 'seb')
        assert len(txns) == 1
        assert txns[0]['amount'] == Decimal('10000.00')

    def test_parse_seb_csv_with_bom(self):
        csv = '\ufeffBokförd;Valutadatum;Text;Typ;Insättningar;Uttag;Bokfört saldo\n' \
              '2025-03-15;2025-03-15;Hyra;Annan;;-5 000,00;95 000,00\n'
        txns = parse_bank_csv(csv, 'seb')
        assert len(txns) == 1

    def test_parse_swedbank_csv(self):
        csv = 'Transaktionsdag;Beskrivning;Belopp;Saldo\n' \
              '2025-03-10;Lön;25 000,00;125 000,00\n'
        txns = parse_bank_csv(csv, 'swedbank')
        assert len(txns) == 1
        assert txns[0]['description'] == 'Lön'
        assert txns[0]['amount'] == Decimal('25000.00')

    def test_parse_generic_csv(self):
        csv = 'Datum;Beskrivning;Belopp;Saldo\n' \
              '2025-03-01;Inbetalning;10 000,00;110 000,00\n' \
              '2025-03-02;Utbetalning;-2 000,00;108 000,00\n'
        txns = parse_bank_csv(csv, 'generic')
        assert len(txns) == 2

    def test_parse_empty_csv(self):
        csv = 'Datum;Beskrivning;Belopp;Saldo\n'
        txns = parse_bank_csv(csv, 'generic')
        assert len(txns) == 0


class TestImport:
    def test_import_transactions(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990001')

        txns = [
            {'transaction_date': date(2025, 3, 1), 'description': 'Test1',
             'amount': Decimal('1000'), 'balance_after': Decimal('101000')},
            {'transaction_date': date(2025, 3, 2), 'description': 'Test2',
             'amount': Decimal('-500'), 'balance_after': Decimal('100500')},
        ]
        result = import_bank_transactions(ba.id, txns, co.id)
        assert result['imported_count'] == 2
        assert result['skipped_count'] == 0

    def test_import_duplicates_skipped(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990002')

        txns = [{'transaction_date': date(2025, 3, 1), 'description': 'Dup',
                 'amount': Decimal('1000'), 'balance_after': Decimal('101000')}]
        import_bank_transactions(ba.id, txns, co.id)
        result = import_bank_transactions(ba.id, txns, co.id)
        assert result['imported_count'] == 0
        assert result['skipped_count'] == 1


class TestMatching:
    def test_auto_match(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990003')

        # Transaction matching the 5000 verification on same date
        txn = BankTransaction(
            bank_account_id=ba.id, company_id=co.id,
            transaction_date=date(2025, 3, 15), description='Hyra',
            amount=Decimal('-5000'), status='unmatched',
        )
        db.session.add(txn)
        db.session.commit()

        matched = auto_match_transactions(co.id, bank_company['fy'].id)
        assert matched == 1
        db.session.refresh(txn)
        assert txn.status == 'matched'

    def test_manual_match(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990004')
        txn = BankTransaction(
            bank_account_id=ba.id, company_id=co.id,
            transaction_date=date(2025, 3, 20), description='Manual',
            amount=Decimal('-5000'), status='unmatched',
        )
        db.session.add(txn)
        db.session.commit()

        result = manual_match_transaction(txn.id, bank_company['verification'].id,
                                          bank_company['user'].id)
        assert result is True
        db.session.refresh(txn)
        assert txn.status == 'matched'

    def test_unmatch(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990005')
        txn = BankTransaction(
            bank_account_id=ba.id, company_id=co.id,
            transaction_date=date(2025, 3, 20), description='Unmatch',
            amount=Decimal('-5000'), status='matched',
            matched_verification_id=bank_company['verification'].id,
        )
        db.session.add(txn)
        db.session.commit()

        result = unmatch_transaction(txn.id, bank_company['user'].id)
        assert result is True
        db.session.refresh(txn)
        assert txn.status == 'unmatched'

    def test_ignore(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990006')
        txn = BankTransaction(
            bank_account_id=ba.id, company_id=co.id,
            transaction_date=date(2025, 3, 20), description='Ignore',
            amount=Decimal('-100'), status='unmatched',
        )
        db.session.add(txn)
        db.session.commit()

        result = ignore_transaction(txn.id, bank_company['user'].id)
        assert result is True
        db.session.refresh(txn)
        assert txn.status == 'ignored'


class TestReconciliation:
    def test_summary_counts(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990007')
        for i, status in enumerate(['unmatched', 'matched', 'ignored']):
            txn = BankTransaction(
                bank_account_id=ba.id, company_id=co.id,
                transaction_date=date(2025, 3, 1 + i), description=f'Txn {i}',
                amount=Decimal(str((i + 1) * 1000)), status=status,
            )
            db.session.add(txn)
        db.session.commit()

        summary = get_reconciliation_summary(co.id)
        assert summary['total'] == 3
        assert summary['matched'] == 1
        assert summary['unmatched'] == 1
        assert summary['ignored'] == 1

    def test_unmatched_list(self, bank_company, db):
        co = bank_company['company']
        ba = create_bank_account(co.id, 'SEB', '99990008')
        txn = BankTransaction(
            bank_account_id=ba.id, company_id=co.id,
            transaction_date=date(2025, 3, 5), description='Unmatched',
            amount=Decimal('500'), status='unmatched',
        )
        db.session.add(txn)
        db.session.commit()

        unmatched = get_unmatched_transactions(co.id)
        assert len(unmatched) >= 1
        descs = [t.description for t in unmatched]
        assert 'Unmatched' in descs

    def test_candidate_verifications(self, bank_company):
        co = bank_company['company']
        fy = bank_company['fy']
        candidates = get_candidate_verifications(co.id, fy.id, Decimal('5000'))
        assert len(candidates) >= 1
        assert candidates[0]['exact_match'] is True
