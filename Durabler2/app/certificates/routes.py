"""Certificate register routes."""
from datetime import datetime, date

from flask import (render_template, redirect, url_for, flash, request,
                   jsonify)
from flask_login import login_required, current_user

from . import certificates_bp
from .forms import CertificateForm, CertificateSearchForm
from app.extensions import db
from app.models import AuditLog
from app.models.certificate import Certificate


@certificates_bp.route('/')
@login_required
def index():
    """List all certificates with filtering."""
    # Get filter parameters
    year_filter = request.args.get('year', '')
    search_term = request.args.get('search', '')

    # Build query
    query = Certificate.query

    if year_filter and year_filter != 'All':
        try:
            query = query.filter(Certificate.year == int(year_filter))
        except ValueError:
            pass

    if search_term:
        search_pattern = f'%{search_term}%'
        query = query.filter(
            db.or_(
                Certificate.test_project.ilike(search_pattern),
                Certificate.project_name.ilike(search_pattern),
                Certificate.customer.ilike(search_pattern),
                Certificate.customer_order.ilike(search_pattern),
                Certificate.product_sn.ilike(search_pattern),
                Certificate.specimen_id.ilike(search_pattern),
                Certificate.material.ilike(search_pattern),
                Certificate.comment.ilike(search_pattern)
            )
        )

    # Order by year desc, cert_id desc
    certificates = query.order_by(
        Certificate.year.desc(),
        Certificate.cert_id.desc(),
        Certificate.revision.desc()
    ).limit(500).all()

    # Get years for filter dropdown
    years = Certificate.get_years_list()
    current_year = datetime.now().year
    if current_year not in years:
        years.insert(0, current_year)

    return render_template('certificates/index.html',
                           certificates=certificates,
                           years=years,
                           year_filter=year_filter,
                           search_term=search_term)


