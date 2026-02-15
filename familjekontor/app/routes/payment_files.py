from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, send_file, jsonify,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.bank import BankAccount
from app.models.payment_file import PaymentFile, PaymentInstruction
from app.forms.payment_file import PaymentBatchForm
from app.services.payment_file_service import (
    get_payable_invoices, create_payment_batch, get_batch_summary,
    generate_payment_file, mark_batch_uploaded, confirm_batch_paid,
    cancel_batch, determine_payment_method,
)

payment_files_bp = Blueprint('payment_files', __name__)

STATUS_LABELS = {
    'draft': 'Utkast',
    'generated': 'Genererad',
    'uploaded': 'Uppladdad',
    'confirmed': 'Bekräftad',
    'cancelled': 'Avbruten',
}


@payment_files_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    query = PaymentFile.query.filter_by(company_id=company_id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    query = query.order_by(PaymentFile.created_at.desc())
    pagination = query.paginate(page=page, per_page=20, error_out=False)

    # Summary
    all_batches = PaymentFile.query.filter_by(company_id=company_id).all()
    summary = {
        'total_count': len(all_batches),
        'total_amount': sum(float(b.total_amount or 0) for b in all_batches if b.status != 'cancelled'),
        'pending_count': sum(1 for b in all_batches if b.status in ('draft', 'generated', 'uploaded')),
    }

    return render_template('payment_files/index.html',
                           pagination=pagination,
                           summary=summary,
                           status_filter=status_filter,
                           status_labels=STATUS_LABELS)


@payment_files_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_batch():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet att skapa betalningsbatcher.', 'danger')
        return redirect(url_for('payment_files.index'))

    form = PaymentBatchForm()
    bank_accounts = BankAccount.query.filter_by(
        company_id=company_id, active=True
    ).order_by(BankAccount.bank_name).all()
    form.bank_account_id.choices = [
        (ba.id, f'{ba.bank_name} - {ba.account_number}') for ba in bank_accounts
    ]

    invoices = get_payable_invoices(company_id)

    # Annotate invoices with payment method info
    invoice_data = []
    for inv in invoices:
        method, account, bic = determine_payment_method(inv.supplier)
        invoice_data.append({
            'invoice': inv,
            'has_payment_details': method is not None,
            'payment_method': method or '',
            'payment_account': account or '',
        })

    if form.validate_on_submit():
        raw_ids = form.invoice_ids.data or ''
        try:
            invoice_ids = [int(x.strip()) for x in raw_ids.split(',') if x.strip()]
        except ValueError:
            flash('Ogiltigt faktura-ID format.', 'danger')
            return render_template('payment_files/new_batch.html',
                                   form=form, invoice_data=invoice_data)

        if not invoice_ids:
            flash('Välj minst en faktura.', 'warning')
            return render_template('payment_files/new_batch.html',
                                   form=form, invoice_data=invoice_data)

        pf, errors = create_payment_batch(
            company_id=company_id,
            bank_account_id=form.bank_account_id.data,
            invoice_ids=invoice_ids,
            execution_date=form.execution_date.data,
            file_format=form.file_format.data,
            created_by=current_user.id,
        )

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('payment_files/new_batch.html',
                                   form=form, invoice_data=invoice_data)

        flash(f'Betalningsbatch {pf.batch_reference} skapad med {pf.number_of_transactions} betalningar.', 'success')
        return redirect(url_for('payment_files.view_batch', batch_id=pf.id))

    return render_template('payment_files/new_batch.html',
                           form=form, invoice_data=invoice_data)


@payment_files_bp.route('/<int:batch_id>')
@login_required
def view_batch(batch_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    summary = get_batch_summary(batch_id)
    return render_template('payment_files/view_batch.html',
                           batch=pf, summary=summary, status_labels=STATUS_LABELS)


@payment_files_bp.route('/<int:batch_id>/generate', methods=['POST'])
@login_required
def generate_file(batch_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    filepath = generate_payment_file(batch_id)
    if filepath:
        flash('Betalningsfil genererad.', 'success')
    else:
        flash('Kunde inte generera betalningsfil.', 'danger')

    return redirect(url_for('payment_files.view_batch', batch_id=batch_id))


@payment_files_bp.route('/<int:batch_id>/download')
@login_required
def download_file(batch_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    if not pf.file_path:
        flash('Ingen fil har genererats ännu.', 'warning')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    if pf.file_format == 'pain001':
        mimetype = 'application/xml'
        filename = f'{pf.batch_reference}.xml'
    else:
        mimetype = 'text/plain'
        filename = f'{pf.batch_reference}.txt'

    return send_file(pf.file_path, mimetype=mimetype, as_attachment=True,
                     download_name=filename)


@payment_files_bp.route('/<int:batch_id>/mark-uploaded', methods=['POST'])
@login_required
def mark_uploaded(batch_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    if mark_batch_uploaded(batch_id, current_user.id):
        flash('Batch markerad som uppladdad till banken.', 'success')
    else:
        flash('Kunde inte uppdatera status.', 'danger')

    return redirect(url_for('payment_files.view_batch', batch_id=batch_id))


@payment_files_bp.route('/<int:batch_id>/confirm', methods=['POST'])
@login_required
def confirm_paid(batch_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    success, errors = confirm_batch_paid(batch_id, current_user.id)
    if success:
        flash('Batch bekräftad — alla fakturor markerade som betalda.', 'success')
    for err in errors:
        flash(err, 'warning')

    return redirect(url_for('payment_files.view_batch', batch_id=batch_id))


@payment_files_bp.route('/<int:batch_id>/cancel', methods=['POST'])
@login_required
def cancel(batch_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    if cancel_batch(batch_id, current_user.id):
        flash('Batch avbruten.', 'success')
    else:
        flash('Kunde inte avbryta batch.', 'danger')

    return redirect(url_for('payment_files.view_batch', batch_id=batch_id))


@payment_files_bp.route('/api/payable-invoices')
@login_required
def api_payable_invoices():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify([])

    invoices = get_payable_invoices(company_id)
    result = []
    for inv in invoices:
        method, account, bic = determine_payment_method(inv.supplier)
        result.append({
            'id': inv.id,
            'supplier': inv.supplier.name,
            'invoice_number': inv.invoice_number,
            'due_date': inv.due_date.isoformat() if inv.due_date else None,
            'total_amount': float(inv.total_amount) if inv.total_amount else 0,
            'currency': inv.currency or 'SEK',
            'payment_method': method,
            'payment_account': account,
            'has_payment_details': method is not None,
        })

    return jsonify(result)


@payment_files_bp.route('/<int:batch_id>/remove/<int:instruction_id>', methods=['POST'])
@login_required
def remove_instruction(batch_id, instruction_id):
    company_id = session.get('active_company_id')
    pf = db.session.get(PaymentFile, batch_id)
    if not pf or pf.company_id != company_id:
        flash('Betalningsbatch hittades inte.', 'danger')
        return redirect(url_for('payment_files.index'))

    if pf.status != 'draft':
        flash('Kan bara ta bort betalningar från utkast.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    instr = db.session.get(PaymentInstruction, instruction_id)
    if not instr or instr.payment_file_id != batch_id:
        flash('Betalning hittades inte.', 'danger')
        return redirect(url_for('payment_files.view_batch', batch_id=batch_id))

    pf.total_amount -= instr.amount
    pf.number_of_transactions -= 1
    db.session.delete(instr)

    if pf.number_of_transactions <= 0:
        db.session.delete(pf)
        db.session.commit()
        flash('Batch borttagen (inga betalningar kvar).', 'info')
        return redirect(url_for('payment_files.index'))

    db.session.commit()
    flash('Betalning borttagen från batch.', 'success')
    return redirect(url_for('payment_files.view_batch', batch_id=batch_id))
