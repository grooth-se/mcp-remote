from datetime import date
from io import BytesIO
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, send_file,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.tax import VATReport, Deadline, TaxPayment, TaxReturn
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.forms.tax import (
    VATGenerateForm, VATFinalizeForm, DeadlineForm,
    DeadlineSeedForm, TaxPaymentForm,
)
from app.forms.deklaration import (
    TaxReturnCreateForm, TaxReturnAdjustmentsForm, AdjustmentLineForm,
)
from app.services.tax_service import (
    get_vat_periods_for_year, create_vat_report, finalize_vat_report,
    seed_deadlines_for_year, get_upcoming_deadlines, get_overdue_deadlines,
    complete_deadline, record_tax_payment, list_tax_payments,
    get_tax_payment_summary, calculate_employer_tax_for_period,
)
from app.services import deklaration_service
from app.services import ink_form_service

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
    company_id = session.get('active_company_id')
    report = db.session.get(VATReport, report_id)
    if not report or report.company_id != company_id:
        flash('Rapporten hittades inte.', 'danger')
        return redirect(url_for('tax.vat_index'))

    finalize_form = VATFinalizeForm()
    return render_template('tax/vat_view.html', report=report,
                           finalize_form=finalize_form)


@tax_bp.route('/vat/<int:report_id>/finalize', methods=['POST'])
@login_required
def vat_finalize(report_id):
    company_id = session.get('active_company_id')
    report_obj = db.session.get(VATReport, report_id)
    if not report_obj or report_obj.company_id != company_id:
        flash('Rapporten hittades inte.', 'danger')
        return redirect(url_for('tax.vat_index'))
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
    company_id = session.get('active_company_id')
    report = db.session.get(VATReport, report_id)
    if not report or report.company_id != company_id:
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
    if status_filter != 'all' and status_filter not in ('pending', 'completed', 'overdue'):
        status_filter = 'all'
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
    company_id = session.get('active_company_id')
    deadline = db.session.get(Deadline, deadline_id)
    if not deadline or deadline.company_id != company_id:
        flash('Deadline hittades inte.', 'danger')
        return redirect(url_for('tax.deadlines_index'))
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


# ---------------------------------------------------------------------------
# Deklaration (Yearly Tax Return)
# ---------------------------------------------------------------------------

@tax_bp.route('/deklaration/')
@login_required
def deklaration_index():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    returns = deklaration_service.get_tax_returns(company_id)
    return render_template('tax/deklaration_index.html',
                           returns=returns, company=company)


@tax_bp.route('/deklaration/new', methods=['GET', 'POST'])
@login_required
def deklaration_new():
    company_id, company, active_fy = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    form = TaxReturnCreateForm()
    fys = FiscalYear.query.filter_by(company_id=company_id).order_by(
        FiscalYear.year.desc()
    ).all()
    form.fiscal_year_id.choices = [(fy.id, f'{fy.year} ({fy.start_date} - {fy.end_date})') for fy in fys]

    if form.validate_on_submit():
        tr = deklaration_service.create_tax_return(
            company_id, form.fiscal_year_id.data, created_by=current_user.id
        )
        if tr:
            flash(f'Deklaration {tr.return_type.upper()} för {tr.tax_year} skapad.', 'success')
            return redirect(url_for('tax.deklaration_view', return_id=tr.id))
        else:
            flash('Kunde inte skapa deklaration.', 'danger')

    return render_template('tax/deklaration_new.html', form=form, company=company)


@tax_bp.route('/deklaration/<int:return_id>')
@login_required
def deklaration_view(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    adj_form = AdjustmentLineForm()
    return render_template('tax/deklaration_view.html', tr=tr, adj_form=adj_form)


@tax_bp.route('/deklaration/<int:return_id>/edit', methods=['GET', 'POST'])
@login_required
def deklaration_edit(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))
    if tr.status != 'draft':
        flash('Kan inte redigera en inlämnad deklaration.', 'warning')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    form = TaxReturnAdjustmentsForm(obj=tr)

    if form.validate_on_submit():
        data = {
            'non_deductible_expenses': form.non_deductible_expenses.data,
            'non_taxable_income': form.non_taxable_income.data,
            'depreciation_tax_diff': form.depreciation_tax_diff.data,
            'previous_deficit': form.previous_deficit.data,
            'notes': form.notes.data,
        }
        deklaration_service.update_adjustments(return_id, data)
        flash('Justeringar sparade.', 'success')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    return render_template('tax/deklaration_edit.html', form=form, tr=tr)


