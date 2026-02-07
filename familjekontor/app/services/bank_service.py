"""Bank integration service: CSV import, auto-matching, reconciliation."""

import csv
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.bank import BankAccount, BankTransaction
from app.models.accounting import Verification, VerificationRow, Account
from app.models.audit import AuditLog


def create_bank_account(company_id, bank_name, account_number, clearing_number=None,
                        iban=None, ledger_account='1930'):
    account = BankAccount(
        company_id=company_id,
        bank_name=bank_name,
        account_number=account_number,
        clearing_number=clearing_number,
        iban=iban,
        ledger_account=ledger_account,
    )
    db.session.add(account)
    db.session.commit()
    return account


def update_bank_account(account_id, **kwargs):
    account = db.session.get(BankAccount, account_id)
    if not account:
        return None
    for key, value in kwargs.items():
        if hasattr(account, key):
            setattr(account, key, value)
    db.session.commit()
    return account


# Column mappings for different bank CSV formats
BANK_FORMATS = {
    'seb': {
        'date': 'Bokforingsdatum',
        'description': 'Text/mottagare',
        'amount': 'Belopp',
        'balance': 'Saldo',
        'delimiter': ';',
        'encoding': 'latin-1',
        'date_format': '%Y-%m-%d',
        'decimal_sep': ',',
    },
    'swedbank': {
        'date': 'Transaktionsdag',
        'description': 'Beskrivning',
        'amount': 'Belopp',
        'balance': 'Saldo',
        'delimiter': ';',
        'encoding': 'latin-1',
        'date_format': '%Y-%m-%d',
        'decimal_sep': ',',
    },
    'generic': {
        'date': 'Datum',
        'description': 'Beskrivning',
        'amount': 'Belopp',
        'balance': 'Saldo',
        'delimiter': ';',
        'encoding': 'utf-8',
        'date_format': '%Y-%m-%d',
        'decimal_sep': ',',
    },
}


def _parse_amount(value, decimal_sep=','):
    """Parse a Swedish-formatted amount string."""
    if not value:
        return Decimal('0')
    value = value.strip().replace(' ', '').replace('\xa0', '')
    if decimal_sep == ',':
        value = value.replace('.', '').replace(',', '.')
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal('0')


def _parse_date(value, date_format='%Y-%m-%d'):
    """Parse a date string."""
    from datetime import datetime
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), date_format).date()
    except ValueError:
        return None


def parse_bank_csv(file_content, bank_format='generic'):
    """Parse bank CSV file content into transaction dicts."""
    fmt = BANK_FORMATS.get(bank_format, BANK_FORMATS['generic'])
    encoding = fmt.get('encoding', 'utf-8')

    if isinstance(file_content, bytes):
        file_content = file_content.decode(encoding, errors='replace')

    reader = csv.DictReader(io.StringIO(file_content), delimiter=fmt['delimiter'])
    transactions = []

    for row in reader:
        txn_date = _parse_date(row.get(fmt['date'], ''), fmt['date_format'])
        description = row.get(fmt['description'], '').strip()
        amount = _parse_amount(row.get(fmt['amount'], ''), fmt['decimal_sep'])
        balance = _parse_amount(row.get(fmt['balance'], ''), fmt['decimal_sep'])

        if txn_date and description:
            transactions.append({
                'transaction_date': txn_date,
                'description': description,
                'amount': amount,
                'balance_after': balance,
            })

    return transactions


def import_bank_transactions(bank_account_id, transactions, company_id):
    """Import parsed transactions into database. Returns result dict."""
    batch_id = str(uuid.uuid4())[:8]
    imported = 0
    skipped = 0
    errors = []

    for txn in transactions:
        existing = BankTransaction.query.filter_by(
            bank_account_id=bank_account_id,
            transaction_date=txn['transaction_date'],
            amount=txn['amount'],
            description=txn['description'],
        ).first()

        if existing:
            skipped += 1
            continue

        try:
            bt = BankTransaction(
                bank_account_id=bank_account_id,
                company_id=company_id,
                transaction_date=txn['transaction_date'],
                description=txn['description'],
                amount=txn['amount'],
                balance_after=txn.get('balance_after'),
                reference=txn.get('reference'),
                counterpart=txn.get('counterpart'),
                import_batch=batch_id,
                status='unmatched',
            )
            db.session.add(bt)
            imported += 1
        except Exception as e:
            errors.append(str(e))

    if imported > 0:
        # Update bank account balance from last transaction
        if transactions:
            last_balance = transactions[-1].get('balance_after')
            if last_balance:
                account = db.session.get(BankAccount, bank_account_id)
                if account:
                    account.balance = last_balance

        db.session.commit()

    return {
        'imported_count': imported,
        'skipped_count': skipped,
        'errors': errors,
        'batch_id': batch_id,
    }


