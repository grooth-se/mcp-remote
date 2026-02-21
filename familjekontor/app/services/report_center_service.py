"""Report center service: available reports, saved configs, PDF generation."""

import json
from io import BytesIO

from app.extensions import db
from app.models.saved_report import SavedReport


def get_available_reports():
    """Static list of all report types with metadata."""
    return [
        {
            'key': 'pnl',
            'name': 'Resultaträkning',
            'icon': 'bi-graph-down',
            'description': 'Intäkter, kostnader och resultat',
            'url_name': 'reports.profit_and_loss',
            'has_pdf': True,
            'has_excel': True,
            'category': 'Finansiella',
        },
        {
            'key': 'balance',
            'name': 'Balansräkning',
            'icon': 'bi-bank',
            'description': 'Tillgångar, skulder och eget kapital',
            'url_name': 'reports.balance_sheet',
            'has_pdf': True,
            'has_excel': True,
            'category': 'Finansiella',
        },
        {
            'key': 'ledger',
            'name': 'Huvudbok',
            'icon': 'bi-journal-text',
            'description': 'Alla transaktioner per konto',
            'url_name': 'reports.general_ledger',
            'has_pdf': False,
            'has_excel': True,
            'category': 'Finansiella',
        },
        {
            'key': 'cashflow',
            'name': 'Kassaflödesanalys',
            'icon': 'bi-water',
            'description': 'Löpande, investering och finansiering',
            'url_name': 'cashflow.index',
            'has_pdf': True,
            'has_excel': True,
            'category': 'Finansiella',
        },
        {
            'key': 'ratios',
            'name': 'Nyckeltal',
            'icon': 'bi-speedometer2',
            'description': 'Lönsamhet, likviditet, soliditet',
            'url_name': 'ratios.index',
            'has_pdf': True,
            'has_excel': False,
            'category': 'Analys',
        },
        {
            'key': 'comparison',
            'name': 'Periodjämförelse',
            'icon': 'bi-arrow-left-right',
            'description': 'Jämför två räkenskapsår',
            'url_name': 'comparison.index',
            'has_pdf': True,
            'has_excel': False,
            'category': 'Analys',
        },
        {
            'key': 'yoy',
            'name': 'Flerårsöversikt',
            'icon': 'bi-graph-up-arrow',
            'description': 'Trendanalys över flera år',
            'url_name': 'comparison.yoy',
            'has_pdf': False,
            'has_excel': False,
            'category': 'Analys',
        },
        {
            'key': 'arap',
            'name': 'Kund/Lev-analys',
            'icon': 'bi-people-fill',
            'description': 'DSO, DPO, åldersanalys',
            'url_name': 'arap.index',
            'has_pdf': False,
            'has_excel': False,
            'category': 'Analys',
        },
        {
            'key': 'annual_report',
            'name': 'Årsredovisning',
            'icon': 'bi-file-earmark-text',
            'description': 'K2-årsredovisning med PDF',
            'url_name': 'annual_report.index',
            'has_pdf': True,
            'has_excel': False,
            'category': 'Skatt & Lön',
        },
        {
            'key': 'vat',
            'name': 'Momsrapporter',
            'icon': 'bi-percent',
            'description': 'Momsdeklaration',
            'url_name': 'tax.vat_index',
            'has_pdf': False,
            'has_excel': False,
            'category': 'Skatt & Lön',
        },
        {
            'key': 'salary',
            'name': 'Löneöversikt',
            'icon': 'bi-cash',
            'description': 'Lönekörning och pension',
            'url_name': 'salary.index',
            'has_pdf': False,
            'has_excel': False,
            'category': 'Skatt & Lön',
        },
        {
            'key': 'business_analysis',
            'name': 'Affärsanalys',
            'icon': 'bi-clipboard-data',
            'description': 'AI-genererad/mallbaserad affärsanalys med nyckeltal, kassaflöde och trender',
            'url_name': 'report_center.business_analysis',
            'has_pdf': True,
            'has_excel': False,
            'category': 'Analys',
        },
    ]


def save_report_config(company_id, user_id, name, report_type, params):
    """Save a report configuration for quick access."""
    sr = SavedReport(
        company_id=company_id,
        user_id=user_id,
        name=name,
        report_type=report_type,
        parameters=json.dumps(params) if params else None,
    )
    db.session.add(sr)
    db.session.commit()
    return sr


def get_saved_reports(company_id, user_id):
    """Get user's saved report configurations."""
    return (SavedReport.query
            .filter_by(company_id=company_id, user_id=user_id)
            .order_by(SavedReport.created_at.desc())
            .all())


def delete_saved_report(report_id, user_id):
    """Delete a saved report, owner only."""
    sr = db.session.get(SavedReport, report_id)
    if not sr or sr.user_id != user_id:
        return False
    db.session.delete(sr)
    db.session.commit()
    return True


def generate_report_pdf(report_type, company_id, fiscal_year_id, **kwargs):
    """Generate a PDF for a given report type.

    Returns BytesIO with PDF content, or None if WeasyPrint unavailable.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        return None

    from flask import render_template
    from app.extensions import db
    from app.models.accounting import FiscalYear
    from app.models.company import Company

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id)

    if report_type == 'pnl':
        from app.services.report_service import get_profit_and_loss
        report = get_profit_and_loss(company_id, fiscal_year_id)
        html_str = render_template('report_center/pdf_pnl.html',
                                   report=report, company=company, fiscal_year=fiscal_year)

    elif report_type == 'balance':
        from app.services.report_service import get_balance_sheet
        report = get_balance_sheet(company_id, fiscal_year_id)
        html_str = render_template('report_center/pdf_balance.html',
                                   report=report, company=company, fiscal_year=fiscal_year)

    elif report_type == 'cashflow':
        from app.services.cashflow_service import get_cash_flow_statement
        cf = get_cash_flow_statement(company_id, fiscal_year_id)
        html_str = render_template('report_center/pdf_cashflow.html',
                                   cf=cf, company=company, fiscal_year=fiscal_year)

    elif report_type == 'ratios':
        from app.services.ratio_service import get_financial_ratios
        ratios = get_financial_ratios(company_id, fiscal_year_id)
        html_str = render_template('report_center/pdf_ratios.html',
                                   ratios=ratios, company=company, fiscal_year=fiscal_year)

    elif report_type == 'comparison':
        fy_b_id = kwargs.get('fy_b_id')
        if not fy_b_id:
            return None
        from app.services.comparison_service import compare_periods
        comparison = compare_periods(company_id, fiscal_year_id, fy_b_id, 'pnl')
        html_str = render_template('report_center/pdf_comparison.html',
                                   comparison=comparison, company=company, fiscal_year=fiscal_year)
    else:
        return None

    output = BytesIO()
    HTML(string=html_str).write_pdf(output)
    output.seek(0)
    return output
