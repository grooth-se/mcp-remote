import os
import mimetypes
from datetime import date, datetime
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, current_app, send_file,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.models.document import Document
from app.forms.company import CompanyForm, FiscalYearForm, CertificateUploadForm
from app.services.company_service import create_company
from app.services import document_service as doc_svc
from app.utils.validators import validate_org_number
from app.models.audit import AuditLog

companies_bp = Blueprint('companies', __name__)


def _upload_dir(*parts):
    """Build an upload directory path relative to the app's configured UPLOAD_FOLDER."""
    base = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
    path = os.path.join(base, *parts)
    os.makedirs(path, exist_ok=True)
    return path


@companies_bp.route('/')
@login_required
def index():
    companies = Company.query.filter_by(active=True).order_by(Company.name).all()
    return render_template('companies/index.html', companies=companies)


@companies_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.index'))

    form = CompanyForm()
    if form.validate_on_submit():
        org = form.org_number.data.replace('-', '').replace(' ', '')
        if not validate_org_number(org):
            flash('Ogiltigt organisationsnummer.', 'danger')
            return render_template('companies/new.html', form=form)

        if Company.query.filter_by(org_number=org).first():
            flash('Företaget finns redan.', 'danger')
            return render_template('companies/new.html', form=form)

        company = create_company(
            name=form.name.data,
            org_number=org,
            company_type=form.company_type.data,
            accounting_standard=form.accounting_standard.data,
            fiscal_year_start=form.fiscal_year_start.data,
            vat_period=form.vat_period.data,
            base_currency=form.base_currency.data,
        )

        # Save address fields
        company.street_address = form.street_address.data
        company.postal_code = form.postal_code.data
        company.city = form.city.data
        company.country = form.country.data or 'Sverige'
        company.theme_color = form.theme_color.data or None

        # Handle logo upload
        if form.logo.data:
            logo_dir = _upload_dir('logos', str(company.id))
            filename = secure_filename(form.logo.data.filename)
            filepath = os.path.join(logo_dir, filename)
            form.logo.data.save(filepath)
            company.logo_path = os.path.join('logos', str(company.id), filename)

        audit = AuditLog(
            company_id=company.id, user_id=current_user.id,
            action='create', entity_type='company', entity_id=company.id,
            new_values={'name': company.name, 'org_number': company.org_number},
        )
        db.session.add(audit)
        db.session.commit()

        session['active_company_id'] = company.id
        flash(f'Företaget {company.name} har skapats.', 'success')
        return redirect(url_for('companies.view', company_id=company.id))

    return render_template('companies/new.html', form=form)