def auto_match_transactions(company_id, fiscal_year_id):
    """Auto-match unmatched bank transactions to verifications by amount and date.

    Strategy: match by abs(amount) within +/-3 days.
    """
    unmatched = BankTransaction.query.filter_by(
        company_id=company_id,
        status='unmatched',
    ).all()

    matched_count = 0
    for txn in unmatched:
        abs_amount = abs(txn.amount)
        date_from = txn.transaction_date - timedelta(days=3)
        date_to = txn.transaction_date + timedelta(days=3)

        # Find verifications with matching total amount in date range
        candidates = Verification.query.filter(
            Verification.company_id == company_id,
            Verification.fiscal_year_id == fiscal_year_id,
            Verification.verification_date.between(date_from, date_to),
        ).all()

        for ver in candidates:
            # Check if already matched
            already_matched = BankTransaction.query.filter_by(
                matched_verification_id=ver.id,
                status='matched',
            ).first()
            if already_matched:
                continue

            # Compare total debit/credit to transaction amount
            ver_amount = abs(ver.total_debit)
            if abs(float(abs_amount) - float(ver_amount)) < 0.01:
                txn.matched_verification_id = ver.id
                txn.status = 'matched'
                matched_count += 1
                break

    if matched_count > 0:
        db.session.commit()

    return matched_count


def manual_match_transaction(txn_id, verification_id, user_id):
    txn = db.session.get(BankTransaction, txn_id)
    if not txn:
        return False

    txn.matched_verification_id = verification_id
    txn.status = 'matched'

    audit = AuditLog(
        company_id=txn.company_id, user_id=user_id,
        action='update', entity_type='bank_transaction', entity_id=txn.id,
        old_values={'status': 'unmatched'},
        new_values={'status': 'matched', 'verification_id': verification_id},
    )
    db.session.add(audit)
    db.session.commit()
    return True


def unmatch_transaction(txn_id, user_id):
    txn = db.session.get(BankTransaction, txn_id)
    if not txn:
        return False

    old_ver_id = txn.matched_verification_id
    txn.matched_verification_id = None
    txn.status = 'unmatched'

    audit = AuditLog(
        company_id=txn.company_id, user_id=user_id,
        action='update', entity_type='bank_transaction', entity_id=txn.id,
        old_values={'status': 'matched', 'verification_id': old_ver_id},
        new_values={'status': 'unmatched'},
    )
    db.session.add(audit)
    db.session.commit()
    return True


def ignore_transaction(txn_id, user_id):
    txn = db.session.get(BankTransaction, txn_id)
    if not txn:
        return False

    old_status = txn.status
    txn.status = 'ignored'

    audit = AuditLog(
        company_id=txn.company_id, user_id=user_id,
        action='update', entity_type='bank_transaction', entity_id=txn.id,
        old_values={'status': old_status},
        new_values={'status': 'ignored'},
    )
    db.session.add(audit)
    db.session.commit()
    return True


def get_reconciliation_summary(company_id, bank_account_id=None):
    """Get reconciliation summary stats."""
    query = BankTransaction.query.filter_by(company_id=company_id)
    if bank_account_id:
        query = query.filter_by(bank_account_id=bank_account_id)

    total = query.count()
    matched = query.filter_by(status='matched').count()
    unmatched = query.filter_by(status='unmatched').count()
    ignored = query.filter_by(status='ignored').count()

    # Bank balance
    bank_balance = Decimal('0')
    accounts = BankAccount.query.filter_by(company_id=company_id, active=True)
    if bank_account_id:
        accounts = accounts.filter_by(id=bank_account_id)
    for acc in accounts.all():
        bank_balance += acc.balance or Decimal('0')

    return {
        'total': total,
        'matched': matched,
        'unmatched': unmatched,
        'ignored': ignored,
        'bank_balance': float(bank_balance),
    }


def get_unmatched_transactions(company_id, bank_account_id=None):
    query = BankTransaction.query.filter_by(
        company_id=company_id, status='unmatched'
    ).order_by(BankTransaction.transaction_date.desc())
    if bank_account_id:
        query = query.filter_by(bank_account_id=bank_account_id)
    return query.all()


def get_candidate_verifications(company_id, fiscal_year_id, amount, date_range=7):
    """Find potential matching verifications for a transaction."""
    abs_amount = abs(float(amount))
    today = date.today()
    date_from = today - timedelta(days=date_range)
    date_to = today + timedelta(days=date_range)

    candidates = Verification.query.filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
    ).order_by(Verification.verification_date.desc()).limit(50).all()

    results = []
    for ver in candidates:
        ver_amount = abs(float(ver.total_debit))
        diff = abs(ver_amount - abs_amount)
        results.append({
            'verification': ver,
            'amount': ver_amount,
            'diff': diff,
            'exact_match': diff < 0.01,
        })

    results.sort(key=lambda x: x['diff'])
    return results[:20]
