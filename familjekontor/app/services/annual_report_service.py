"""Årsredovisning (Annual Report) service — K2 compliant."""

import os
from datetime import datetime, timezone

from flask import render_template, current_app

from app.extensions import db
from app.models.annual_report import AnnualReport
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.models.salary import Employee
from app.models.audit import AuditLog
from app.services.report_service import get_profit_and_loss, get_balance_sheet
from app.services.asset_service import get_asset_note_data
from app.services.governance_service import get_board_for_annual_report


K2_BOILERPLATE = (
    'Årsredovisningen har upprättats enligt årsredovisningslagen och '
    'Bokföringsnämndens allmänna råd BFNAR 2016:10 Årsredovisning i mindre '
    'företag (K2).\n\n'
    'Intäkter redovisas till det verkliga värdet av vad som erhållits eller '
    'kommer att erhållas.\n\n'
    'Anläggningstillgångar värderas till anskaffningsvärde med avdrag för '
    'ackumulerade avskrivningar och eventuella nedskrivningar.\n\n'
    'Fordringar upptas till det belopp som efter individuell bedömning '
    'beräknas bli betalt.'
)


def get_k2_boilerplate():
    """Return default K2 accounting principles text."""
    return K2_BOILERPLATE


def get_or_create_report(company_id, fiscal_year_id, created_by=None):
    """Get existing annual report or create a new draft.

    Pre-populates redovisningsprinciper with K2 boilerplate on creation.
    """
    report = AnnualReport.query.filter_by(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
    ).first()

    if report:
        return report

    report = AnnualReport(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        status='draft',
        redovisningsprinciper=K2_BOILERPLATE,
        created_by=created_by,
    )
    db.session.add(report)
    db.session.commit()
    return report


def save_report(report_id, form_data):
    """Update annual report fields from form data."""
    report = db.session.get(AnnualReport, report_id)
    if not report:
        return None

    fields = [
        'verksamhet', 'vasentliga_handelser', 'handelser_efter_fy',
        'framtida_utveckling', 'resultatdisposition',
        'redovisningsprinciper', 'extra_noter',
        'board_members', 'signing_location', 'signing_date',
    ]
    for field in fields:
        if field in form_data:
            setattr(report, field, form_data[field])

    report.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return report


def get_multi_year_overview(company_id, fiscal_year_id, num_years=3):
    """Calculate flerårsöversikt (multi-year summary).

    Returns list of dicts sorted by year descending:
    [{year, start_date, end_date, revenue, result_before_tax, total_assets, equity}]
    """
    target_fy = db.session.get(FiscalYear, fiscal_year_id)
    if not target_fy:
        return []

    # Get target FY and previous FYs
    fiscal_years = FiscalYear.query.filter(
        FiscalYear.company_id == company_id,
        FiscalYear.year <= target_fy.year,
    ).order_by(FiscalYear.year.desc()).limit(num_years).all()

    overview = []
    for fy in fiscal_years:
        pnl = get_profit_and_loss(company_id, fy.id)
        bs = get_balance_sheet(company_id, fy.id)

        revenue = pnl['sections']['Nettoomsättning']['total']
        equity = bs['sections']['Eget kapital']['total']

        overview.append({
            'year': fy.year,
            'start_date': fy.start_date,
            'end_date': fy.end_date,
            'revenue': revenue,
            'result_before_tax': pnl['result_before_tax'],
            'total_assets': bs['total_assets'],
            'equity': equity,
        })

    return overview


def get_average_employees(company_id, fiscal_year_id):
    """Count employees active during the fiscal year."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return 0

    count = Employee.query.filter(
        Employee.company_id == company_id,
        Employee.employment_start <= fy.end_date,
        db.or_(
            Employee.employment_end.is_(None),
            Employee.employment_end >= fy.start_date,
        ),
    ).count()

    return count


def finalize_report(report_id, user_id=None):
    """Mark report as final."""
    report = db.session.get(AnnualReport, report_id)
    if not report:
        return None

    report.status = 'final'
    report.updated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        company_id=report.company_id, user_id=user_id,
        action='approve', entity_type='annual_report', entity_id=report.id,
        new_values={'status': 'final'},
    )
    db.session.add(audit)
    db.session.commit()
    return report


def reopen_report(report_id, user_id=None):
    """Reopen a finalized report for editing."""
    report = db.session.get(AnnualReport, report_id)
    if not report:
        return None

    report.status = 'draft'
    report.updated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        company_id=report.company_id, user_id=user_id,
        action='update', entity_type='annual_report', entity_id=report.id,
        new_values={'status': 'draft'},
    )
    db.session.add(audit)
    db.session.commit()
    return report


def generate_annual_report_pdf(report_id):
    """Generate complete årsredovisning as PDF using weasyprint."""
    report = db.session.get(AnnualReport, report_id)
    if not report:
        return None

    company = report.company
    fy = report.fiscal_year

    pnl = get_profit_and_loss(company.id, fy.id)
    bs = get_balance_sheet(company.id, fy.id)
    overview = get_multi_year_overview(company.id, fy.id)
    avg_employees = get_average_employees(company.id, fy.id)

    # Board members: use governance data if available, fallback to text field
    board_objs = get_board_for_annual_report(company.id, fy.id)
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

    asset_note = get_asset_note_data(company.id, fy.id)

    html = render_template('annual_report/pdf.html',
                           report=report, company=company, fy=fy,
                           pnl=pnl, bs=bs, overview=overview,
                           avg_employees=avg_employees,
                           board_members=members,
                           extra_notes=extra_notes,
                           asset_note=asset_note)

    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        return html

    pdf_dir = os.path.join(current_app.static_folder, 'annual_reports', str(company.id))
    os.makedirs(pdf_dir, exist_ok=True)

    filename = f'arsredovisning_{fy.year}.pdf'
    pdf_path = os.path.join(pdf_dir, filename)

    HTML(string=html).write_pdf(pdf_path)

    report.pdf_path = f'annual_reports/{company.id}/{filename}'
    db.session.commit()

    return pdf_path
