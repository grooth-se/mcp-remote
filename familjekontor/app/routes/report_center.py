from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify, request, send_file
from flask_login import login_required, current_user

from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.report_center_service import (
    get_available_reports, save_report_config, get_saved_reports,
    delete_saved_report, generate_report_pdf,
)

report_center_bp = Blueprint('report_center', __name__)


@report_center_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    reports = get_available_reports()
    saved = get_saved_reports(company_id, current_user.id)

    # Group by category
    categories = {}
    for r in reports:
        cat = r['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    company = db.session.get(Company, company_id)
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    return render_template('report_center/index.html',
                           categories=categories, saved=saved,
                           company=company, fiscal_years=fiscal_years)


@report_center_bp.route('/save', methods=['POST'])
@login_required
def save():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'error': 'No company'}), 400

    data = request.get_json()
    if not data or not data.get('name') or not data.get('report_type'):
        return jsonify({'error': 'Missing fields'}), 400

    sr = save_report_config(
        company_id, current_user.id,
        data['name'], data['report_type'],
        data.get('parameters'),
    )
    return jsonify({'id': sr.id, 'name': sr.name}), 201


@report_center_bp.route('/saved/<int:report_id>/delete', methods=['POST'])
@login_required
def delete(report_id):
    success = delete_saved_report(report_id, current_user.id)
    if success:
        flash('Sparad rapport borttagen.', 'success')
    else:
        flash('Kunde inte ta bort rapporten.', 'danger')
    return redirect(url_for('report_center.index'))


@report_center_bp.route('/pdf/<report_type>')
@login_required
def pdf(report_type):
    company_id = session.get('active_company_id')
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)

    if not company_id or not fiscal_year_id:
        flash('Välj företag och räkenskapsår.', 'warning')
        return redirect(url_for('report_center.index'))

    fy_b_id = request.args.get('fy_b_id', type=int)
    output = generate_report_pdf(report_type, company_id, fiscal_year_id, fy_b_id=fy_b_id)

    if output is None:
        flash('PDF kunde inte genereras (WeasyPrint ej tillgänglig eller ogiltig rapporttyp).', 'warning')
        return redirect(url_for('report_center.index'))

    company = db.session.get(Company, company_id)
    fy = db.session.get(FiscalYear, fiscal_year_id)

    return send_file(output,
                     download_name=f'{report_type}_{company.name}_{fy.year}.pdf',
                     as_attachment=True,
                     mimetype='application/pdf')
