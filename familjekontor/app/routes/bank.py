from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app.extensions import db
from app.models.bank import BankAccount, BankTransaction
from app.models.accounting import FiscalYear
from app.forms.bank import BankAccountForm, BankImportForm, ManualMatchForm
from app.services import bank_service

bank_bp = Blueprint('bank', __name__)


def _get_active_context():
    company_id = session.get('active_company_id')
    if not company_id:
        return None, None, None
    from app.models.company import Company
    company = db.session.get(Company, company_id)
    active_fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()
    return company_id, company, active_fy


@bank_bp.route('/')
@login_required
def index():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    summary = bank_service.get_reconciliation_summary(company_id)
    accounts = BankAccount.query.filter_by(company_id=company_id, active=True).all()
    return render_template('bank/index.html', summary=summary, accounts=accounts)


@bank_bp.route('/accounts')
@login_required
def accounts():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    accounts = BankAccount.query.filter_by(company_id=company_id).order_by(BankAccount.bank_name).all()
    return render_template('bank/accounts.html', accounts=accounts)


@bank_bp.route('/accounts/new', methods=['GET', 'POST'])
@login_required
def new_account():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    form = BankAccountForm()
    if form.validate_on_submit():
        bank_service.create_bank_account(
            company_id=company_id,
            bank_name=form.bank_name.data,
            account_number=form.account_number.data,
            clearing_number=form.clearing_number.data,
            iban=form.iban.data,
            currency=form.currency.data,
            ledger_account=form.ledger_account.data,
        )
        flash('Bankkonto har skapats.', 'success')
        return redirect(url_for('bank.accounts'))

    return render_template('bank/account_form.html', form=form, title='Nytt bankkonto')


@bank_bp.route('/accounts/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    account = db.session.get(BankAccount, account_id)
    if not account or account.company_id != company_id:
        flash('Bankkonto hittades inte.', 'danger')
        return redirect(url_for('bank.accounts'))

    form = BankAccountForm(obj=account)
    if form.validate_on_submit():
        bank_service.update_bank_account(
            account_id,
            bank_name=form.bank_name.data,
            account_number=form.account_number.data,
            clearing_number=form.clearing_number.data,
            iban=form.iban.data,
            currency=form.currency.data,
            ledger_account=form.ledger_account.data,
        )
        flash('Bankkonto har uppdaterats.', 'success')
        return redirect(url_for('bank.accounts'))

    return render_template('bank/account_form.html', form=form, title='Redigera bankkonto')


@bank_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    form = BankImportForm()
    accounts = BankAccount.query.filter_by(company_id=company_id, active=True).all()
    form.bank_account_id.choices = [(a.id, f'{a.bank_name} - {a.account_number}') for a in accounts]

    result = None
    if form.validate_on_submit():
        file_content = form.file.data.read()
        transactions = bank_service.parse_bank_csv(file_content, form.bank_format.data)
        if transactions:
            result = bank_service.import_bank_transactions(
                form.bank_account_id.data, transactions, company_id
            )
            flash(f'Importerade {result["imported_count"]} transaktioner, '
                  f'{result["skipped_count"]} redan importerade.', 'success')
        else:
            flash('Inga transaktioner kunde tolkas från filen.', 'warning')

    return render_template('bank/import.html', form=form, result=result)


@bank_bp.route('/auto-match', methods=['POST'])
@login_required
def auto_match():
    company_id, company, active_fy = _get_active_context()
    if not company_id or not active_fy:
        flash('Välj ett företag med aktivt räkenskapsår.', 'warning')
        return redirect(url_for('bank.index'))

    matched = bank_service.auto_match_transactions(company_id, active_fy.id)
    flash(f'Automatisk matchning: {matched} transaktioner matchades.', 'success')
    return redirect(url_for('bank.reconciliation'))


@bank_bp.route('/reconciliation')
@login_required
def reconciliation():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    status_filter = request.args.get('status', 'unmatched')
    if status_filter not in ('unmatched', 'matched', 'ignored'):
        status_filter = 'unmatched'
    bank_account_id = request.args.get('account_id', type=int)

    query = BankTransaction.query.filter_by(company_id=company_id)
    if bank_account_id:
        query = query.filter_by(bank_account_id=bank_account_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    transactions = query.order_by(BankTransaction.transaction_date.desc()).all()
    accounts = BankAccount.query.filter_by(company_id=company_id, active=True).all()
    summary = bank_service.get_reconciliation_summary(company_id, bank_account_id)

    return render_template('bank/reconciliation.html',
                           transactions=transactions, accounts=accounts,
                           summary=summary, status_filter=status_filter,
                           bank_account_id=bank_account_id)


@bank_bp.route('/transactions/<int:txn_id>/match', methods=['GET', 'POST'])
@login_required
def match_transaction(txn_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    txn = db.session.get(BankTransaction, txn_id)
    if not txn or txn.company_id != company_id:
        flash('Transaktion hittades inte.', 'danger')
        return redirect(url_for('bank.reconciliation'))

    form = ManualMatchForm()

    candidates = []
    if active_fy:
        candidates = bank_service.get_candidate_verifications(
            company_id, active_fy.id, txn.amount
        )
        form.verification_id.choices = [
            (c['verification'].id,
             f"#{c['verification'].verification_number} - {c['verification'].verification_date} "
             f"- {c['amount']:.2f} kr - {c['verification'].description or ''}")
            for c in candidates
        ]

    if form.validate_on_submit():
        bank_service.manual_match_transaction(txn_id, form.verification_id.data, current_user.id)
        flash('Transaktionen har matchats.', 'success')
        return redirect(url_for('bank.reconciliation'))

    return render_template('bank/match.html', txn=txn, form=form, candidates=candidates)


@bank_bp.route('/transactions/<int:txn_id>/unmatch', methods=['POST'])
@login_required
def unmatch_transaction(txn_id):
    company_id = session.get('active_company_id')
    txn = db.session.get(BankTransaction, txn_id)
    if not txn or txn.company_id != company_id:
        flash('Transaktion hittades inte.', 'danger')
        return redirect(url_for('bank.reconciliation'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('bank.reconciliation'))
    bank_service.unmatch_transaction(txn_id, current_user.id)
    flash('Matchning har tagits bort.', 'success')
    return redirect(url_for('bank.reconciliation'))


@bank_bp.route('/transactions/<int:txn_id>/ignore', methods=['POST'])
@login_required
def ignore_transaction(txn_id):
    company_id = session.get('active_company_id')
    txn = db.session.get(BankTransaction, txn_id)
    if not txn or txn.company_id != company_id:
        flash('Transaktion hittades inte.', 'danger')
        return redirect(url_for('bank.reconciliation'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('bank.reconciliation'))
    bank_service.ignore_transaction(txn_id, current_user.id)
    flash('Transaktionen har ignorerats.', 'success')
    return redirect(url_for('bank.reconciliation'))
