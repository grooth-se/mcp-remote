from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, session, send_file)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.consolidation import ConsolidationGroup, ConsolidationGroupMember, IntercompanyElimination
from app.forms.consolidation import (
    ConsolidationGroupForm, AddMemberForm,
    ConsolidationReportForm, EliminationForm,
)
from app.services import consolidation_service

consolidation_bp = Blueprint('consolidation', __name__)


def _user_can_access_group(group, company_id):
    """Check if active company is parent or member of the consolidation group."""
    if group.parent_company_id == company_id:
        return True
    return any(m.company_id == company_id for m in group.members)


@consolidation_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    # Only show groups where active company is parent or member
    all_groups = ConsolidationGroup.query.order_by(ConsolidationGroup.name).all()
    groups = [g for g in all_groups if _user_can_access_group(g, company_id)]
    return render_template('consolidation/index.html', groups=groups)


@consolidation_bp.route('/groups/new', methods=['GET', 'POST'])
@login_required
def new_group():
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('consolidation.index'))

    form = ConsolidationGroupForm()
    companies = Company.query.filter_by(active=True).order_by(Company.name).all()
    form.parent_company_id.choices = [(c.id, c.name) for c in companies]

    if form.validate_on_submit():
        group = consolidation_service.create_consolidation_group(
            name=form.name.data,
            parent_company_id=form.parent_company_id.data,
            description=form.description.data,
        )
        flash(f'Koncerngrupp "{group.name}" har skapats.', 'success')
        return redirect(url_for('consolidation.view_group', group_id=group.id))

    return render_template('consolidation/group_form.html', form=form, title='Ny koncerngrupp')


@consolidation_bp.route('/groups/<int:group_id>')
@login_required
def view_group(group_id):
    company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))

    add_form = AddMemberForm()
    companies = Company.query.filter_by(active=True).order_by(Company.name).all()
    member_ids = [m.company_id for m in group.members]
    add_form.company_id.choices = [(c.id, c.name) for c in companies if c.id not in member_ids]

    report_form = ConsolidationReportForm()
    # Get distinct fiscal years across all member companies
    years = set()
    for member in group.members:
        for fy in FiscalYear.query.filter_by(company_id=member.company_id).all():
            years.add(fy.year)
    report_form.fiscal_year_year.choices = [(y, str(y)) for y in sorted(years, reverse=True)]

    return render_template('consolidation/group_view.html',
                           group=group, add_form=add_form, report_form=report_form)


@consolidation_bp.route('/groups/<int:group_id>/add-member', methods=['POST'])
@login_required
def add_member(group_id):
    company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('consolidation.view_group', group_id=group_id))

    form = AddMemberForm()
    companies = Company.query.filter_by(active=True).all()
    form.company_id.choices = [(c.id, c.name) for c in companies]

    if form.validate_on_submit():
        consolidation_service.add_member(
            group_id, form.company_id.data, form.ownership_pct.data
        )
        flash('Företag har lagts till.', 'success')

    return redirect(url_for('consolidation.view_group', group_id=group_id))


@consolidation_bp.route('/groups/<int:group_id>/remove-member/<int:company_id>', methods=['POST'])
@login_required
def remove_member(group_id, company_id):
    active_company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, active_company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('consolidation.view_group', group_id=group_id))

    consolidation_service.remove_member(group_id, company_id)
    flash('Företag har tagits bort.', 'success')
    return redirect(url_for('consolidation.view_group', group_id=group_id))


@consolidation_bp.route('/groups/<int:group_id>/report', methods=['GET', 'POST'])
@login_required
def report(group_id):
    active_company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, active_company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))

    form = ConsolidationReportForm()
    years = set()
    for member in group.members:
        for fy in FiscalYear.query.filter_by(company_id=member.company_id).all():
            years.add(fy.year)
    form.fiscal_year_year.choices = [(y, str(y)) for y in sorted(years, reverse=True)]

    report_data = None
    if form.validate_on_submit() or request.args.get('year'):
        fy_year = form.fiscal_year_year.data or request.args.get('year', type=int)
        report_type = form.report_type.data or request.args.get('type', 'pnl')
        if report_type not in ('pnl', 'balance'):
            report_type = 'pnl'

        if report_type == 'pnl':
            report_data = consolidation_service.get_consolidated_pnl(group_id, fy_year)
        else:
            report_data = consolidation_service.get_consolidated_balance_sheet(group_id, fy_year)

    return render_template('consolidation/report.html',
                           group=group, form=form, report=report_data)


@consolidation_bp.route('/groups/<int:group_id>/eliminations')
@login_required
def eliminations(group_id):
    active_company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, active_company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))

    elims = IntercompanyElimination.query.filter_by(group_id=group_id).order_by(
        IntercompanyElimination.created_at.desc()
    ).all()

    return render_template('consolidation/group_view.html',
                           group=group, eliminations=elims, show_eliminations=True,
                           add_form=AddMemberForm(), report_form=ConsolidationReportForm())


@consolidation_bp.route('/groups/<int:group_id>/eliminations/new', methods=['GET', 'POST'])
@login_required
def new_elimination(group_id):
    active_company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, active_company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('consolidation.view_group', group_id=group_id))

    form = EliminationForm()
    member_companies = [(m.company_id, m.company.name) for m in group.members]
    form.from_company_id.choices = member_companies
    form.to_company_id.choices = member_companies

    # Need a fiscal year
    fy_id = request.args.get('fiscal_year_id', type=int)
    if not fy_id and group.members:
        fy = FiscalYear.query.filter_by(
            company_id=group.members[0].company_id, status='open'
        ).first()
        fy_id = fy.id if fy else None

    if form.validate_on_submit() and fy_id:
        consolidation_service.create_elimination(
            group_id=group_id,
            fiscal_year_id=fy_id,
            from_company_id=form.from_company_id.data,
            to_company_id=form.to_company_id.data,
            account_number=form.account_number.data,
            amount=form.amount.data,
            description=form.description.data,
        )
        flash('Eliminering har skapats.', 'success')
        return redirect(url_for('consolidation.view_group', group_id=group_id))

    return render_template('consolidation/group_form.html', form=form,
                           title='Ny koncerneliminering', group=group)


@consolidation_bp.route('/groups/<int:group_id>/report/excel')
@login_required
def report_excel(group_id):
    active_company_id = session.get('active_company_id')
    group = db.session.get(ConsolidationGroup, group_id)
    if not group or not _user_can_access_group(group, active_company_id):
        flash('Gruppen hittades inte.', 'danger')
        return redirect(url_for('consolidation.index'))

    fy_year = request.args.get('year', type=int)
    report_type = request.args.get('type', 'pnl')

    if not fy_year:
        flash('Välj ett räkenskapsår.', 'warning')
        return redirect(url_for('consolidation.view_group', group_id=group_id))

    output = consolidation_service.export_consolidated_report(group_id, fy_year, report_type)
    if not output:
        flash('Kunde inte generera rapport.', 'danger')
        return redirect(url_for('consolidation.view_group', group_id=group_id))

    return send_file(output, as_attachment=True,
                     download_name=f'koncernrapport_{group.name}_{fy_year}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