@tax_bp.route('/deklaration/<int:return_id>/refresh', methods=['POST'])
@login_required
def deklaration_refresh(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    result = deklaration_service.refresh_from_accounting(return_id)
    if result:
        flash('Bokföringsdata uppdaterad.', 'success')
    else:
        flash('Kunde inte uppdatera (deklarationen är redan inlämnad).', 'warning')
    return redirect(url_for('tax.deklaration_view', return_id=return_id))


@tax_bp.route('/deklaration/<int:return_id>/add-adjustment', methods=['POST'])
@login_required
def deklaration_add_adjustment(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))
    if current_user.is_readonly or tr.status != 'draft':
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    form = AdjustmentLineForm()
    if form.validate_on_submit():
        deklaration_service.add_adjustment_line(
            return_id,
            adjustment_type=form.adjustment_type.data,
            description=form.description.data,
            amount=form.amount.data,
            sru_code=form.sru_code.data,
        )
        flash('Justering tillagd.', 'success')
    return redirect(url_for('tax.deklaration_view', return_id=return_id))


@tax_bp.route('/deklaration/adjustment/<int:adjustment_id>/remove', methods=['POST'])
@login_required
def deklaration_remove_adjustment(adjustment_id):
    from app.models.tax import TaxReturnAdjustment
    adj = db.session.get(TaxReturnAdjustment, adjustment_id)
    if not adj:
        flash('Justeringen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    return_id = adj.tax_return_id
    company_id = session.get('active_company_id')
    if adj.tax_return.company_id != company_id:
        flash('Ingen behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    deklaration_service.remove_adjustment_line(adjustment_id)
    flash('Justering borttagen.', 'success')
    return redirect(url_for('tax.deklaration_view', return_id=return_id))


@tax_bp.route('/deklaration/<int:return_id>/submit', methods=['POST'])
@login_required
def deklaration_submit(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    result = deklaration_service.submit_tax_return(return_id)
    if result:
        flash('Deklarationen markerad som inlämnad.', 'success')
    else:
        flash('Kunde inte lämna in deklarationen.', 'warning')
    return redirect(url_for('tax.deklaration_view', return_id=return_id))


@tax_bp.route('/deklaration/<int:return_id>/approve', methods=['POST'])
@login_required
def deklaration_approve(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    result = deklaration_service.approve_tax_return(return_id)
    if result:
        flash('Deklarationen godkänd.', 'success')
    else:
        flash('Deklarationen måste vara inlämnad innan den kan godkännas.', 'warning')
    return redirect(url_for('tax.deklaration_view', return_id=return_id))


@tax_bp.route('/deklaration/<int:return_id>/export')
@login_required
def deklaration_export(return_id):
    company_id = session.get('active_company_id')
    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    output = deklaration_service.export_tax_return_excel(return_id)
    if not output:
        flash('Kunde inte generera Excel.', 'danger')
        return redirect(url_for('tax.deklaration_view', return_id=return_id))

    filename = f'deklaration_{tr.return_type}_{tr.tax_year}.xlsx'
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ---------------------------------------------------------------------------
# INK form routes (Skatteverket-formatted reports)
# ---------------------------------------------------------------------------

@tax_bp.route('/deklaration/<int:return_id>/ink-form')
@login_required
def deklaration_ink_view(return_id):
    """View INK form data (INK2R/INK2S/INK2 or INK4 equivalents)."""
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    data = ink_form_service.compute_all_ink_data(return_id)
    if not data or data['tr'].company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    return render_template(
        'tax/ink_view.html',
        company=data['company'],
        fy=data['fy'],
        tr=data['tr'],
        ink_type=data['ink_type'],
        ink_main=data['ink_main'],
        balance_sheet=data['ink_r']['balance_sheet'],
        income_statement=data['ink_r']['income_statement'],
        ink_s=data['ink_s'],
        totals=data['ink_r']['totals'],
    )


@tax_bp.route('/deklaration/<int:return_id>/ink-pdf')
@login_required
def deklaration_ink_pdf(return_id):
    """Download INK form as PDF."""
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    result = ink_form_service.generate_ink_pdf(return_id)
    if result is None:
        flash('Kunde inte generera PDF.', 'danger')
        return redirect(url_for('tax.deklaration_ink_view', return_id=return_id))

    if isinstance(result, str):
        # WeasyPrint not available — return HTML
        return result

    filename = f'{tr.return_type}_{tr.tax_year}.pdf'
    return send_file(result, as_attachment=True, download_name=filename,
                     mimetype='application/pdf')


@tax_bp.route('/deklaration/<int:return_id>/sru')
@login_required
def deklaration_sru_export(return_id):
    """Download SRU file for Skatteverket digital submission."""
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    tr = db.session.get(TaxReturn, return_id)
    if not tr or tr.company_id != company_id:
        flash('Deklarationen hittades inte.', 'danger')
        return redirect(url_for('tax.deklaration_index'))

    output = ink_form_service.generate_sru_file(return_id)
    if not output:
        flash('Kunde inte generera SRU-fil.', 'danger')
        return redirect(url_for('tax.deklaration_ink_view', return_id=return_id))

    filename = f'{tr.return_type}_{tr.tax_year}.sru'
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='text/plain')
