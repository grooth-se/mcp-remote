from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, session, jsonify, send_file)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.forms.budget import BudgetFilterForm, BudgetCopyForm
from app.services import budget_service

budget_bp = Blueprint('budget', __name__)


def _get_active_context():
    company_id = session.get('active_company_id')
    if not company_id:
        return None, None, None
    from app.models.company import Company
    company = db.session.get(Company, company_id)
    active_fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()
    return company_id, company, active_fy


def _get_fy_choices(company_id):
    fys = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    return [(fy.id, f'{fy.year} ({fy.status})') for fy in fys]


@budget_bp.route('/')
@login_required
def index():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Valj ett foretag forst.', 'warning')
        return redirect(url_for('companies.index'))

    form = BudgetFilterForm()
    form.fiscal_year_id.choices = _get_fy_choices(company_id)
    if active_fy:
        form.fiscal_year_id.data = active_fy.id

    return render_template('budget/index.html', form=form, active_fy=active_fy)


@budget_bp.route('/grid')
@login_required
def grid():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    fy_id = request.args.get('fiscal_year_id', type=int)
    if not fy_id and active_fy:
        fy_id = active_fy.id
    if not fy_id:
        flash('Inget rakenskapsar valt.', 'warning')
        return redirect(url_for('budget.index'))

    fy = db.session.get(FiscalYear, fy_id)
    grid_data = budget_service.get_budget_grid(company_id, fy_id)

    return render_template('budget/grid_editor.html', grid=grid_data, fy=fy)


@budget_bp.route('/api/save-grid', methods=['POST'])
@login_required
def api_save_grid():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return jsonify({'error': 'Inget foretag valt'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Ingen data'}), 400

    fy_id = data.get('fiscal_year_id')
    grid_data = data.get('grid', {})

    if not fy_id:
        return jsonify({'error': 'Inget rakenskapsar'}), 400

    count = budget_service.save_budget_grid(company_id, fy_id, grid_data, current_user.id)
    return jsonify({'success': True, 'updated': count})


@budget_bp.route('/variance')
@login_required
def variance():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    fy_id = request.args.get('fiscal_year_id', type=int)
    if not fy_id and active_fy:
        fy_id = active_fy.id
    if not fy_id:
        flash('Inget rakenskapsar valt.', 'warning')
        return redirect(url_for('budget.index'))

    fy = db.session.get(FiscalYear, fy_id)
    variance_data = budget_service.get_variance_analysis(company_id, fy_id)

    return render_template('budget/variance.html', variance=variance_data, fy=fy)


@budget_bp.route('/forecast')
@login_required
def forecast():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    fy_id = request.args.get('fiscal_year_id', type=int)
    if not fy_id and active_fy:
        fy_id = active_fy.id
    if not fy_id:
        flash('Inget rakenskapsar valt.', 'warning')
        return redirect(url_for('budget.index'))

    fy = db.session.get(FiscalYear, fy_id)
    forecast_data = budget_service.get_forecast(company_id, fy_id)

    return render_template('budget/forecast.html', forecast=forecast_data, fy=fy)


@budget_bp.route('/copy', methods=['GET', 'POST'])
@login_required
def copy():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        return redirect(url_for('companies.index'))

    form = BudgetCopyForm()
    choices = _get_fy_choices(company_id)
    form.source_fiscal_year_id.choices = choices
    form.target_fiscal_year_id.choices = choices

    if form.validate_on_submit():
        count = budget_service.copy_budget_from_year(
            company_id,
            form.source_fiscal_year_id.data,
            form.target_fiscal_year_id.data,
            current_user.id,
        )
        flash(f'Kopierade {count} budgetrader.', 'success')
        return redirect(url_for('budget.index'))

    return render_template('budget/index.html', form=form, copy_form=form,
                           active_fy=active_fy, show_copy=True)


@budget_bp.route('/grid/excel')
@login_required
def grid_excel():
    company_id, company, active_fy = _get_active_context()
    if not company_id or not active_fy:
        return redirect(url_for('budget.index'))

    fy_id = request.args.get('fiscal_year_id', type=int) or active_fy.id
    output = budget_service.export_budget_to_excel(company_id, fy_id, company.name)
    return send_file(output, as_attachment=True,
                     download_name=f'budget_{company.name}_{fy_id}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@budget_bp.route('/variance/excel')
@login_required
def variance_excel():
    company_id, company, active_fy = _get_active_context()
    if not company_id or not active_fy:
        return redirect(url_for('budget.index'))

    fy_id = request.args.get('fiscal_year_id', type=int) or active_fy.id
    output = budget_service.export_variance_to_excel(company_id, fy_id, company.name)
    return send_file(output, as_attachment=True,
                     download_name=f'avvikelseanalys_{company.name}_{fy_id}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