@certificates_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new certificate."""
    form = CertificateForm()

    if request.method == 'GET':
        # Pre-fill with defaults
        current_year = datetime.now().year
        next_id = Certificate.get_next_cert_id(current_year)
        form.year.data = current_year
        form.cert_id.data = next_id
        form.revision.data = 1
        form.cert_date.data = date.today()

    if form.validate_on_submit():
        # Check if certificate already exists
        existing = Certificate.query.filter_by(
            year=form.year.data,
            cert_id=form.cert_id.data,
            revision=form.revision.data
        ).first()

        if existing:
            flash(f'Certificate DUR-{form.year.data}-{form.cert_id.data} Rev.{form.revision.data} already exists!', 'danger')
            return render_template('certificates/edit.html', form=form, is_new=True)

        cert = Certificate(
            year=form.year.data,
            cert_id=form.cert_id.data,
            revision=form.revision.data,
            cert_date=form.cert_date.data,
            test_project=form.test_project.data,
            project_name=form.project_name.data,
            test_standard=form.test_standard.data,
            customer=form.customer.data,
            customer_order=form.customer_order.data,
            product=form.product.data,
            product_sn=form.product_sn.data,
            material=form.material.data,
            specimen_id=form.specimen_id.data,
            location_orientation=form.location_orientation.data,
            temperature=form.temperature.data,
            comment=form.comment.data,
            reported=form.reported.data,
            invoiced=form.invoiced.data,
            created_by_id=current_user.id
        )

        db.session.add(cert)

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='CREATE',
            table_name='certificates',
            new_values={'certificate_number': cert.certificate_number},
            ip_address=request.remote_addr
        )
        db.session.add(audit)

        db.session.commit()

        flash(f'Certificate {cert.certificate_number} created successfully!', 'success')
        return redirect(url_for('certificates.view', cert_id=cert.id))

    return render_template('certificates/edit.html', form=form, is_new=True)


@certificates_bp.route('/<int:cert_id>')
@login_required
def view(cert_id):
    """View certificate details."""
    cert = Certificate.query.get_or_404(cert_id)

    # Get linked test records
    test_records = cert.test_records.all() if cert.test_records else []

    return render_template('certificates/view.html',
                           cert=cert,
                           test_records=test_records)


@certificates_bp.route('/<int:cert_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(cert_id):
    """Edit certificate."""
    cert = Certificate.query.get_or_404(cert_id)
    form = CertificateForm(obj=cert)

    if form.validate_on_submit():
        # Store old values for audit
        old_values = {
            'certificate_number': cert.certificate_number,
            'customer': cert.customer,
            'test_project': cert.test_project
        }

        # Update certificate
        cert.year = form.year.data
        cert.cert_id = form.cert_id.data
        cert.revision = form.revision.data
        cert.cert_date = form.cert_date.data
        cert.test_project = form.test_project.data
        cert.project_name = form.project_name.data
        cert.test_standard = form.test_standard.data
        cert.customer = form.customer.data
        cert.customer_order = form.customer_order.data
        cert.product = form.product.data
        cert.product_sn = form.product_sn.data
        cert.material = form.material.data
        cert.specimen_id = form.specimen_id.data
        cert.location_orientation = form.location_orientation.data
        cert.temperature = form.temperature.data
        cert.comment = form.comment.data
        cert.reported = form.reported.data
        cert.invoiced = form.invoiced.data

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='UPDATE',
            table_name='certificates',
            record_id=cert.id,
            old_values=old_values,
            new_values={'certificate_number': cert.certificate_number},
            ip_address=request.remote_addr
        )
        db.session.add(audit)

        db.session.commit()

        flash(f'Certificate {cert.certificate_number} updated!', 'success')
        return redirect(url_for('certificates.view', cert_id=cert.id))

    return render_template('certificates/edit.html', form=form, cert=cert, is_new=False)


@certificates_bp.route('/<int:cert_id>/revision', methods=['POST'])
@login_required
def create_revision(cert_id):
    """Create new revision of certificate."""
    cert = Certificate.query.get_or_404(cert_id)

    # Create new certificate with incremented revision
    new_cert = Certificate(
        year=cert.year,
        cert_id=cert.cert_id,
        revision=cert.revision + 1,
        cert_date=date.today(),
        test_project=cert.test_project,
        project_name=cert.project_name,
        test_standard=cert.test_standard,
        customer=cert.customer,
        customer_order=cert.customer_order,
        product=cert.product,
        product_sn=cert.product_sn,
        material=cert.material,
        specimen_id=cert.specimen_id,
        location_orientation=cert.location_orientation,
        temperature=cert.temperature,
        comment=f"Revision of {cert.certificate_number_with_rev}",
        reported=False,
        invoiced=False,
        created_by_id=current_user.id
    )

    db.session.add(new_cert)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='CREATE',
        table_name='certificates',
        new_values={
            'certificate_number': new_cert.certificate_number_with_rev,
            'from_revision': cert.certificate_number_with_rev
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)

    db.session.commit()

    flash(f'Created revision {new_cert.certificate_number_with_rev}', 'success')
    return redirect(url_for('certificates.edit', cert_id=new_cert.id))


@certificates_bp.route('/<int:cert_id>/delete', methods=['POST'])
@login_required
def delete(cert_id):
    """Delete certificate (admin only)."""
    if current_user.role != 'admin':
        flash('Only administrators can delete certificates.', 'danger')
        return redirect(url_for('certificates.index'))

    cert = Certificate.query.get_or_404(cert_id)

    # Check for linked test records
    if cert.test_records.count() > 0:
        flash(f'Cannot delete {cert.certificate_number} - has linked test records.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    cert_num = cert.certificate_number_with_rev

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        table_name='certificates',
        record_id=cert_id,
        old_values={'certificate_number': cert_num},
        ip_address=request.remote_addr,
        reason=request.form.get('reason', 'User requested deletion')
    )
    db.session.add(audit)

    db.session.delete(cert)
    db.session.commit()

    flash(f'Certificate {cert_num} deleted.', 'success')
    return redirect(url_for('certificates.index'))


@certificates_bp.route('/search')
@login_required
def search():
    """Search certificates (for AJAX)."""
    term = request.args.get('q', '')

    if len(term) < 2:
        return jsonify([])

    # Search by certificate number or other fields
    pattern = f'%{term}%'

    # Try parsing as certificate number first
    year, cert_id, _ = Certificate.parse_certificate_number(term)

    if year and cert_id:
        certs = Certificate.query.filter_by(year=year, cert_id=cert_id)\
            .order_by(Certificate.revision.desc()).limit(10).all()
    else:
        certs = Certificate.query.filter(
            db.or_(
                Certificate.test_project.ilike(pattern),
                Certificate.customer.ilike(pattern),
                Certificate.product_sn.ilike(pattern),
                Certificate.specimen_id.ilike(pattern)
            )
        ).order_by(Certificate.year.desc(), Certificate.cert_id.desc()).limit(10).all()

    return jsonify([{
        'id': c.id,
        'certificate_number': c.certificate_number,
        'certificate_number_with_rev': c.certificate_number_with_rev,
        'customer': c.customer or '',
        'test_project': c.test_project or ''
    } for c in certs])


@certificates_bp.route('/next-id')
@login_required
def next_id():
    """Get next certificate ID for year (AJAX)."""
    year = request.args.get('year', datetime.now().year, type=int)
    next_cert_id = Certificate.get_next_cert_id(year)
    return jsonify({'year': year, 'next_id': next_cert_id})
