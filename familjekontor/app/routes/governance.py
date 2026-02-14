from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.governance import (
    BoardMember, ShareClass, Shareholder, ShareholderHolding,
    DividendDecision, AGMMinutes, BOARD_ROLE_LABELS,
)
from app.forms.governance import (
    BoardMemberForm, ShareClassForm, ShareholderForm,
    HoldingForm, DividendForm, AGMForm,
)
from app.services.governance_service import (
    create_board_member, update_board_member, end_appointment,
    get_board_members, create_share_class, get_share_classes,
    create_shareholder, get_shareholders, add_holding,
    get_ownership_summary, get_share_register,
    create_dividend_decision, pay_dividend, get_dividends,
    create_agm_minutes, get_agm_history, get_agm,
)

governance_bp = Blueprint('governance', __name__)


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


# ---------------------------------------------------------------------------
# Board Members
# ---------------------------------------------------------------------------

@governance_bp.route('/board')
@login_required
def board():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    show_all = request.args.get('all') == '1'
    members = get_board_members(company_id, active_only=not show_all)
    return render_template('governance/board.html',
                           members=members, show_all=show_all,
                           role_labels=BOARD_ROLE_LABELS)


@governance_bp.route('/board/new', methods=['GET', 'POST'])
@login_required
def board_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.board'))

    form = BoardMemberForm()
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'personal_number': form.personal_number.data,
            'role': form.role.data,
            'title': form.title.data,
            'appointed_date': form.appointed_date.data,
            'end_date': form.end_date.data,
            'appointed_by': form.appointed_by.data,
            'email': form.email.data,
            'phone': form.phone.data,
        }
        try:
            member = create_board_member(company_id, data, created_by=current_user.id)
            flash(f'{member.name} tillagd som {member.role_label}.', 'success')
            return redirect(url_for('governance.board'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('governance/board_form.html', form=form, edit=False)


@governance_bp.route('/board/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def board_edit(member_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.board'))

    member = db.session.get(BoardMember, member_id)
    if not member or member.company_id != company_id:
        flash('Styrelseledamot hittades inte.', 'danger')
        return redirect(url_for('governance.board'))

    form = BoardMemberForm(obj=member)
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'personal_number': form.personal_number.data,
            'role': form.role.data,
            'title': form.title.data,
            'appointed_date': form.appointed_date.data,
            'end_date': form.end_date.data,
            'appointed_by': form.appointed_by.data,
            'email': form.email.data,
            'phone': form.phone.data,
        }
        try:
            update_board_member(member.id, data)
            flash('Styrelseledamot uppdaterad.', 'success')
            return redirect(url_for('governance.board'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('governance/board_form.html', form=form, edit=True, member=member)


@governance_bp.route('/board/<int:member_id>/end', methods=['POST'])
@login_required
def board_end(member_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.board'))

    member = db.session.get(BoardMember, member_id)
    if not member or member.company_id != company_id:
        flash('Styrelseledamot hittades inte.', 'danger')
        return redirect(url_for('governance.board'))

    from datetime import date
    end_date_str = request.form.get('end_date')
    if end_date_str:
        from datetime import datetime
        d = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        d = date.today()

    try:
        end_appointment(member.id, d)
        flash(f'{member.name} avgått {d}.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('governance.board'))


# ---------------------------------------------------------------------------
# Shares & Ownership
# ---------------------------------------------------------------------------

@governance_bp.route('/shares')
@login_required
def shares():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    share_classes = get_share_classes(company_id)
    shareholders = get_shareholders(company_id)
    ownership = get_ownership_summary(company_id)

    return render_template('governance/shares.html',
                           share_classes=share_classes,
                           shareholders=shareholders,
                           ownership=ownership)


@governance_bp.route('/shares/classes/new', methods=['GET', 'POST'])
@login_required
def share_class_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.shares'))

    form = ShareClassForm()
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'votes_per_share': form.votes_per_share.data,
            'par_value': form.par_value.data,
            'total_shares': form.total_shares.data,
        }
        try:
            sc = create_share_class(company_id, data, created_by=current_user.id)
            flash(f'Aktieslag "{sc.name}" skapat.', 'success')
            return redirect(url_for('governance.shares'))
        except Exception as e:
            flash(str(e), 'danger')

    return render_template('governance/share_class_form.html', form=form)


@governance_bp.route('/shares/shareholders/new', methods=['GET', 'POST'])
@login_required
def shareholder_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.shares'))

    form = ShareholderForm()
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'personal_or_org_number': form.personal_or_org_number.data,
            'address': form.address.data,
            'is_company': form.is_company.data,
        }
        try:
            sh = create_shareholder(company_id, data, created_by=current_user.id)
            flash(f'Aktieägare "{sh.name}" skapad.', 'success')
            return redirect(url_for('governance.shares'))
        except Exception as e:
            flash(str(e), 'danger')

    return render_template('governance/shareholder_form.html', form=form)


@governance_bp.route('/shares/holdings/new', methods=['GET', 'POST'])
@login_required
def holding_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.shares'))

    share_classes = get_share_classes(company_id)
    shareholders = get_shareholders(company_id)

    form = HoldingForm()
    form.share_class_id.choices = [(sc.id, sc.name) for sc in share_classes]

    if form.validate_on_submit():
        shareholder_id = request.form.get('shareholder_id', type=int)
        if not shareholder_id:
            flash('Välj en aktieägare.', 'danger')
        else:
            data = {
                'share_class_id': form.share_class_id.data,
                'shares': form.shares.data,
                'acquired_date': form.acquired_date.data,
                'acquisition_type': form.acquisition_type.data,
                'price_per_share': form.price_per_share.data,
                'note': form.note.data,
            }
            try:
                add_holding(shareholder_id, data, created_by=current_user.id)
                flash('Innehav registrerat.', 'success')
                return redirect(url_for('governance.shares'))
            except ValueError as e:
                flash(str(e), 'danger')

    return render_template('governance/holding_form.html', form=form,
                           shareholders=shareholders)


@governance_bp.route('/shares/register')
@login_required
def share_register():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    register = get_share_register(company_id)
    share_classes = get_share_classes(company_id)
    return render_template('governance/register.html',
                           register=register, share_classes=share_classes,
                           company=company)


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

@governance_bp.route('/dividends')
@login_required
def dividends():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    divs = get_dividends(company_id)
    return render_template('governance/dividends.html', dividends=divs)


@governance_bp.route('/dividends/new', methods=['GET', 'POST'])
@login_required
def dividend_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.dividends'))

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    share_classes = get_share_classes(company_id)

    form = DividendForm()
    form.fiscal_year_id.choices = [(fy.id, f'{fy.year} ({fy.start_date} – {fy.end_date})') for fy in fiscal_years]
    form.share_class_id.choices = [(0, '-- Alla aktieslag --')] + [(sc.id, sc.name) for sc in share_classes]

    if form.validate_on_submit():
        data = {
            'fiscal_year_id': form.fiscal_year_id.data,
            'decision_date': form.decision_date.data,
            'total_amount': form.total_amount.data,
            'amount_per_share': form.amount_per_share.data,
            'share_class_id': form.share_class_id.data if form.share_class_id.data else None,
            'record_date': form.record_date.data,
            'payment_date': form.payment_date.data,
        }
        try:
            div = create_dividend_decision(company_id, data, created_by=current_user.id)
            flash(f'Utdelningsbeslut registrerat: {float(div.total_amount):,.2f} kr.', 'success')
            return redirect(url_for('governance.dividends'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('governance/dividend_form.html', form=form)


@governance_bp.route('/dividends/<int:dividend_id>/pay', methods=['POST'])
@login_required
def dividend_pay(dividend_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.dividends'))
    if not active_fy:
        flash('Inget aktivt räkenskapsår.', 'warning')
        return redirect(url_for('governance.dividends'))

    try:
        pay_dividend(dividend_id, active_fy.id, created_by=current_user.id)
        flash('Utdelning utbetald och bokförd.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('governance.dividends'))


# ---------------------------------------------------------------------------
# AGM Minutes
# ---------------------------------------------------------------------------

@governance_bp.route('/agm')
@login_required
def agm_list():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    agms = get_agm_history(company_id)
    return render_template('governance/agm_list.html', agms=agms)


@governance_bp.route('/agm/new', methods=['GET', 'POST'])
@login_required
def agm_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('governance.agm_list'))

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()

    form = AGMForm()
    form.fiscal_year_id.choices = [(0, '-- Inget --')] + [(fy.id, f'{fy.year}') for fy in fiscal_years]

    if form.validate_on_submit():
        data = {
            'meeting_date': form.meeting_date.data,
            'meeting_type': form.meeting_type.data,
            'fiscal_year_id': form.fiscal_year_id.data if form.fiscal_year_id.data else None,
            'chairman': form.chairman.data,
            'minutes_taker': form.minutes_taker.data,
            'attendees': form.attendees.data,
            'resolutions': form.resolutions.data,
        }
        try:
            agm = create_agm_minutes(company_id, data, created_by=current_user.id)
            flash(f'Bolagsstämma {agm.meeting_date} registrerad.', 'success')
            return redirect(url_for('governance.agm_view', agm_id=agm.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('governance/agm_form.html', form=form)


@governance_bp.route('/agm/<int:agm_id>')
@login_required
def agm_view(agm_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    agm = get_agm(agm_id)
    if not agm or agm.company_id != company_id:
        flash('Bolagsstämma hittades inte.', 'danger')
        return redirect(url_for('governance.agm_list'))

    return render_template('governance/agm_view.html', agm=agm)
