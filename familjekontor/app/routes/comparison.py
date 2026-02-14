from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify, request
from flask_login import login_required
from datetime import datetime

from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.comparison_service import (
    compare_periods, get_yoy_analysis, get_account_drilldown,
)

comparison_bp = Blueprint('comparison', __name__)


@comparison_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    fy_a_id = request.args.get('fy_a', type=int)
    fy_b_id = request.args.get('fy_b', type=int)
    report_type = request.args.get('report_type', 'pnl')

    comparison = None
    if fy_a_id and fy_b_id:
        comparison = compare_periods(company_id, fy_a_id, fy_b_id, report_type)

    company = db.session.get(Company, company_id)

    return render_template('comparison/index.html',
                           comparison=comparison, company=company,
                           fiscal_years=fiscal_years,
                           fy_a_id=fy_a_id, fy_b_id=fy_b_id,
                           report_type=report_type)


@comparison_bp.route('/yoy')
@login_required
def yoy():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    num_years = request.args.get('num_years', 3, type=int)

    yoy_data = None
    if fiscal_year_id:
        yoy_data = get_yoy_analysis(company_id, fiscal_year_id, num_years)

    company = db.session.get(Company, company_id)

    return render_template('comparison/yoy.html',
                           yoy=yoy_data, company=company,
                           fiscal_years=fiscal_years,
                           current_fy_id=fiscal_year_id,
                           num_years=num_years)


@comparison_bp.route('/api/yoy-chart')
@login_required
def api_yoy_chart():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'error': 'No company'}), 400

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    num_years = request.args.get('num_years', 3, type=int)
    if not fiscal_year_id:
        return jsonify({'error': 'No fiscal year'}), 400

    yoy_data = get_yoy_analysis(company_id, fiscal_year_id, num_years)

    return jsonify({
        'labels': [str(fy.year) for fy in yoy_data['years']],
        'sections': {name: values for name, values in yoy_data['sections'].items()},
        'summaries': {key: values for key, values in yoy_data['summaries'].items()},
    })


@comparison_bp.route('/drilldown/<account_number>')
@login_required
def drilldown(account_number):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not fiscal_year_id and fiscal_years:
        fiscal_year_id = fiscal_years[0].id

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    drilldown_data = None
    if fiscal_year_id:
        drilldown_data = get_account_drilldown(
            company_id, fiscal_year_id, account_number,
            start_date=start_date, end_date=end_date,
        )

    if drilldown_data is None and fiscal_year_id:
        flash(f'Konto {account_number} hittades inte.', 'warning')
        return redirect(url_for('comparison.index'))

    company = db.session.get(Company, company_id)

    return render_template('comparison/drilldown.html',
                           data=drilldown_data, company=company,
                           fiscal_years=fiscal_years,
                           current_fy_id=fiscal_year_id,
                           account_number=account_number,
                           start_date=start_date, end_date=end_date)
