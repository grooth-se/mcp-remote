from datetime import date
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.salary import Employee, SalaryRun, SalaryEntry
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.models.audit import AuditLog
from app.forms.salary import (
    EmployeeForm, SalaryRunForm, SalaryEntryEditForm,
    SalaryPayForm, CollectumPeriodForm,
)
from app.services.salary_service import (
    create_salary_run, recalculate_salary_entry, recalculate_all_entries,
    approve_salary_run, mark_salary_run_paid,
    generate_salary_slip, generate_agi_data, generate_collectum_data,
)

salary_bp = Blueprint('salary', __name__)


def _get_active_context():
    """Return (company_id, company, active_fy) or redirect."""
    company_id = session.get('active_company_id')
    if not company_id:
        return None, None, None
    company = db.session.get(Company, company_id)
    if not company:
        return None, None, None
    active_fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()
    return company_id, company, active_fy


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@salary_bp.route('/')
@login_required
def index():
    company_id, company, active_fy = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    recent_runs = SalaryRun.query.filter_by(company_id=company_id).order_by(
        SalaryRun.period_year.desc(), SalaryRun.period_month.desc()
    ).limit(10).all()

    employee_count = Employee.query.filter_by(company_id=company_id, active=True).count()

    return render_template('salary/index.html',
                           company=company,
                           recent_runs=recent_runs,
                           employee_count=employee_count)


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@salary_bp.route('/employees')
@login_required
def employees():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    show_inactive = request.args.get('show_inactive', '0') == '1'
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = Employee.query.filter_by(company_id=company_id)
    if not show_inactive:
        query = query.filter_by(active=True)
    if search:
        query = query.filter(
            db.or_(Employee.last_name.ilike(f'%{search}%'), Employee.first_name.ilike(f'%{search}%'))
        )
    pagination = query.order_by(Employee.last_name, Employee.first_name).paginate(page=page, per_page=25, error_out=False)

    return render_template('salary/employees.html',
                           pagination=pagination, company=company,
                           show_inactive=show_inactive, search=search)