@companies_bp.route('/<int:company_id>')
@login_required
def view(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        flash('Företaget hittades inte.', 'danger')
        return redirect(url_for('companies.index'))

    fiscal_years = FiscalYear.query.filter_by(
        company_id=company_id
    ).order_by(FiscalYear.year.desc()).all()

    documents = Document.query.filter_by(
        company_id=company_id, document_type='certificate'
    ).order_by(Document.created_at.desc()).all()

    upload_form = CertificateUploadForm()

    return render_template('companies/view.html',
                           company=company,
                           fiscal_years=fiscal_years,
                           documents=documents,
                           upload_form=upload_form,
                           today=date.today())


@companies_bp.route('/<int:company_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(company_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    company = db.session.get(Company, company_id)
    if not company:
        flash('Företaget hittades inte.', 'danger')
        return redirect(url_for('companies.index'))

    form = CompanyForm(obj=company)
    if form.validate_on_submit():
        old_values = {'name': company.name}
        company.name = form.name.data
        company.accounting_standard = form.accounting_standard.data
        company.vat_period = form.vat_period.data
        company.base_currency = form.base_currency.data
        company.street_address = form.street_address.data
        company.postal_code = form.postal_code.data
        company.city = form.city.data
        company.country = form.country.data or 'Sverige'
        company.theme_color = form.theme_color.data or None

        # Handle logo upload
        if form.logo.data:
            logo_dir = _upload_dir('logos', str(company.id))
            filename = secure_filename(form.logo.data.filename)
            filepath = os.path.join(logo_dir, filename)
            form.logo.data.save(filepath)
            company.logo_path = os.path.join('logos', str(company.id), filename)

        audit = AuditLog(
            company_id=company.id, user_id=current_user.id,
            action='update', entity_type='company', entity_id=company.id,
            old_values=old_values, new_values={'name': company.name},
        )
        db.session.add(audit)
        db.session.commit()
        flash('Företaget har uppdaterats.', 'success')
        return redirect(url_for('companies.view', company_id=company.id))

    return render_template('companies/edit.html', form=form, company=company)


@companies_bp.route('/<int:company_id>/logo')
@login_required
def serve_logo(company_id):
    company = db.session.get(Company, company_id)
    if not company or not company.logo_path:
        from flask import abort
        abort(404)
    base = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
    full_path = os.path.join(base, company.logo_path)
    if not os.path.exists(full_path):
        from flask import abort
        abort(404)
    return send_file(full_path)


@companies_bp.route('/<int:company_id>/logo/delete', methods=['POST'])
@login_required
def delete_logo(company_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.edit', company_id=company_id))

    company = db.session.get(Company, company_id)
    if not company:
        flash('Företaget hittades inte.', 'danger')
        return redirect(url_for('companies.index'))

    if company.logo_path:
        base = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
        full_path = os.path.join(base, company.logo_path)
        if os.path.exists(full_path):
            os.remove(full_path)
        company.logo_path = None
        db.session.commit()
        flash('Logotypen har tagits bort.', 'success')

    return redirect(url_for('companies.edit', company_id=company_id))


@companies_bp.route('/<int:company_id>/delete', methods=['POST'])
@login_required
def delete(company_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    company = db.session.get(Company, company_id)
    if not company:
        flash('Företaget hittades inte.', 'danger')
        return redirect(url_for('companies.index'))

    company.active = False
    audit = AuditLog(
        company_id=company.id, user_id=current_user.id,
        action='delete', entity_type='company', entity_id=company.id,
        old_values={'name': company.name, 'active': True},
        new_values={'active': False},
    )
    db.session.add(audit)
    db.session.commit()

    if session.get('active_company_id') == company.id:
        session.pop('active_company_id', None)

    flash(f'Företaget {company.name} har tagits bort.', 'success')
    return redirect(url_for('companies.index'))


@companies_bp.route('/<int:company_id>/certificate/upload', methods=['POST'])
@login_required
def upload_certificate(company_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    company = db.session.get(Company, company_id)
    if not company:
        flash('Företaget hittades inte.', 'danger')
        return redirect(url_for('companies.index'))

    form = CertificateUploadForm()
    if form.validate_on_submit():
        doc, error = doc_svc.upload_document(
            company_id=company_id,
            file=form.file.data,
            doc_type='certificate',
            description=form.description.data,
            valid_from=form.valid_from.data,
            expiry_date=form.expiry_date.data,
            user_id=current_user.id,
        )
        if doc:
            flash(f'Dokumentet "{doc.file_name}" har laddats upp.', 'success')
        else:
            flash(error or 'Uppladdningen misslyckades.', 'danger')
    else:
        flash('Välj en fil att ladda upp.', 'danger')

    return redirect(url_for('companies.view', company_id=company_id))


@companies_bp.route('/<int:company_id>/certificate/<int:doc_id>/download')
@login_required
def download_certificate(company_id, doc_id):
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokumentet hittades inte.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    base = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
    full_path = os.path.join(base, doc.file_path)
    if not os.path.exists(full_path):
        flash('Filen saknas på servern.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    return send_file(full_path, as_attachment=False, download_name=doc.file_name)


@companies_bp.route('/<int:company_id>/certificate/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_certificate(company_id, doc_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokumentet hittades inte.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    base = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
    full_path = os.path.join(base, doc.file_path)
    if os.path.exists(full_path):
        os.remove(full_path)

    db.session.delete(doc)
    db.session.commit()
    flash(f'Dokumentet "{doc.file_name}" har tagits bort.', 'success')
    return redirect(url_for('companies.view', company_id=company_id))


@companies_bp.route('/<int:company_id>/fiscal-year/new', methods=['GET', 'POST'])
@login_required
def new_fiscal_year(company_id):
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('companies.view', company_id=company_id))

    company = db.session.get(Company, company_id)
    if not company:
        flash('Företaget hittades inte.', 'danger')
        return redirect(url_for('companies.index'))

    form = FiscalYearForm()
    if form.validate_on_submit():
        try:
            start = datetime.strptime(form.start_date.data, '%Y-%m-%d').date()
            end = datetime.strptime(form.end_date.data, '%Y-%m-%d').date()
        except ValueError:
            flash('Ogiltigt datumformat.', 'danger')
            return render_template('companies/fiscal_year_new.html', form=form, company=company)

        existing = FiscalYear.query.filter_by(
            company_id=company_id, year=form.year.data
        ).first()
        if existing:
            flash('Räkenskapsåret finns redan.', 'danger')
            return render_template('companies/fiscal_year_new.html', form=form, company=company)

        fy = FiscalYear(
            company_id=company_id,
            year=form.year.data,
            start_date=start,
            end_date=end,
            status='open',
        )
        db.session.add(fy)
        db.session.commit()
        flash(f'Räkenskapsår {form.year.data} har skapats.', 'success')
        return redirect(url_for('companies.view', company_id=company_id))

    return render_template('companies/fiscal_year_new.html', form=form, company=company)
