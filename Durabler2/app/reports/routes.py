"""Reports routes for approval workflow."""
from datetime import datetime
from pathlib import Path
from flask import (
    render_template, redirect, url_for, flash, request,
    current_app, send_file, abort
)
from flask_login import login_required, current_user

from . import reports_bp
from app.extensions import db
from app.models import (
    ReportApproval, TestRecord, AuditLog, Certificate,
    STATUS_DRAFT, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_PUBLISHED,
    APPROVAL_STATUS_LABELS, STATUS_COLORS,
    approver_required, engineer_required
)


@reports_bp.route('/')
@login_required
def index():
    """List all reports with approval status."""
    # Get filter parameters
    status_filter = request.args.get('status', '')
    test_method_filter = request.args.get('test_method', '')

    # Build query
    query = ReportApproval.query.join(TestRecord)

    if status_filter:
        query = query.filter(ReportApproval.status == status_filter)

    if test_method_filter:
        query = query.filter(TestRecord.test_method == test_method_filter)

    # Order by most recent first
    reports = query.order_by(ReportApproval.created_at.desc()).all()

    # Get unique test methods for filter dropdown
    test_methods = db.session.query(TestRecord.test_method).distinct().all()
    test_methods = [tm[0] for tm in test_methods if tm[0]]

    return render_template('reports/index.html',
                           reports=reports,
                           status_filter=status_filter,
                           test_method_filter=test_method_filter,
                           test_methods=test_methods,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/create-from-test/<int:test_id>', methods=['POST'])
@login_required
@engineer_required
def create_from_test(test_id):
    """Create a new approval record for a test record."""
    test_record = TestRecord.query.get_or_404(test_id)

    # Check if approval already exists
    if test_record.approval:
        flash(f'Approval record already exists for {test_record.test_id}.', 'info')
        return redirect(url_for('reports.view', id=test_record.approval.id))

    # Create new approval record
    approval = ReportApproval.get_or_create(test_record, current_user)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='CREATE_APPROVAL',
        table_name='report_approvals',
        record_id=approval.id,
        new_values={
            'test_id': test_record.test_id,
            'test_method': test_record.test_method,
            'certificate_number': test_record.certificate_number
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Approval workflow started for {test_record.test_id}.', 'success')

    # Redirect back to certificate view if there's a certificate, otherwise to reports
    if test_record.certificate_id:
        return redirect(url_for('certificates.view', cert_id=test_record.certificate_id))
    return redirect(url_for('reports.view', id=approval.id))


@reports_bp.route('/pending')
@login_required
@approver_required
def pending():
    """List reports pending approval (approvers only)."""
    reports = ReportApproval.query.filter_by(status=STATUS_PENDING)\
        .join(TestRecord)\
        .order_by(ReportApproval.submitted_at.asc())\
        .all()

    return render_template('reports/pending.html',
                           reports=reports,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/<int:id>')
@login_required
def view(id):
    """View report approval details."""
    approval = ReportApproval.query.get_or_404(id)

    return render_template('reports/view.html',
                           approval=approval,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/<int:id>/submit', methods=['POST'])
@login_required
@engineer_required
def submit(id):
    """Submit report for approval."""
    approval = ReportApproval.query.get_or_404(id)

    if not approval.can_submit:
        flash('This report cannot be submitted for approval.', 'danger')
        return redirect(url_for('reports.view', id=id))

    # Check if Word report exists
    if not approval.word_report_path:
        flash('Please generate the Word report first before submitting.', 'warning')
        return redirect(url_for('reports.view', id=id))

    approval.submit_for_approval(current_user)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='SUBMIT_FOR_APPROVAL',
        table_name='report_approvals',
        record_id=approval.id,
        new_values={
            'status': STATUS_PENDING,
            'certificate_number': approval.certificate_number
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Report {approval.certificate_number} submitted for approval.', 'success')
    return redirect(url_for('reports.view', id=id))


@reports_bp.route('/<int:id>/review')
@login_required
@approver_required
def review(id):
    """Review page for approving/rejecting report."""
    approval = ReportApproval.query.get_or_404(id)

    if not approval.can_review:
        flash('This report is not pending review.', 'warning')
        return redirect(url_for('reports.view', id=id))

    return render_template('reports/review.html',
                           approval=approval,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/<int:id>/approve', methods=['POST'])
@login_required
@approver_required
def approve(id):
    """Approve the report."""
    approval = ReportApproval.query.get_or_404(id)

    if not approval.can_review:
        flash('This report cannot be approved.', 'danger')
        return redirect(url_for('reports.view', id=id))

    approval.approve(current_user)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='APPROVE_REPORT',
        table_name='report_approvals',
        record_id=approval.id,
        new_values={
            'status': STATUS_APPROVED,
            'certificate_number': approval.certificate_number,
            'reviewed_by': current_user.full_name or current_user.username
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Report {approval.certificate_number} approved. Ready for signing.', 'success')

    # Redirect to sign page (will be implemented in Phase 3)
    return redirect(url_for('reports.sign', id=id))


@reports_bp.route('/<int:id>/reject', methods=['POST'])
@login_required
@approver_required
def reject(id):
    """Reject the report with comments."""
    approval = ReportApproval.query.get_or_404(id)

    if not approval.can_review:
        flash('This report cannot be rejected.', 'danger')
        return redirect(url_for('reports.view', id=id))

    comments = request.form.get('comments', '').strip()
    if not comments:
        flash('Please provide a reason for rejection.', 'warning')
        return redirect(url_for('reports.review', id=id))

    approval.reject(current_user, comments)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='REJECT_REPORT',
        table_name='report_approvals',
        record_id=approval.id,
        new_values={
            'status': STATUS_REJECTED,
            'certificate_number': approval.certificate_number,
            'reviewed_by': current_user.full_name or current_user.username,
            'comments': comments
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Report {approval.certificate_number} rejected and returned for revision.', 'warning')
    return redirect(url_for('reports.index'))


@reports_bp.route('/<int:id>/sign', methods=['GET', 'POST'])
@login_required
@approver_required
def sign(id):
    """Sign and publish the approved report."""
    from utils.reporting.pdf_signer import (
        sign_report, create_placeholder_signed_pdf,
        check_dependencies, PDFSigningError, CertificateError
    )

    approval = ReportApproval.query.get_or_404(id)

    if approval.status != STATUS_APPROVED:
        flash('Only approved reports can be signed.', 'danger')
        return redirect(url_for('reports.view', id=id))

    # Check signing capabilities
    deps = check_dependencies()
    can_sign = deps['can_sign'] and deps['can_convert']

    # Get certificate configuration
    certs_folder = Path(current_app.config.get('CERTS_FOLDER', 'certs'))
    cert_file = current_app.config.get('COMPANY_CERT_FILE', 'durabler_company.p12')
    cert_password = current_app.config.get('COMPANY_CERT_PASSWORD', '')
    cert_path = certs_folder / cert_file
    has_certificate = cert_path.exists()

    if request.method == 'POST':
        reports_folder = Path(current_app.config['REPORTS_FOLDER'])

        # Get Word report path
        word_report_path = None
        if approval.word_report_path:
            word_report_path = reports_folder / approval.word_report_path
            if not word_report_path.exists():
                # Try alternate location
                word_report_path = Path(approval.word_report_path)

        signer_name = current_user.full_name or current_user.username
        signer_user_id = current_user.user_id or str(current_user.id)

        try:
            if can_sign and has_certificate and word_report_path and word_report_path.exists():
                # Full PDF signing with X.509 certificate
                result = sign_report(
                    word_report_path=word_report_path,
                    output_folder=reports_folder,
                    certificate_number=approval.certificate_number,
                    cert_path=cert_path,
                    cert_password=cert_password,
                    signer_name=signer_name,
                    signer_user_id=signer_user_id
                )
                signing_method = 'X.509 Digital Signature'
            else:
                # Fallback to placeholder (conversion without signing)
                if word_report_path and word_report_path.exists():
                    result = create_placeholder_signed_pdf(
                        word_report_path=word_report_path,
                        output_folder=reports_folder,
                        certificate_number=approval.certificate_number,
                        signer_name=signer_name,
                        signer_user_id=signer_user_id
                    )
                    signing_method = 'PDF Conversion (no digital signature)'
                else:
                    # No Word report available - create minimal placeholder
                    result = create_placeholder_signed_pdf(
                        word_report_path=Path('/dev/null'),  # Non-existent path
                        output_folder=reports_folder,
                        certificate_number=approval.certificate_number,
                        signer_name=signer_name,
                        signer_user_id=signer_user_id
                    )
                    signing_method = 'Placeholder (no source document)'

            # Update approval record
            approval.publish(
                pdf_path=result['pdf_path'],
                pdf_hash=result['pdf_hash']
            )
            approval.signature_timestamp = result['timestamp']

            # Audit log with detailed signing information
            audit = AuditLog(
                user_id=current_user.id,
                action='PUBLISH_REPORT',
                table_name='report_approvals',
                record_id=approval.id,
                new_values={
                    'status': STATUS_PUBLISHED,
                    'certificate_number': approval.certificate_number,
                    'signed_by': signer_name,
                    'signer_user_id': signer_user_id,
                    'signing_method': signing_method,
                    'pdf_hash': result['pdf_hash'][:16] + '...',
                    'timestamp': result['timestamp'].isoformat()
                },
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

            if result.get('is_placeholder'):
                flash(f'Report {approval.certificate_number} published (PDF converted, digital signature not available).', 'warning')
            else:
                flash(f'Report {approval.certificate_number} digitally signed and published.', 'success')

            return redirect(url_for('reports.view', id=id))

        except (PDFSigningError, CertificateError) as e:
            flash(f'Signing failed: {str(e)}', 'danger')
            return redirect(url_for('reports.sign', id=id))

    # GET request - show signing page with status info
    return render_template('reports/sign.html',
                           approval=approval,
                           status_labels=APPROVAL_STATUS_LABELS,
                           can_sign=can_sign,
                           has_certificate=has_certificate,
                           signing_deps=deps)


@reports_bp.route('/<int:id>/download')
@login_required
def download(id):
    """Download the signed PDF."""
    approval = ReportApproval.query.get_or_404(id)

    if not approval.can_download_signed:
        flash('Signed PDF is not available for this report.', 'warning')
        return redirect(url_for('reports.view', id=id))

    pdf_path = Path(current_app.config['REPORTS_FOLDER']) / approval.signed_pdf_path

    if not pdf_path.exists():
        flash('Signed PDF file not found.', 'danger')
        return redirect(url_for('reports.view', id=id))

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"{approval.certificate_number}_signed.pdf",
        mimetype='application/pdf'
    )


# Context processor to make pending count available in templates
@reports_bp.app_context_processor
def inject_pending_count():
    """Inject pending reports count into all templates."""
    if current_user.is_authenticated and current_user.can_approve:
        return {'pending_reports_count': ReportApproval.get_pending_count()}
    return {'pending_reports_count': 0}
