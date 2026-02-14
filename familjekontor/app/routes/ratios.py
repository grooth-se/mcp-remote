from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify, request
from flask_login import login_required
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.ratio_service import (
    get_financial_ratios, get_multi_year_ratios, get_ratio_summary,
)

ratios_bp = Blueprint('ratios', __name__)


@ratios_bp.route('/')
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

    ratios = None
    summary = None
    if fiscal_year_id:
        ratios = get_financial_ratios(company_id, fiscal_year_id)
        summary = get_ratio_summary(company_id, fiscal_year_id)

    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id) if fiscal_year_id else None

    return render_template('ratios/index.html',
                           ratios=ratios, summary=summary,
                           company=company, fiscal_year=fiscal_year,
                           fiscal_years=fiscal_years,
                           current_fy_id=fiscal_year_id)


@ratios_bp.route('/api/multi-year')
@login_required
def api_multi_year():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'error': 'No company selected'}), 400

    data = get_multi_year_ratios(company_id)
    return jsonify(data)
