from flask import Blueprint, render_template, redirect, url_for, flash, request, session, send_file
from flask_login import login_required
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.forms.report import ReportFilterForm
from app.services.report_service import (
    get_profit_and_loss, get_balance_sheet, get_general_ledger, export_report_to_excel
)

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/pnl')
@login_required
def profit_and_loss():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    form = ReportFilterForm()
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    form.fiscal_year_id.choices = [(fy.id, f'{fy.year} ({fy.start_date} - {fy.end_date})') for fy in fiscal_years]

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    report_data = None
    if fiscal_year_id:
        report_data = get_profit_and_loss(company_id, fiscal_year_id)

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id) if fiscal_year_id else None

    return render_template('reports/pnl.html',
                           form=form, report=report_data,
                           company=company, fiscal_year=fiscal_year,
                           current_fy_id=fiscal_year_id)


@reports_bp.route('/pnl/excel')
@login_required
def pnl_excel():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not company_id or not fiscal_year_id:
        return redirect(url_for('reports.profit_and_loss'))

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id)
    report_data = get_profit_and_loss(company_id, fiscal_year_id)

    output = export_report_to_excel(report_data, 'pnl', company.name, fiscal_year)
    return send_file(output, download_name=f'Resultatrakning_{company.name}_{fiscal_year.year}.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/balance')
@login_required
def balance_sheet():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    form = ReportFilterForm()
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    form.fiscal_year_id.choices = [(fy.id, f'{fy.year} ({fy.start_date} - {fy.end_date})') for fy in fiscal_years]

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    report_data = None
    if fiscal_year_id:
        report_data = get_balance_sheet(company_id, fiscal_year_id)

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id) if fiscal_year_id else None

    return render_template('reports/balance.html',
                           form=form, report=report_data,
                           company=company, fiscal_year=fiscal_year,
                           current_fy_id=fiscal_year_id)


@reports_bp.route('/balance/excel')
@login_required
def balance_excel():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not company_id or not fiscal_year_id:
        return redirect(url_for('reports.balance_sheet'))

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id)
    report_data = get_balance_sheet(company_id, fiscal_year_id)

    output = export_report_to_excel(report_data, 'balance', company.name, fiscal_year)
    return send_file(output, download_name=f'Balansrakning_{company.name}_{fiscal_year.year}.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/ledger')
@login_required
def general_ledger():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    form = ReportFilterForm()
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    form.fiscal_year_id.choices = [(fy.id, f'{fy.year} ({fy.start_date} - {fy.end_date})') for fy in fiscal_years]

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    account_number = request.args.get('account_number', '')

    ledger = None
    if fiscal_year_id:
        ledger = get_general_ledger(company_id, fiscal_year_id, account_number or None)

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id) if fiscal_year_id else None

    return render_template('reports/ledger.html',
                           form=form, ledger=ledger,
                           company=company, fiscal_year=fiscal_year,
                           current_fy_id=fiscal_year_id,
                           account_number=account_number)


@reports_bp.route('/ledger/excel')
@login_required
def ledger_excel():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    account_number = request.args.get('account_number', '')
    if not company_id or not fiscal_year_id:
        return redirect(url_for('reports.general_ledger'))

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id)
    ledger = get_general_ledger(company_id, fiscal_year_id, account_number or None)

    output = export_report_to_excel(ledger, 'ledger', company.name, fiscal_year)
    return send_file(output, download_name=f'Huvudbok_{company.name}_{fiscal_year.year}.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
