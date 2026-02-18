"""Reports routes for certificate-centric approval workflow.

Workflow:
1. Certificate view → [Generate Report] → Creates Word doc, saves to server, status=DRAFT
2. Certificate view → [Submit for Review] → status=PENDING_REVIEW
3. Approver → [Review] → See certificate data + Word doc link
4. Approver → [Approve] → Generates PDF, status=PUBLISHED
5. Approver → [Reject] → status=REJECTED with comments, back to engineer
"""
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
    status_filter = request.args.get('status', '')

    query = ReportApproval.query

    if status_filter:
        query = query.filter(ReportApproval.status == status_filter)

    reports = query.order_by(ReportApproval.created_at.desc()).all()

    return render_template('reports/index.html',
                           reports=reports,
                           status_filter=status_filter,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/pending')
@login_required
@approver_required
def pending():
    """List reports pending approval (approvers only)."""
    reports = ReportApproval.query.filter_by(status=STATUS_PENDING)\
        .order_by(ReportApproval.submitted_at.asc())\
        .all()

    return render_template('reports/pending.html',
                           reports=reports,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/certificate/<int:cert_id>/start', methods=['POST'])
@login_required
@engineer_required
def start_approval(cert_id):
    """Start approval workflow for a certificate (create approval record)."""
    certificate = Certificate.query.get_or_404(cert_id)

    # Check if approval already exists
    if certificate.approval:
        flash(f'Approval workflow already exists for {certificate.certificate_number_with_rev}.', 'info')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Create new approval record
    approval = ReportApproval.get_or_create_for_certificate(certificate, current_user)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='START_APPROVAL',
        table_name='report_approvals',
        record_id=approval.id,
        new_values={
            'certificate_number': certificate.certificate_number_with_rev,
            'status': STATUS_DRAFT
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Approval workflow started for {certificate.certificate_number_with_rev}.', 'success')
    return redirect(url_for('certificates.view', cert_id=cert_id))


@reports_bp.route('/certificate/<int:cert_id>/generate-report', methods=['POST'])
@login_required
@engineer_required
def generate_report(cert_id):
    """Generate Word report for certificate and save to server."""
    certificate = Certificate.query.get_or_404(cert_id)

    # Get or create approval record
    if not certificate.approval:
        approval = ReportApproval.get_or_create_for_certificate(certificate, current_user)
        db.session.commit()
    else:
        approval = certificate.approval

    # Check if we can edit (DRAFT or REJECTED status)
    if approval.status not in [STATUS_DRAFT, STATUS_REJECTED]:
        flash('Cannot generate report - approval is already in progress.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Get test records for this certificate
    test_records = certificate.test_records.all()
    if not test_records:
        flash('No test records linked to this certificate.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    try:
        # Import report generators
        from utils.reporting.word_report import TensileReportGenerator

        # Create reports folder
        reports_folder = Path(current_app.config['REPORTS_FOLDER'])
        drafts_folder = reports_folder / 'drafts'
        drafts_folder.mkdir(parents=True, exist_ok=True)

        # Generate filename
        safe_cert_num = certificate.certificate_number_with_rev.replace(' ', '_').replace('/', '-')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f"{safe_cert_num}_{timestamp}.docx"
        output_path = drafts_folder / report_filename

        # For now, generate report based on first test record's type
        # TODO: Support multi-test combined reports
        test_record = test_records[0]

        if test_record.test_method == 'TENSILE':
            # Generate tensile report
            results = {r.parameter_name: r for r in test_record.results.all()}
            geometry = test_record.geometry or {}

            test_info = {
                'test_project': certificate.test_order or '',
                'customer': certificate.customer or '',
                'customer_order': certificate.customer_order or '',
                'product_sn': certificate.product_sn or '',
                'specimen_id': test_record.specimen_id or '',
                'location_orientation': certificate.location_orientation or '',
                'material': certificate.material or '',
                'certificate_number': certificate.certificate_number_with_rev,
                'test_date': test_record.test_date.strftime('%Y-%m-%d') if test_record.test_date else '',
                'test_engineer': current_user.username,
                'temperature': str(test_record.temperature) if test_record.temperature else '23',
                'strain_source': 'Displacement Only' if geometry.get('use_displacement_only') else 'Extensometer',
                'comments': ''
            }

            specimen_type = geometry.get('type', 'round')
            if specimen_type == 'round':
                dimensions = {
                    'diameter': geometry.get('D0'),
                    'final_diameter': geometry.get('D1'),
                    'gauge_length': geometry.get('L0'),
                    'final_gauge_length': geometry.get('L1'),
                    'parallel_length': geometry.get('Lp')
                }
            else:
                dimensions = {
                    'width': geometry.get('a0'),
                    'thickness': geometry.get('b0'),
                    'gauge_length': geometry.get('L0'),
                    'final_gauge_length': geometry.get('L1'),
                    'parallel_length': geometry.get('Lp')
                }

            # Convert results
            results_for_report = {}
            for name, result in results.items():
                class ResultValue:
                    def __init__(self, v, u):
                        self.value = v
                        self.uncertainty = u
                results_for_report[name] = ResultValue(result.value, result.uncertainty)

            # Map names
            result_mapping = {
                'Rp0.2': 'Rp02', 'Rp0.5': 'Rp05', 'A%': 'A_percent', 'Z%': 'Z',
                'Stress_rate_Rp02': 'stress_rate_rp02', 'Strain_rate_Rp02': 'strain_rate_rp02',
                'Stress_rate_Rm': 'stress_rate_rm', 'Strain_rate_Rm': 'strain_rate_rm'
            }
            for db_name, report_name in result_mapping.items():
                if db_name in results_for_report:
                    results_for_report[report_name] = results_for_report[db_name]

            yield_type = geometry.get('yield_method', 'offset')

            # Parse requirements from certificate
            # Format expected: "Rp0.2 min 500, Rm 600-800, A min 15%, Z min 40%"
            requirements = {}
            if certificate.requirement:
                req_text = certificate.requirement
                # Try to parse individual requirements
                import re
                # Match patterns like "Rp0.2 min 500" or "Rm: 600-800" or "A >= 15%"
                patterns = [
                    (r'Rp0\.?2[:\s]*(.*?)(?:,|;|$)', 'Rp02'),
                    (r'Rp0\.?5[:\s]*(.*?)(?:,|;|$)', 'Rp05'),
                    (r'ReH[:\s]*(.*?)(?:,|;|$)', 'ReH'),
                    (r'ReL[:\s]*(.*?)(?:,|;|$)', 'ReL'),
                    (r'Rm[:\s]*(.*?)(?:,|;|$)', 'Rm'),
                    (r'\bA[:\s]*(.*?)(?:,|;|$)', 'A'),
                    (r'\bZ[:\s]*(.*?)(?:,|;|$)', 'Z'),
                ]
                for pattern, key in patterns:
                    match = re.search(pattern, req_text, re.IGNORECASE)
                    if match:
                        requirements[key] = match.group(1).strip()

                # If no structured format, use entire text as general requirement
                if not requirements:
                    requirements['general'] = req_text

            report_data = TensileReportGenerator.prepare_report_data(
                test_info=test_info,
                dimensions=dimensions,
                results=results_for_report,
                specimen_type=specimen_type,
                yield_type=yield_type,
                requirements=requirements
            )

            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'
            generator = TensileReportGenerator(None)
            generator.generate_report(
                output_path=output_path,
                data=report_data,
                chart_path=None,
                logo_path=logo_path if logo_path.exists() else None
            )
        else:
            # For other test types, create a placeholder or use their generators
            flash(f'Report generation for {test_record.test_method} not yet implemented in this workflow.', 'warning')
            return redirect(url_for('certificates.view', cert_id=cert_id))

        # Update approval record with Word report path
        approval.word_report_path = str(output_path.relative_to(reports_folder))
        approval.status = STATUS_DRAFT

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='GENERATE_REPORT',
            table_name='report_approvals',
            record_id=approval.id,
            new_values={
                'certificate_number': certificate.certificate_number_with_rev,
                'word_report_path': approval.word_report_path
            },
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Report generated and saved: {report_filename}', 'success')

    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Report generation failed: {str(e)}', 'danger')

    return redirect(url_for('certificates.view', cert_id=cert_id))


@reports_bp.route('/certificate/<int:cert_id>/download-word')
@login_required
def download_word(cert_id):
    """Download the Word report for editing."""
    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval or not certificate.approval.word_report_path:
        flash('No Word report available.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    reports_folder = Path(current_app.config['REPORTS_FOLDER'])
    word_path = reports_folder / certificate.approval.word_report_path

    if not word_path.exists():
        flash('Word report file not found.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    return send_file(
        word_path,
        as_attachment=True,
        download_name=f"{certificate.certificate_number_with_rev.replace(' ', '_')}.docx",
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@reports_bp.route('/certificate/<int:cert_id>/upload-word-new', methods=['POST'])
@login_required
@engineer_required
def upload_word_new(cert_id):
    """Upload Word report to start approval workflow (without auto-generating)."""
    from werkzeug.utils import secure_filename

    certificate = Certificate.query.get_or_404(cert_id)

    if 'word_file' not in request.files:
        flash('No file uploaded.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    file = request.files['word_file']
    if file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if not file.filename.endswith('.docx'):
        flash('Please upload a Word document (.docx).', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Create or get approval record
    if not certificate.approval:
        approval = ReportApproval.get_or_create_for_certificate(certificate, current_user)
        db.session.commit()
    else:
        approval = certificate.approval
        if approval.status not in [STATUS_DRAFT, STATUS_REJECTED]:
            flash('Cannot upload - approval is already in progress.', 'warning')
            return redirect(url_for('certificates.view', cert_id=cert_id))

    # Save uploaded file
    reports_folder = Path(current_app.config['REPORTS_FOLDER'])
    drafts_folder = reports_folder / 'drafts'
    drafts_folder.mkdir(parents=True, exist_ok=True)

    safe_cert_num = certificate.certificate_number_with_rev.replace(' ', '_').replace('/', '-')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_cert_num}_{timestamp}.docx"
    filepath = drafts_folder / filename

    file.save(filepath)

    # Update approval record
    approval.word_report_path = str(filepath.relative_to(reports_folder))
    approval.status = STATUS_DRAFT

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='UPLOAD_REPORT_NEW',
        table_name='report_approvals',
        record_id=approval.id,
        new_values={
            'word_report_path': approval.word_report_path,
            'certificate_number': certificate.certificate_number_with_rev
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Word report uploaded: {filename}. You can now submit for approval.', 'success')
    return redirect(url_for('certificates.view', cert_id=cert_id))


@reports_bp.route('/certificate/<int:cert_id>/upload-word', methods=['POST'])
@login_required
@engineer_required
def upload_word(cert_id):
    """Upload edited Word report back to server."""
    from werkzeug.utils import secure_filename

    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval:
        flash('No approval workflow started.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if certificate.approval.status not in [STATUS_DRAFT, STATUS_REJECTED]:
        flash('Cannot upload - approval is already in progress.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if 'word_file' not in request.files:
        flash('No file uploaded.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    file = request.files['word_file']
    if file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if not file.filename.endswith('.docx'):
        flash('Please upload a Word document (.docx).', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Save uploaded file
    reports_folder = Path(current_app.config['REPORTS_FOLDER'])
    drafts_folder = reports_folder / 'drafts'
    drafts_folder.mkdir(parents=True, exist_ok=True)

    safe_cert_num = certificate.certificate_number_with_rev.replace(' ', '_').replace('/', '-')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_cert_num}_{timestamp}.docx"
    filepath = drafts_folder / filename

    file.save(filepath)

    # Update approval record
    old_path = certificate.approval.word_report_path
    certificate.approval.word_report_path = str(filepath.relative_to(reports_folder))

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='UPLOAD_REPORT',
        table_name='report_approvals',
        record_id=certificate.approval.id,
        old_values={'word_report_path': old_path},
        new_values={'word_report_path': certificate.approval.word_report_path},
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Word report uploaded: {filename}', 'success')
    return redirect(url_for('certificates.view', cert_id=cert_id))


@reports_bp.route('/certificate/<int:cert_id>/submit', methods=['POST'])
@login_required
@engineer_required
def submit(cert_id):
    """Submit certificate report for approval."""
    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval:
        flash('No approval workflow started. Generate a report first.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if not certificate.approval.can_submit:
        flash('This report cannot be submitted for approval.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if not certificate.approval.word_report_path:
        flash('Please generate a Word report first.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    certificate.approval.submit_for_approval(current_user)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='SUBMIT_FOR_APPROVAL',
        table_name='report_approvals',
        record_id=certificate.approval.id,
        new_values={
            'status': STATUS_PENDING,
            'certificate_number': certificate.certificate_number_with_rev
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Report submitted for approval: {certificate.certificate_number_with_rev}', 'success')
    return redirect(url_for('certificates.view', cert_id=cert_id))


@reports_bp.route('/certificate/<int:cert_id>/review')
@login_required
@approver_required
def review(cert_id):
    """Review page for approving/rejecting certificate report."""
    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval:
        flash('No approval workflow for this certificate.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if not certificate.approval.can_review:
        flash('This report is not pending review.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Get all test records for this certificate
    test_records = certificate.test_records.all()

    return render_template('reports/review_certificate.html',
                           certificate=certificate,
                           approval=certificate.approval,
                           test_records=test_records,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/certificate/<int:cert_id>/approve', methods=['POST'])
@login_required
@approver_required
def approve(cert_id):
    """Approve the certificate report with uploaded signed PDF.

    Simplified workflow for test phase:
    1. Approver downloads Word doc, reviews externally
    2. Approver saves as PDF and signs with external PDF software
    3. Approver uploads signed PDF here to approve and publish
    """
    import hashlib
    from werkzeug.utils import secure_filename

    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval or not certificate.approval.can_review:
        flash('This report cannot be approved.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Check for uploaded signed PDF
    if 'signed_pdf' not in request.files:
        flash('Please upload the signed PDF file.', 'warning')
        return redirect(url_for('reports.review', cert_id=cert_id))

    pdf_file = request.files['signed_pdf']
    if pdf_file.filename == '':
        flash('No PDF file selected.', 'warning')
        return redirect(url_for('reports.review', cert_id=cert_id))

    if not pdf_file.filename.lower().endswith('.pdf'):
        flash('Please upload a PDF file.', 'warning')
        return redirect(url_for('reports.review', cert_id=cert_id))

    # Save the uploaded signed PDF
    reports_folder = Path(current_app.config['REPORTS_FOLDER'])
    year = datetime.now().year
    signed_folder = reports_folder / 'signed' / str(year)
    signed_folder.mkdir(parents=True, exist_ok=True)

    safe_cert_num = certificate.certificate_number_with_rev.replace(' ', '_').replace('/', '-')
    pdf_filename = f"{safe_cert_num}_signed.pdf"
    output_pdf = signed_folder / pdf_filename

    pdf_file.save(output_pdf)

    # Calculate hash for integrity verification
    with open(output_pdf, 'rb') as f:
        pdf_hash = hashlib.sha256(f.read()).hexdigest()

    pdf_path = str(output_pdf.relative_to(reports_folder))
    timestamp = datetime.utcnow()
    approver_name = current_user.full_name or current_user.username

    # Mark as approved and published
    certificate.approval.approve(current_user)
    certificate.approval.publish(pdf_path=pdf_path, pdf_hash=pdf_hash)
    certificate.approval.signature_timestamp = timestamp
    certificate.reported = True

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='APPROVE_AND_PUBLISH',
        table_name='report_approvals',
        record_id=certificate.approval.id,
        new_values={
            'status': STATUS_PUBLISHED,
            'certificate_number': certificate.certificate_number_with_rev,
            'approved_by': approver_name,
            'signed_pdf_uploaded': True,
            'pdf_hash': pdf_hash[:16] + '...',
            'timestamp': timestamp.isoformat()
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Report approved and published: {certificate.certificate_number_with_rev}', 'success')
    return redirect(url_for('certificates.view', cert_id=cert_id))


@reports_bp.route('/certificate/<int:cert_id>/reject', methods=['POST'])
@login_required
@approver_required
def reject(cert_id):
    """Reject the certificate report with comments."""
    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval or not certificate.approval.can_review:
        flash('This report cannot be rejected.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    comments = request.form.get('comments', '').strip()
    if not comments:
        flash('Please provide a reason for rejection.', 'warning')
        return redirect(url_for('reports.review', cert_id=cert_id))

    certificate.approval.reject(current_user, comments)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='REJECT_REPORT',
        table_name='report_approvals',
        record_id=certificate.approval.id,
        new_values={
            'status': STATUS_REJECTED,
            'certificate_number': certificate.certificate_number_with_rev,
            'rejected_by': current_user.full_name or current_user.username,
            'comments': comments
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Report rejected: {certificate.certificate_number_with_rev}', 'warning')
    return redirect(url_for('reports.pending'))


@reports_bp.route('/certificate/<int:cert_id>/download-pdf')
@login_required
def download_pdf(cert_id):
    """Download the published PDF."""
    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval or not certificate.approval.can_download_signed:
        flash('PDF is not available.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    reports_folder = Path(current_app.config['REPORTS_FOLDER'])
    pdf_path = reports_folder / certificate.approval.signed_pdf_path

    if not pdf_path.exists():
        flash('PDF file not found.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"{certificate.certificate_number_with_rev.replace(' ', '_')}.pdf",
        mimetype='application/pdf'
    )


@reports_bp.route('/certificate/<int:cert_id>/replace-pdf', methods=['POST'])
@login_required
@approver_required
def replace_pdf(cert_id):
    """Replace signed PDF for an approved/published certificate."""
    import hashlib

    certificate = Certificate.query.get_or_404(cert_id)

    if not certificate.approval:
        flash('No approval record found.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if certificate.approval.status not in [STATUS_APPROVED, STATUS_PUBLISHED]:
        flash('Can only replace PDF for approved reports.', 'danger')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Check for uploaded signed PDF
    if 'signed_pdf' not in request.files:
        flash('Please upload the signed PDF file.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    pdf_file = request.files['signed_pdf']
    if pdf_file.filename == '':
        flash('No PDF file selected.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    if not pdf_file.filename.lower().endswith('.pdf'):
        flash('Please upload a PDF file.', 'warning')
        return redirect(url_for('certificates.view', cert_id=cert_id))

    # Save the uploaded signed PDF
    reports_folder = Path(current_app.config['REPORTS_FOLDER'])
    year = datetime.now().year
    signed_folder = reports_folder / 'signed' / str(year)
    signed_folder.mkdir(parents=True, exist_ok=True)

    safe_cert_num = certificate.certificate_number_with_rev.replace(' ', '_').replace('/', '-')
    pdf_filename = f"{safe_cert_num}_signed.pdf"
    output_pdf = signed_folder / pdf_filename

    # Archive old PDF if exists
    old_pdf_path = certificate.approval.signed_pdf_path
    if old_pdf_path:
        old_pdf_full = reports_folder / old_pdf_path
        if old_pdf_full.exists():
            archive_folder = reports_folder / 'archive' / str(year)
            archive_folder.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"{safe_cert_num}_{timestamp}.pdf"
            old_pdf_full.rename(archive_folder / archive_name)

    pdf_file.save(output_pdf)

    # Calculate hash for integrity verification
    with open(output_pdf, 'rb') as f:
        pdf_hash = hashlib.sha256(f.read()).hexdigest()

    pdf_path = str(output_pdf.relative_to(reports_folder))
    timestamp = datetime.utcnow()

    certificate.approval.publish(pdf_path=pdf_path, pdf_hash=pdf_hash)
    certificate.approval.signature_timestamp = timestamp
    certificate.reported = True

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='REPLACE_PDF',
        table_name='report_approvals',
        record_id=certificate.approval.id,
        old_values={'signed_pdf_path': old_pdf_path},
        new_values={
            'certificate_number': certificate.certificate_number_with_rev,
            'signed_pdf_path': pdf_path,
            'pdf_hash': pdf_hash[:16] + '...',
            'timestamp': timestamp.isoformat()
        },
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f'Signed PDF replaced: {certificate.certificate_number_with_rev}', 'success')
    return redirect(url_for('certificates.view', cert_id=cert_id))


# Legacy routes for backwards compatibility
@reports_bp.route('/<int:id>')
@login_required
def view(id):
    """View report approval details (legacy - redirects to certificate)."""
    approval = ReportApproval.query.get_or_404(id)
    if approval.certificate_id:
        return redirect(url_for('certificates.view', cert_id=approval.certificate_id))
    # Old test-record based approval
    return render_template('reports/view.html',
                           approval=approval,
                           status_labels=APPROVAL_STATUS_LABELS,
                           status_colors=STATUS_COLORS)


@reports_bp.route('/<int:id>/download')
@login_required
def download(id):
    """Download signed PDF (legacy route)."""
    approval = ReportApproval.query.get_or_404(id)

    if not approval.can_download_signed:
        flash('PDF is not available.', 'warning')
        if approval.certificate_id:
            return redirect(url_for('certificates.view', cert_id=approval.certificate_id))
        return redirect(url_for('reports.index'))

    pdf_path = Path(current_app.config['REPORTS_FOLDER']) / approval.signed_pdf_path

    if not pdf_path.exists():
        flash('PDF file not found.', 'danger')
        return redirect(url_for('reports.index'))

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"{approval.certificate_number}.pdf",
        mimetype='application/pdf'
    )


# Context processor for pending count in navbar
@reports_bp.app_context_processor
def inject_pending_count():
    """Inject pending reports count into all templates."""
    if current_user.is_authenticated and current_user.can_approve:
        return {'pending_reports_count': ReportApproval.get_pending_count()}
    return {'pending_reports_count': 0}
