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
    approval = ReportApproval.query.get_or_404(id)

    if approval.status != STATUS_APPROVED:
        flash('Only approved reports can be signed.', 'danger')
        return redirect(url_for('reports.view', id=id))

    if request.method == 'POST':
        # Phase 3 will implement actual PDF signing
        # For now, just mark as published with placeholder

        # Generate signed PDF path
        year = datetime.now().year
        signed_folder = Path(current_app.config['REPORTS_FOLDER']) / 'signed' / str(year)
        signed_folder.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"{approval.certificate_number.replace(' ', '_')}_signed.pdf"
        pdf_path = signed_folder / pdf_filename

        # Placeholder: In Phase 3, we'll actually convert and sign the PDF
        # For now, create a simple placeholder
        import hashlib
        placeholder_hash = hashlib.sha256(
            f"{approval.certificate_number}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()

        approval.publish(
            pdf_path=str(pdf_path.relative_to(current_app.config['REPORTS_FOLDER'])),
            pdf_hash=placeholder_hash
        )

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='PUBLISH_REPORT',
            table_name='report_approvals',
            record_id=approval.id,
            new_values={
                'status': STATUS_PUBLISHED,
                'certificate_number': approval.certificate_number,
                'signed_by': current_user.full_name or current_user.username,
                'pdf_hash': placeholder_hash[:16] + '...'
            },
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Report {approval.certificate_number} signed and published.', 'success')
        return redirect(url_for('reports.view', id=id))

    return render_template('reports/sign.html',
                           approval=approval,
                           status_labels=APPROVAL_STATUS_LABELS)


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
