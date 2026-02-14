from flask import Blueprint, render_template, redirect, url_for, flash, session, send_file
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.annual_report import AnnualReport
from app.forms.annual_report import AnnualReportForm
from app.services.annual_report_service import (
    get_or_create_report, save_report, get_multi_year_overview,
    get_average_employees, finalize_report, reopen_report,
    generate_annual_report_pdf,
)
from app.services.report_service import get_profit_and_loss, get_balance_sheet
from app.services.asset_service import get_asset_note_data
from app.services.governance_service import get_board_for_annual_report

annual_report_bp = Blueprint('annual_report', __name__)


@annual_report_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(
        company_id=company_id
    ).order_by(FiscalYear.year.desc()).all()

    reports = AnnualReport.query.filter_by(
        company_id=company_id
    ).all()
    report_map = {r.fiscal_year_id: r for r in reports}

    return render_template('annual_report/index.html',
                           fiscal_years=fiscal_years, report_map=report_map)


@annual_report_bp.route('/edit/<int:fiscal_year_id>', methods=['GET', 'POST'])
@login_required
def edit(fiscal_year_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy or fy.company_id != company_id:
        flash('Räkenskapsåret hittades inte.', 'danger')
        return redirect(url_for('annual_report.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet att redigera årsredovisningar.', 'danger')
        return redirect(url_for('annual_report.index'))

    report = get_or_create_report(company_id, fiscal_year_id, created_by=current_user.id)

    if report.status == 'final':
        flash('Årsredovisningen är finaliserad. Öppna den igen för att redigera.', 'warning')
        return redirect(url_for('annual_report.view', report_id=report.id))

    form = AnnualReportForm(obj=report)

    if form.validate_on_submit():
        form_data = {
            'verksamhet': form.verksamhet.data,
            'vasentliga_handelser': form.vasentliga_handelser.data,
            'handelser_efter_fy': form.handelser_efter_fy.data,
            'framtida_utveckling': form.framtida_utveckling.data,
            'resultatdisposition': form.resultatdisposition.data,
            'redovisningsprinciper': form.redovisningsprinciper.data,
            'extra_noter': form.extra_noter.data,
            'board_members': form.board_members.data,
            'signing_location': form.signing_location.data,
            'signing_date': form.signing_date.data,
        }
        save_report(report.id, form_data)
        flash('Utkastet har sparats.', 'success')
        return redirect(url_for('annual_report.view', report_id=report.id))

    # Auto-calculated data for display
    company = report.company
    pnl = get_profit_and_loss(company_id, fiscal_year_id)
    bs = get_balance_sheet(company_id, fiscal_year_id)
    overview = get_multi_year_overview(company_id, fiscal_year_id)
    avg_employees = get_average_employees(company_id, fiscal_year_id)

    return render_template('annual_report/edit.html',
                           form=form, report=report, fy=fy, company=company,
                           pnl=pnl, bs=bs, overview=overview,
                           avg_employees=avg_employees)


@annual_report_bp.route('/<int:report_id>')
@login_required
def view(report_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    report = db.session.get(AnnualReport, report_id)
    if not report or report.company_id != company_id:
        flash('Årsredovisningen hittades inte.', 'danger')
        return redirect(url_for('annual_report.index'))

    fy = report.fiscal_year
    company = report.company
    pnl = get_profit_and_loss(company_id, fy.id)
    bs = get_balance_sheet(company_id, fy.id)
    overview = get_multi_year_overview(company_id, fy.id)
    avg_employees = get_average_employees(company_id, fy.id)

    # Board members: use governance data if available, fallback to text field
    board_objs = get_board_for_annual_report(company_id, fy.id)
    if board_objs:
        members = [f'{m.name}, {m.role_label}' for m in board_objs]
    elif report.board_members:
        members = [m.strip() for m in report.board_members.strip().splitlines() if m.strip()]
    else:
        members = []

    # Parse extra notes
    extra_notes = []
    if report.extra_noter:
        parts = report.extra_noter.split('---')
        extra_notes = [p.strip() for p in parts if p.strip()]

    asset_note = get_asset_note_data(company_id, fy.id)

    return render_template('annual_report/view.html',
                           report=report, fy=fy, company=company,
                           pnl=pnl, bs=bs, overview=overview,
                           avg_employees=avg_employees,
                           board_members=members, extra_notes=extra_notes,
                           asset_note=asset_note)


@annual_report_bp.route('/<int:report_id>/finalize', methods=['POST'])
@login_required
def do_finalize(report_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    report = db.session.get(AnnualReport, report_id)
    if not report or report.company_id != company_id:
        flash('Årsredovisningen hittades inte.', 'danger')
        return redirect(url_for('annual_report.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('annual_report.index'))

    finalize_report(report_id, user_id=current_user.id)
    flash('Årsredovisningen har finaliserats.', 'success')
    return redirect(url_for('annual_report.view', report_id=report_id))


@annual_report_bp.route('/<int:report_id>/reopen', methods=['POST'])
@login_required
def do_reopen(report_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    report = db.session.get(AnnualReport, report_id)
    if not report or report.company_id != company_id:
        flash('Årsredovisningen hittades inte.', 'danger')
        return redirect(url_for('annual_report.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('annual_report.index'))

    reopen_report(report_id, user_id=current_user.id)
    flash('Årsredovisningen har öppnats för redigering.', 'success')
    return redirect(url_for('annual_report.edit', fiscal_year_id=report.fiscal_year_id))


@annual_report_bp.route('/<int:report_id>/pdf')
@login_required
def download_pdf(report_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    report = db.session.get(AnnualReport, report_id)
    if not report or report.company_id != company_id:
        flash('Årsredovisningen hittades inte.', 'danger')
        return redirect(url_for('annual_report.index'))

    result = generate_annual_report_pdf(report_id)
    if result is None:
        flash('Kunde inte generera PDF.', 'danger')
        return redirect(url_for('annual_report.view', report_id=report_id))

    # If weasyprint is not available, result is HTML string
    if isinstance(result, str):
        flash('PDF-generering ej tillgänglig (weasyprint saknas). Använd utskrift från webbläsaren.', 'warning')
        return redirect(url_for('annual_report.view', report_id=report_id))

    fy = report.fiscal_year
    return send_file(result, as_attachment=True,
                     download_name=f'arsredovisning_{fy.year}.pdf',
                     mimetype='application/pdf')
