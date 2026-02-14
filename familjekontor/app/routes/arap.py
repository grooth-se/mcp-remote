from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify, request
from flask_login import login_required

from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.arap_service import (
    get_ar_aging_by_customer, get_ap_aging_by_supplier,
    get_dso, get_dpo, get_top_customers, get_top_suppliers,
    get_customer_revenue_breakdown,
)

arap_bp = Blueprint('arap', __name__)


@arap_bp.route('/')
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

    ar = get_ar_aging_by_customer(company_id)
    ap = get_ap_aging_by_supplier(company_id)
    dso = get_dso(company_id, fiscal_year_id) if fiscal_year_id else None
    dpo = get_dpo(company_id, fiscal_year_id) if fiscal_year_id else None

    company = db.session.get(Company, company_id)

    return render_template('arap/index.html',
                           ar=ar, ap=ap, dso=dso, dpo=dpo,
                           company=company, fiscal_years=fiscal_years,
                           current_fy_id=fiscal_year_id)


@arap_bp.route('/receivables')
@login_required
def receivables():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    ar = get_ar_aging_by_customer(company_id)
    company = db.session.get(Company, company_id)

    return render_template('arap/receivables.html', ar=ar, company=company)


@arap_bp.route('/payables')
@login_required
def payables():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    ap = get_ap_aging_by_supplier(company_id)
    company = db.session.get(Company, company_id)

    return render_template('arap/payables.html', ap=ap, company=company)


@arap_bp.route('/api/top-customers')
@login_required
def api_top_customers():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not company_id or not fiscal_year_id:
        return jsonify({'error': 'Missing params'}), 400

    top = get_top_customers(company_id, fiscal_year_id)
    return jsonify({
        'labels': [c['customer_name'] for c in top],
        'values': [c['total_amount'] for c in top],
    })


@arap_bp.route('/api/top-suppliers')
@login_required
def api_top_suppliers():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not company_id or not fiscal_year_id:
        return jsonify({'error': 'Missing params'}), 400

    top = get_top_suppliers(company_id, fiscal_year_id)
    return jsonify({
        'labels': [s['supplier_name'] for s in top],
        'values': [s['total_amount'] for s in top],
    })


@arap_bp.route('/api/revenue-breakdown')
@login_required
def api_revenue_breakdown():
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    if not company_id or not fiscal_year_id:
        return jsonify({'error': 'Missing params'}), 400

    breakdown = get_customer_revenue_breakdown(company_id, fiscal_year_id)
    return jsonify(breakdown)
