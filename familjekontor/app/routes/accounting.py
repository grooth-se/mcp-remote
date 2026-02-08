from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.audit import AuditLog
from app.forms.accounting import VerificationForm
from app.services.accounting_service import create_verification, get_trial_balance
from app.services import document_service

accounting_bp = Blueprint('accounting', __name__)


@accounting_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id:
        fy = FiscalYear.query.filter_by(
            company_id=company_id, status='open'
        ).order_by(FiscalYear.year.desc()).first()
        if fy:
            fiscal_year_id = fy.id

    verifications = []
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    if fiscal_year_id:
        verifications = Verification.query.filter_by(
            company_id=company_id, fiscal_year_id=fiscal_year_id
        ).order_by(Verification.verification_number.desc()).all()

    return render_template('accounting/index.html',
                           verifications=verifications,
                           fiscal_years=fiscal_years,
                           current_fy_id=fiscal_year_id)


@accounting_bp.route('/verification/new', methods=['GET', 'POST'])
@login_required
def new_verification():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('accounting.index'))

    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()

    if not fy:
        flash('Inget öppet räkenskapsår.', 'danger')
        return redirect(url_for('accounting.index'))

    form = VerificationForm()
    accounts = Account.query.filter_by(
        company_id=company_id, active=True
    ).order_by(Account.account_number).all()

    if request.method == 'POST' and form.validate_on_submit():
        # Parse dynamic rows from form
        rows = []
        i = 0
        while f'rows-{i}-account_id' in request.form:
            account_id = request.form.get(f'rows-{i}-account_id', type=int)
            debit = request.form.get(f'rows-{i}-debit', '0')
            credit = request.form.get(f'rows-{i}-credit', '0')
            desc = request.form.get(f'rows-{i}-description', '')

            try:
                debit_val = Decimal(debit) if debit else Decimal('0')
                credit_val = Decimal(credit) if credit else Decimal('0')
            except Exception:
                debit_val = Decimal('0')
                credit_val = Decimal('0')

            if account_id and (debit_val > 0 or credit_val > 0):
                rows.append({
                    'account_id': account_id,
                    'debit': debit_val,
                    'credit': credit_val,
                    'description': desc,
                })
            i += 1

        if not rows:
            flash('Lägg till minst en rad.', 'danger')
            return render_template('accounting/new_verification.html',
                                   form=form, accounts=accounts, fiscal_year=fy)

        try:
            ver = create_verification(
                company_id=company_id,
                fiscal_year_id=fy.id,
                verification_date=form.verification_date.data,
                description=form.description.data,
                rows=rows,
                verification_type=form.verification_type.data,
                created_by=current_user.id,
            )
            audit = AuditLog(
                company_id=company_id, user_id=current_user.id,
                action='create', entity_type='verification', entity_id=ver.id,
                new_values={'number': ver.verification_number, 'description': ver.description},
            )
            db.session.add(audit)
            db.session.commit()

            flash(f'Verifikation #{ver.verification_number} har skapats.', 'success')
            return redirect(url_for('accounting.view_verification', verification_id=ver.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('accounting/new_verification.html',
                           form=form, accounts=accounts, fiscal_year=fy)


@accounting_bp.route('/verification/<int:verification_id>')
@login_required
def view_verification(verification_id):
    ver = db.session.get(Verification, verification_id)
    if not ver:
        flash('Verifikationen hittades inte.', 'danger')
        return redirect(url_for('accounting.index'))
    return render_template('accounting/view_verification.html', verification=ver)


@accounting_bp.route('/verification/<int:verification_id>/upload-document', methods=['POST'])
@login_required
def upload_verification_document(verification_id):
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    ver = db.session.get(Verification, verification_id)
    if not ver or ver.company_id != company_id:
        flash('Verifikationen hittades inte.', 'danger')
        return redirect(url_for('accounting.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('accounting.view_verification', verification_id=verification_id))

    file = request.files.get('document')
    if not file or not file.filename:
        flash('Ingen fil vald.', 'warning')
        return redirect(url_for('accounting.view_verification', verification_id=verification_id))

    doc, error = document_service.upload_document(
        company_id=company_id,
        file=file,
        doc_type='underlag',
        description=f'Verifikation #{ver.verification_number}',
        verification_id=verification_id,
        user_id=current_user.id,
    )
    if error:
        flash(f'Uppladdning misslyckades: {error}', 'danger')
    else:
        flash('Dokument har laddats upp.', 'success')

    return redirect(url_for('accounting.view_verification', verification_id=verification_id))


@accounting_bp.route('/trial-balance')
@login_required
def trial_balance():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    balance = []
    if fiscal_year_id:
        balance = get_trial_balance(company_id, fiscal_year_id)

    return render_template('accounting/trial_balance.html',
                           balance=balance, fiscal_years=fiscal_years,
                           current_fy_id=fiscal_year_id)
