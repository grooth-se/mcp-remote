from datetime import date
from io import BytesIO
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, send_file,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.tax import VATReport, Deadline, TaxPayment
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.forms.tax import (
    VATGenerateForm, VATFinalizeForm, DeadlineForm,
    DeadlineSeedForm, TaxPaymentForm,
)
from app.services.tax_service import (
    get_vat_periods_for_year, create_vat_report, finalize_vat_report,
    seed_deadlines_for_year, get_upcoming_deadlines, get_overdue_deadlines,
    complete_deadline, record_tax_payment, list_tax_payments,
    get_tax_payment_summary, calculate_employer_tax_for_period,
)

tax_bp = Blueprint('tax', __name__)


def _get_active_context():
    """Return (company_id, company, active_fy) or redirect."""
    company_id = session.get('active_company_id')
    if not company_id:
        return None, None, None
    company = db.session.get(Company, company_id)
    if not company:
        return None, None, None
    active_fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()
    return company_id, company, active_fy


# ---------------------------------------------------------------------------
# Tax overview
# ---------------------------------------------------------------------------

@tax_bp.route('/')
@login_required
def index():
    company_id, company, active_fy = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    upcoming = get_upcoming_deadlines(company_id, days_ahead=30)
    overdue = get_overdue_deadlines(company_id)
    recent_vat = VATReport.query.filter_by(company_id=company_id).order_by(
        VATReport.period_end.desc()
    ).limit(5).all()
    recent_payments = TaxPayment.query.filter_by(company_id=company_id).order_by(
        TaxPayment.payment_date.desc()
    ).limit(5).all()

    return render_template('tax/index.html',
                           company=company,
                           upcoming=upcoming,
                           overdue=overdue,
                           recent_vat=recent_vat,
                           recent_payments=recent_payments)


# ---------------------------------------------------------------------------
# VAT
# ---------------------------------------------------------------------------

@tax_bp.route('/vat/')
@login_required
def vat_index():
    company_id, company, active_fy = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    reports = VATReport.query.filter_by(company_id=company_id).order_by(
        VATReport.period_end.desc()
    ).all()
    return render_template('tax/vat_index.html', reports=reports, company=company)


@tax_bp.route('/vat/generate', methods=['GET', 'POST'])
@login_required
def vat_generate():
    company_id, company, active_fy = _get_active_context()
    if not company or not active_fy:
        flash('Inget aktivt räkenskapsår.', 'warning')
        return redirect(url_for('tax.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.vat_index'))

    periods = get_vat_periods_for_year(company_id, active_fy.year)
    form = VATGenerateForm()
    form.period.choices = [(str(i), p['label']) for i, p in enumerate(periods)]

    if form.validate_on_submit():
        idx = int(form.period.data)
        period_info = periods[idx]
        report = create_vat_report(company_id, active_fy.id, period_info,
                                   created_by=current_user.id)
        flash(f'Momsrapport skapad för {period_info["label"]}.', 'success')
        return redirect(url_for('tax.vat_view', report_id=report.id))

    return render_template('tax/vat_generate.html', form=form, company=company)


@tax_bp.route('/vat/<int:report_id>')
@login_required
def vat_view(report_id):
    report = db.session.get(VATReport, report_id)
    if not report:
        flash('Rapporten hittades inte.', 'danger')
        return redirect(url_for('tax.vat_index'))

    finalize_form = VATFinalizeForm()
    return render_template('tax/vat_view.html', report=report,
                           finalize_form=finalize_form)


@tax_bp.route('/vat/<int:report_id>/finalize', methods=['POST'])
@login_required
def vat_finalize(report_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.vat_view', report_id=report_id))

    report = finalize_vat_report(report_id)
    if report:
        flash('Momsrapporten har markerats som inlämnad.', 'success')
    else:
        flash('Rapporten hittades inte.', 'danger')
    return redirect(url_for('tax.vat_view', report_id=report_id))


@tax_bp.route('/vat/<int:report_id>/export')
@login_required
def vat_export(report_id):
    """Export a VAT report as Excel."""
    report = db.session.get(VATReport, report_id)
    if not report:
        flash('Rapporten hittades inte.', 'danger')
        return redirect(url_for('tax.vat_index'))

    try:
        import openpyxl
    except ImportError:
        flash('openpyxl krävs för Excel-export.', 'danger')
        return redirect(url_for('tax.vat_view', report_id=report_id))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Momsdeklaration'

    ws.append(['Momsdeklaration'])
    ws.append(['Företag', report.company.name])
    ws.append(['Period', f'{report.period_start} - {report.period_end}'])
    ws.append([])
    ws.append(['Post', 'Belopp (SEK)'])
    ws.append(['Utgående moms 25%', float(report.output_vat_25)])
    ws.append(['Utgående moms 12%', float(report.output_vat_12)])
    ws.append(['Utgående moms 6%', float(report.output_vat_6)])
    ws.append(['Ingående moms', float(report.input_vat)])
    ws.append([])
    ws.append(['Moms att betala', float(report.vat_to_pay)])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f'moms_{report.period_start}_{report.period_end}.xlsx'
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ---------------------------------------------------------------------------
# Employer tax (read-only)
# ---------------------------------------------------------------------------

@tax_bp.route('/employer/')
@login_required
def employer_index():
    company_id, company, active_fy = _get_active_context()
    if not company or not active_fy:
        flash('Inget aktivt räkenskapsår.', 'warning')
        return redirect(url_for('tax.index'))

    year = request.args.get('year', active_fy.year, type=int)
    fy = FiscalYear.query.filter_by(company_id=company_id, year=year).first()
    if not fy:
        fy = active_fy

    # Monthly breakdown
    import calendar
    months = []
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        start = date(year, month, 1)
        end = date(year, month, last_day)
        data = calculate_employer_tax_for_period(company_id, fy.id, start, end)
        data['month'] = month
        data['month_name'] = _month_name_sv(month)
        months.append(data)

    return render_template('tax/employer_index.html',
                           company=company, year=year, months=months)


def _month_name_sv(month):
    names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Maj', 'Jun',
             'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec']
    return names[month]


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------

