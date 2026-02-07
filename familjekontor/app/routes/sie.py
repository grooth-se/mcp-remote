from flask import Blueprint, render_template, redirect, url_for, flash, request, session, Response
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.forms.sie import SIEImportForm, SIEExportForm
from app.services.sie_handler import read_sie_file, import_sie, export_sie

sie_bp = Blueprint('sie', __name__)


@sie_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    import_form = SIEImportForm()
    export_form = SIEExportForm()

    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    fy_choices = [(0, 'Autodetektera')] + [(fy.id, f'{fy.year} ({fy.start_date} - {fy.end_date})') for fy in fiscal_years]
    import_form.fiscal_year_id.choices = fy_choices
    export_form.fiscal_year_id.choices = [(fy.id, f'{fy.year} ({fy.start_date} - {fy.end_date})') for fy in fiscal_years]

    return render_template('sie/index.html', import_form=import_form, export_form=export_form)


@sie_bp.route('/import', methods=['POST'])
@login_required
def import_file():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('sie.index'))

    import_form = SIEImportForm()
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    fy_choices = [(0, 'Autodetektera')] + [(fy.id, f'{fy.year}') for fy in fiscal_years]
    import_form.fiscal_year_id.choices = fy_choices

    if import_form.validate_on_submit():
        file = import_form.file.data
        try:
            file_content = file.read()
            sie_data = read_sie_file(file_content=file_content)

            fiscal_year_id = import_form.fiscal_year_id.data
            if fiscal_year_id == 0:
                fiscal_year_id = None

            stats = import_sie(company_id, sie_data, fiscal_year_id)

            msg_parts = []
            if stats['accounts_created']:
                msg_parts.append(f"{stats['accounts_created']} konton skapade")
            if stats['accounts_existing']:
                msg_parts.append(f"{stats['accounts_existing']} konton fanns redan")
            if stats['verifications_created']:
                msg_parts.append(f"{stats['verifications_created']} verifikationer importerade")
            if stats['rows_created']:
                msg_parts.append(f"{stats['rows_created']} rader importerade")
            if stats['errors']:
                msg_parts.append(f"{len(stats['errors'])} fel")

            flash('SIE-import klar: ' + ', '.join(msg_parts), 'success')

            if stats['errors']:
                for err in stats['errors'][:10]:
                    flash(f'Varning: {err}', 'warning')

        except Exception as e:
            flash(f'Fel vid import: {str(e)}', 'danger')

    return redirect(url_for('sie.index'))


@sie_bp.route('/export', methods=['POST'])
@login_required
def export_file():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    export_form = SIEExportForm()
    fiscal_years = FiscalYear.query.filter_by(company_id=company_id).order_by(FiscalYear.year.desc()).all()
    export_form.fiscal_year_id.choices = [(fy.id, f'{fy.year}') for fy in fiscal_years]

    if export_form.validate_on_submit():
        try:
            sie_content = export_sie(company_id, export_form.fiscal_year_id.data)
            from app.models.company import Company
            company = db.session.get(Company, company_id)
            fy = db.session.get(FiscalYear, export_form.fiscal_year_id.data)
            filename = f'SIE4_{company.name}_{fy.year}.se'

            return Response(
                sie_content.encode('cp437', errors='replace'),
                mimetype='application/octet-stream',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            flash(f'Fel vid export: {str(e)}', 'danger')

    return redirect(url_for('sie.index'))