@salary_bp.route('/employees/new', methods=['GET', 'POST'])
@login_required
def employee_new():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.employees'))

    form = EmployeeForm()
    if form.validate_on_submit():
        emp = Employee(
            company_id=company_id,
            personal_number=form.personal_number.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            employment_start=form.employment_start.data,
            employment_end=form.employment_end.data,
            monthly_salary=form.monthly_salary.data,
            tax_table=form.tax_table.data,
            tax_column=form.tax_column.data,
            pension_plan=form.pension_plan.data,
            bank_clearing=form.bank_clearing.data,
            bank_account=form.bank_account.data,
        )
        db.session.add(emp)
        db.session.flush()

        audit = AuditLog(
            company_id=company_id,
            user_id=current_user.id,
            action='create',
            entity_type='employee',
            entity_id=emp.id,
            new_values={'name': emp.full_name},
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Anställd {emp.full_name} skapad.', 'success')
        return redirect(url_for('salary.employees'))

    return render_template('salary/employee_form.html',
                           form=form, company=company, title='Ny anställd')


@salary_bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
def employee_edit(employee_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.employees'))

    emp = db.session.get(Employee, employee_id)
    if not emp or emp.company_id != company_id:
        flash('Anställd hittades inte.', 'danger')
        return redirect(url_for('salary.employees'))

    form = EmployeeForm(obj=emp)
    if form.validate_on_submit():
        old_values = {'name': emp.full_name, 'salary': str(emp.monthly_salary)}
        form.populate_obj(emp)
        db.session.flush()

        audit = AuditLog(
            company_id=company_id,
            user_id=current_user.id,
            action='update',
            entity_type='employee',
            entity_id=emp.id,
            old_values=old_values,
            new_values={'name': emp.full_name, 'salary': str(emp.monthly_salary)},
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Anställd {emp.full_name} uppdaterad.', 'success')
        return redirect(url_for('salary.employees'))

    return render_template('salary/employee_form.html',
                           form=form, company=company,
                           title=f'Redigera {emp.full_name}',
                           employee=emp)


@salary_bp.route('/employees/<int:employee_id>/deactivate', methods=['POST'])
@login_required
def employee_deactivate(employee_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.employees'))

    emp = db.session.get(Employee, employee_id)
    if not emp or emp.company_id != company_id:
        flash('Anställd hittades inte.', 'danger')
        return redirect(url_for('salary.employees'))

    emp.active = not emp.active
    status = 'aktiverad' if emp.active else 'avaktiverad'

    audit = AuditLog(
        company_id=company_id,
        user_id=current_user.id,
        action='update',
        entity_type='employee',
        entity_id=emp.id,
        new_values={'active': emp.active},
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'{emp.full_name} {status}.', 'success')
    return redirect(url_for('salary.employees'))


# ---------------------------------------------------------------------------
# Salary runs
# ---------------------------------------------------------------------------

@salary_bp.route('/runs/new', methods=['GET', 'POST'])
@login_required
def run_new():
    company_id, company, active_fy = _get_active_context()
    if not company or not active_fy:
        flash('Inget aktivt räkenskapsår.', 'warning')
        return redirect(url_for('salary.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.index'))

    form = SalaryRunForm()
    if form.validate_on_submit():
        try:
            run = create_salary_run(
                company_id=company_id,
                fiscal_year_id=active_fy.id,
                period_year=form.period_year.data,
                period_month=form.period_month.data,
            )
            audit = AuditLog(
                company_id=company_id,
                user_id=current_user.id,
                action='create',
                entity_type='salary_run',
                entity_id=run.id,
                new_values={'period': run.period_label},
            )
            db.session.add(audit)
            db.session.commit()

            flash(f'Löneköring skapad för {run.period_label}.', 'success')
            return redirect(url_for('salary.run_view', run_id=run.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('salary/run_new.html', form=form, company=company)


@salary_bp.route('/runs/<int:run_id>')
@login_required
def run_view(run_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    run = db.session.get(SalaryRun, run_id)
    if not run or run.company_id != company_id:
        flash('Löneköring hittades inte.', 'danger')
        return redirect(url_for('salary.index'))

    pay_form = SalaryPayForm()
    return render_template('salary/run_view.html',
                           run=run, company=company, pay_form=pay_form)


@salary_bp.route('/runs/<int:run_id>/recalculate', methods=['POST'])
@login_required
def run_recalculate(run_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.run_view', run_id=run_id))

    try:
        recalculate_all_entries(run_id)
        flash('Löneköring omräknad.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('salary.run_view', run_id=run_id))


@salary_bp.route('/runs/<int:run_id>/entries/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def entry_edit(run_id, entry_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.run_view', run_id=run_id))

    entry = db.session.get(SalaryEntry, entry_id)
    if not entry or entry.salary_run_id != run_id:
        flash('Lönepost hittades inte.', 'danger')
        return redirect(url_for('salary.run_view', run_id=run_id))

    run = entry.salary_run
    if run.company_id != company_id:
        flash('Löneköring hittades inte.', 'danger')
        return redirect(url_for('salary.index'))

    if run.status != 'draft':
        flash('Kan bara ändra utkast.', 'warning')
        return redirect(url_for('salary.run_view', run_id=run_id))

    form = SalaryEntryEditForm(obj=entry)
    if form.validate_on_submit():
        try:
            overrides = {
                'gross_salary': form.gross_salary.data,
                'tax_deduction': form.tax_deduction.data,
                'other_deductions': form.other_deductions.data or 0,
                'other_additions': form.other_additions.data or 0,
                'notes': form.notes.data,
            }
            recalculate_salary_entry(entry_id, overrides)
            flash('Lönepost uppdaterad.', 'success')
            return redirect(url_for('salary.run_view', run_id=run_id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('salary/entry_edit.html',
                           form=form, entry=entry, run=run, company=company)


@salary_bp.route('/runs/<int:run_id>/approve', methods=['POST'])
@login_required
def run_approve(run_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.run_view', run_id=run_id))

    try:
        run = approve_salary_run(run_id, current_user.id)
        audit = AuditLog(
            company_id=company_id,
            user_id=current_user.id,
            action='approve',
            entity_type='salary_run',
            entity_id=run.id,
            new_values={'status': 'approved', 'verification_id': run.verification_id},
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Löneköring godkänd. Verifikation #{run.verification.verification_number} skapad.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('salary.run_view', run_id=run_id))


@salary_bp.route('/runs/<int:run_id>/pay', methods=['POST'])
@login_required
def run_pay(run_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('salary.run_view', run_id=run_id))

    form = SalaryPayForm()
    if form.validate_on_submit():
        try:
            mark_salary_run_paid(run_id, form.paid_date.data)
            flash('Löneköring markerad som betald.', 'success')
        except ValueError as e:
            flash(str(e), 'danger')

    return redirect(url_for('salary.run_view', run_id=run_id))


# ---------------------------------------------------------------------------
# Salary slips
# ---------------------------------------------------------------------------

@salary_bp.route('/runs/<int:run_id>/slips')
@login_required
def run_slips(run_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    run = db.session.get(SalaryRun, run_id)
    if not run or run.company_id != company_id:
        flash('Löneköring hittades inte.', 'danger')
        return redirect(url_for('salary.index'))

    slips = [generate_salary_slip(entry) for entry in run.entries]
    return render_template('salary/salary_slip.html',
                           slips=slips, run=run, company=company,
                           single=False)


@salary_bp.route('/runs/<int:run_id>/slips/<int:entry_id>')
@login_required
def run_slip_single(run_id, entry_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    entry = db.session.get(SalaryEntry, entry_id)
    if not entry or entry.salary_run_id != run_id:
        flash('Lönepost hittades inte.', 'danger')
        return redirect(url_for('salary.run_view', run_id=run_id))

    slip = generate_salary_slip(entry)
    return render_template('salary/salary_slip.html',
                           slips=[slip], run=entry.salary_run,
                           company=company, single=True)


# ---------------------------------------------------------------------------
# AGI
# ---------------------------------------------------------------------------

@salary_bp.route('/runs/<int:run_id>/agi')
@login_required
def run_agi(run_id):
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    run = db.session.get(SalaryRun, run_id)
    if not run or run.company_id != company_id:
        flash('Löneköring hittades inte.', 'danger')
        return redirect(url_for('salary.index'))

    agi_data = generate_agi_data(run)
    return render_template('salary/agi.html',
                           agi=agi_data, run=run, company=company)


# ---------------------------------------------------------------------------
# Collectum
# ---------------------------------------------------------------------------

@salary_bp.route('/pension/collectum', methods=['GET', 'POST'])
@login_required
def collectum():
    company_id, company, _ = _get_active_context()
    if not company:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    form = CollectumPeriodForm()
    collectum_data = None

    if form.validate_on_submit():
        collectum_data = generate_collectum_data(
            company_id, form.period_year.data, form.period_month.data
        )
        if not collectum_data:
            flash('Ingen löneköring hittades för vald period.', 'info')

    return render_template('salary/collectum.html',
                           form=form, collectum=collectum_data, company=company)
