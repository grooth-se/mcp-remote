"""Routes for real estate register management."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models.real_estate import RealEstate
from app.models.accounting import FiscalYear
from app.models.asset import FixedAsset
from app.forms.real_estate import RealEstateForm
from app.services.real_estate_service import (
    get_real_estates, create_real_estate, update_real_estate,
    delete_real_estate, calculate_property_tax, get_rental_income_ytd,
    get_real_estate_summary,
)

realestate_bp = Blueprint('realestate', __name__)


@realestate_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()

    summaries = get_real_estate_summary(company_id, fy.id if fy else None)
    return render_template('real_estate/index.html', summaries=summaries)


@realestate_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('realestate.index'))

    form = RealEstateForm()
    assets = FixedAsset.query.filter_by(company_id=company_id, asset_category='byggnader_mark').all()
    form.asset_id.choices = [(0, '— Ingen —')] + [(a.id, a.name) for a in assets]

    if form.validate_on_submit():
        asset_id = form.asset_id.data if form.asset_id.data != 0 else None
        prop = create_real_estate(
            company_id,
            property_name=form.property_name.data,
            fastighetsbeteckning=form.fastighetsbeteckning.data,
            street_address=form.street_address.data,
            postal_code=form.postal_code.data,
            city=form.city.data,
            taxeringsvarde=form.taxeringsvarde.data or 0,
            taxeringsvarde_year=form.taxeringsvarde_year.data,
            property_tax_rate=form.property_tax_rate.data or 0.0075,
            monthly_rent_target=form.monthly_rent_target.data or 0,
            rent_account=form.rent_account.data or '3910',
            asset_id=asset_id,
            notes=form.notes.data,
        )
        flash(f'Fastighet "{prop.property_name}" skapad.', 'success')
        return redirect(url_for('realestate.index'))

    return render_template('real_estate/form.html', form=form, prop=None)


@realestate_bp.route('/<int:prop_id>')
@login_required
def view(prop_id):
    company_id = session.get('active_company_id')
    prop = db.session.get(RealEstate, prop_id)
    if not prop or prop.company_id != company_id:
        flash('Fastighet hittades inte.', 'danger')
        return redirect(url_for('realestate.index'))

    tax = calculate_property_tax(prop)
    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()
    rental_income = get_rental_income_ytd(company_id, fy.id, prop.rent_account) if fy else 0

    return render_template('real_estate/view.html', prop=prop, tax=tax,
                           rental_income=rental_income)


@realestate_bp.route('/<int:prop_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(prop_id):
    company_id = session.get('active_company_id')
    prop = db.session.get(RealEstate, prop_id)
    if not prop or prop.company_id != company_id:
        flash('Fastighet hittades inte.', 'danger')
        return redirect(url_for('realestate.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('realestate.view', prop_id=prop_id))

    form = RealEstateForm(obj=prop)
    assets = FixedAsset.query.filter_by(company_id=company_id, asset_category='byggnader_mark').all()
    form.asset_id.choices = [(0, '— Ingen —')] + [(a.id, a.name) for a in assets]

    if form.validate_on_submit():
        asset_id = form.asset_id.data if form.asset_id.data != 0 else None
        update_real_estate(
            prop_id,
            property_name=form.property_name.data,
            fastighetsbeteckning=form.fastighetsbeteckning.data,
            street_address=form.street_address.data,
            postal_code=form.postal_code.data,
            city=form.city.data,
            taxeringsvarde=form.taxeringsvarde.data or 0,
            taxeringsvarde_year=form.taxeringsvarde_year.data,
            property_tax_rate=form.property_tax_rate.data or 0.0075,
            monthly_rent_target=form.monthly_rent_target.data or 0,
            rent_account=form.rent_account.data or '3910',
            asset_id=asset_id,
            notes=form.notes.data,
        )
        flash('Fastighet uppdaterad.', 'success')
        return redirect(url_for('realestate.view', prop_id=prop_id))

    return render_template('real_estate/form.html', form=form, prop=prop)


@realestate_bp.route('/<int:prop_id>/delete', methods=['POST'])
@login_required
def delete(prop_id):
    company_id = session.get('active_company_id')
    prop = db.session.get(RealEstate, prop_id)
    if not prop or prop.company_id != company_id:
        flash('Fastighet hittades inte.', 'danger')
        return redirect(url_for('realestate.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('realestate.index'))

    delete_real_estate(prop_id)
    flash('Fastighet inaktiverad.', 'success')
    return redirect(url_for('realestate.index'))
