from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.asset import FixedAsset, DepreciationRun, ASSET_CATEGORY_DEFAULTS, ASSET_CATEGORY_LABELS
from app.forms.asset import FixedAssetForm, DepreciationRunForm, AssetDisposalForm
from app.services.asset_service import (
    create_asset, update_asset, get_assets, get_asset,
    get_accumulated_depreciation, calculate_monthly_depreciation,
    generate_depreciation_run, post_depreciation_run, dispose_asset,
    get_depreciation_schedule, get_asset_note_data,
)

assets_bp = Blueprint('assets', __name__)


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


@assets_bp.route('/')
@login_required
def index():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    status_filter = request.args.get('status')
    category_filter = request.args.get('category')
    assets = get_assets(company_id, status=status_filter, category=category_filter)

    total_purchase = sum(float(a.purchase_amount) for a in assets)
    total_book = sum(
        float(a.purchase_amount) - float(get_accumulated_depreciation(a.id))
        for a in assets if a.status != 'disposed'
    )

    return render_template('assets/index.html',
                           assets=assets,
                           total_purchase=total_purchase,
                           total_book=total_book,
                           category_labels=ASSET_CATEGORY_LABELS,
                           status_filter=status_filter,
                           category_filter=category_filter)


@assets_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('assets.index'))

    form = FixedAssetForm()
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'description': form.description.data,
            'asset_category': form.asset_category.data,
            'purchase_date': form.purchase_date.data,
            'purchase_amount': form.purchase_amount.data,
            'supplier_name': form.supplier_name.data,
            'invoice_reference': form.invoice_reference.data,
            'depreciation_method': form.depreciation_method.data,
            'useful_life_months': form.useful_life_months.data,
            'residual_value': form.residual_value.data,
            'depreciation_start': form.depreciation_start.data,
            'asset_account': form.asset_account.data or None,
            'depreciation_account': form.depreciation_account.data or None,
            'expense_account': form.expense_account.data or None,
        }
        try:
            asset = create_asset(company_id, data, created_by=current_user.id)
            flash(f'Tillgång {asset.asset_number} skapad.', 'success')
            return redirect(url_for('assets.view', asset_id=asset.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('assets/form.html', form=form, edit=False,
                           category_defaults=ASSET_CATEGORY_DEFAULTS)


@assets_bp.route('/<int:asset_id>')
@login_required
def view(asset_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    asset = get_asset(asset_id)
    if not asset or asset.company_id != company_id:
        flash('Tillgång hittades inte.', 'danger')
        return redirect(url_for('assets.index'))

    accumulated = get_accumulated_depreciation(asset.id)
    book_value = float(asset.purchase_amount) - float(accumulated)
    schedule = get_depreciation_schedule(asset.id)
    monthly = calculate_monthly_depreciation(asset)

    return render_template('assets/view.html',
                           asset=asset,
                           accumulated=float(accumulated),
                           book_value=book_value,
                           schedule=schedule,
                           monthly=float(monthly))


@assets_bp.route('/<int:asset_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(asset_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('assets.index'))

    asset = get_asset(asset_id)
    if not asset or asset.company_id != company_id:
        flash('Tillgång hittades inte.', 'danger')
        return redirect(url_for('assets.index'))

    form = FixedAssetForm(obj=asset)
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'description': form.description.data,
            'depreciation_method': form.depreciation_method.data,
            'useful_life_months': form.useful_life_months.data,
            'residual_value': form.residual_value.data,
            'depreciation_start': form.depreciation_start.data,
            'asset_account': form.asset_account.data,
            'depreciation_account': form.depreciation_account.data,
            'expense_account': form.expense_account.data,
            'supplier_name': form.supplier_name.data,
            'invoice_reference': form.invoice_reference.data,
        }
        try:
            update_asset(asset.id, data)
            flash('Tillgång uppdaterad.', 'success')
            return redirect(url_for('assets.view', asset_id=asset.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('assets/form.html', form=form, edit=True, asset=asset,
                           category_defaults=ASSET_CATEGORY_DEFAULTS)


@assets_bp.route('/<int:asset_id>/dispose', methods=['GET', 'POST'])
@login_required
def do_dispose(asset_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('assets.index'))
    if not active_fy:
        flash('Inget aktivt räkenskapsår.', 'warning')
        return redirect(url_for('assets.index'))

    asset = get_asset(asset_id)
    if not asset or asset.company_id != company_id:
        flash('Tillgång hittades inte.', 'danger')
        return redirect(url_for('assets.index'))

    accumulated = get_accumulated_depreciation(asset.id)
    book_value = float(asset.purchase_amount) - float(accumulated)

    form = AssetDisposalForm()
    if form.validate_on_submit():
        try:
            dispose_asset(
                asset.id,
                form.disposal_date.data,
                form.disposal_amount.data,
                active_fy.id,
                created_by=current_user.id,
            )
            flash(f'Tillgång {asset.asset_number} avyttrad.', 'success')
            return redirect(url_for('assets.view', asset_id=asset.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('assets/dispose.html', form=form, asset=asset,
                           accumulated=float(accumulated), book_value=book_value)


@assets_bp.route('/depreciation')
@login_required
def depreciation_list():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    runs = DepreciationRun.query.filter_by(
        company_id=company_id
    ).order_by(DepreciationRun.period_date.desc()).all()

    return render_template('assets/depreciation.html', runs=runs)


@assets_bp.route('/depreciation/new', methods=['GET', 'POST'])
@login_required
def depreciation_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('assets.index'))
    if not active_fy:
        flash('Inget aktivt räkenskapsår.', 'warning')
        return redirect(url_for('assets.index'))

    form = DepreciationRunForm()
    if form.validate_on_submit():
        try:
            run = generate_depreciation_run(
                company_id, active_fy.id,
                form.period_date.data,
                created_by=current_user.id,
            )
            if run.total_amount <= 0:
                flash('Inga tillgångar att avskriva för denna period.', 'warning')
                db.session.delete(run)
                db.session.commit()
                return redirect(url_for('assets.depreciation_list'))
            flash(f'Avskrivningskörning genererad: {float(run.total_amount):,.2f} kr.', 'success')
            return redirect(url_for('assets.depreciation_list'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('assets/depreciation_form.html', form=form)


@assets_bp.route('/depreciation/<int:run_id>/post', methods=['POST'])
@login_required
def depreciation_post(run_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('assets.depreciation_list'))

    run = db.session.get(DepreciationRun, run_id)
    if not run or run.company_id != company_id:
        flash('Avskrivningskörning hittades inte.', 'danger')
        return redirect(url_for('assets.depreciation_list'))

    try:
        post_depreciation_run(run.id, created_by=current_user.id)
        flash('Avskrivningskörningen är bokförd.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('assets.depreciation_list'))
