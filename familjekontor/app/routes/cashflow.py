from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify, request, send_file
from flask_login import login_required
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.cashflow_service import (
    get_cash_flow_statement, get_monthly_cash_flow,
    get_cash_flow_forecast, export_cashflow_to_excel,
)

cashflow_bp = Blueprint('cashflow', __name__)


@cashflow_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    cf_data = None
    if fiscal_year_id:
        cf_data = get_cash_flow_statement(company_id, fiscal_year_id)

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id) if fiscal_year_id else None

    return render_template('cashflow/index.html',
                           cf=cf_data, company=company, fiscal_year=fiscal_year,
                           fiscal_years=fiscal_years, current_fy_id=fiscal_year_id)


@cashflow_bp.route('/api/monthly')
@login_required
def api_monthly():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'error': 'No company selected'}), 400

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id:
        return jsonify({'error': 'No fiscal year'}), 400

    monthly = get_monthly_cash_flow(company_id, fiscal_year_id)
    forecast = get_cash_flow_forecast(company_id, fiscal_year_id)

    return jsonify({
        'monthly': monthly,
        'forecast': forecast,
    })


@cashflow_bp.route('/excel')
@login_required
def excel_export():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not company_id or not fiscal_year_id:
        return redirect(url_for('cashflow.index'))

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id)
    cf_data = get_cash_flow_statement(company_id, fiscal_year_id)

    output = export_cashflow_to_excel(cf_data, company.name, fiscal_year)
    return send_file(output,
                     download_name=f'Kassaflodesanalys_{company.name}_{fiscal_year.year}.xlsx',
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