@tax_bp.route('/deadlines/')
@login_required
def deadlines_index():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    status_filter = request.args.get('status', 'all')
    query = Deadline.query.filter_by(company_id=company_id)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    deadlines = query.order_by(Deadline.due_date).all()

    # Auto-update overdue
    get_overdue_deadlines(company_id)

    return render_template('tax/deadlines_index.html',
                           deadlines=deadlines, company=company,
                           status_filter=status_filter)


@tax_bp.route('/deadlines/new', methods=['GET', 'POST'])
@login_required
def deadline_new():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deadlines_index'))

    form = DeadlineForm()
    if form.validate_on_submit():
        deadline = Deadline(
            company_id=company_id,
            deadline_type=form.deadline_type.data,
            description=form.description.data,
            due_date=form.due_date.data,
            reminder_date=form.reminder_date.data,
            period_label=form.period_label.data,
            notes=form.notes.data,
            auto_generated=False,
        )
        db.session.add(deadline)
        db.session.commit()
        flash('Deadline skapad.', 'success')
        return redirect(url_for('tax.deadlines_index'))

    return render_template('tax/deadline_new.html', form=form, company=company)


@tax_bp.route('/deadlines/seed', methods=['GET', 'POST'])
@login_required
def deadlines_seed():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deadlines_index'))

    form = DeadlineSeedForm()
    if form.validate_on_submit():
        created = seed_deadlines_for_year(company_id, form.year.data)
        if created:
            flash(f'{len(created)} deadlines genererade för {form.year.data}.', 'success')
        else:
            flash(f'Deadlines finns redan för {form.year.data}.', 'info')
        return redirect(url_for('tax.deadlines_index'))

    return render_template('tax/deadlines_seed.html', form=form, company=company)


@tax_bp.route('/deadlines/<int:deadline_id>/complete', methods=['POST'])
@login_required
def deadline_complete(deadline_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deadlines_index'))

    notes = request.form.get('notes', '')
    result = complete_deadline(deadline_id, current_user.id, notes)
    if result:
        flash('Deadline markerad som klar.', 'success')
    else:
        flash('Deadline hittades inte.', 'danger')
    return redirect(url_for('tax.deadlines_index'))


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@tax_bp.route('/payments/')
@login_required
def payments_index():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    year = request.args.get('year', date.today().year, type=int)
    payments = list_tax_payments(company_id, year)
    return render_template('tax/payments_index.html',
                           payments=payments, company=company, year=year)


@tax_bp.route('/payments/new', methods=['GET', 'POST'])
@login_required
def payment_new():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.payments_index'))

    pending_deadlines = Deadline.query.filter(
        Deadline.company_id == company_id,
        Deadline.status.in_(['pending', 'overdue']),
    ).order_by(Deadline.due_date).all()
    deadline_choices = [(d.id, f'{d.description} ({d.due_date})') for d in pending_deadlines]

    form = TaxPaymentForm(deadline_choices=deadline_choices)
    if form.validate_on_submit():
        dl_id = form.deadline_id.data if form.deadline_id.data != 0 else None
        record_tax_payment(
            company_id=company_id,
            payment_type=form.payment_type.data,
            amount=form.amount.data,
            payment_date=form.payment_date.data,
            reference=form.reference.data,
            deadline_id=dl_id,
            notes=form.notes.data,
            created_by=current_user.id,
        )
        flash('Skattebetalning registrerad.', 'success')
        return redirect(url_for('tax.payments_index'))

    return render_template('tax/payment_new.html', form=form, company=company)


@tax_bp.route('/payments/summary')
@login_required
def payments_summary():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    year = request.args.get('year', date.today().year, type=int)
    summary = get_tax_payment_summary(company_id, year)
    return render_template('tax/payments_summary.html',
                           summary=summary, company=company, year=year)
