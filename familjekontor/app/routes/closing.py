from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.services.accounting_service import preview_closing, close_fiscal_year

closing_bp = Blueprint('closing', __name__)


@closing_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(
        company_id=company_id
    ).order_by(FiscalYear.year.desc()).all()

    return render_template('closing/index.html', fiscal_years=fiscal_years)


@closing_bp.route('/<int:fiscal_year_id>/preview')
@login_required
def preview(fiscal_year_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    try:
        data = preview_closing(company_id, fiscal_year_id)
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('closing.index'))

    return render_template('closing/preview.html', **data)


@closing_bp.route('/<int:fiscal_year_id>/close', methods=['POST'])
@login_required
def execute_close(fiscal_year_id):
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet att stänga räkenskapsår.', 'danger')
        return redirect(url_for('closing.index'))

    try:
        result = close_fiscal_year(company_id, fiscal_year_id, created_by=current_user.id)
        flash(
            f'Räkenskapsåret {result["next_fiscal_year"].year - 1} är nu stängt. '
            f'Ingående balanser har skapats för {result["next_fiscal_year"].year}.',
            'success'
        )
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('closing.index'))
