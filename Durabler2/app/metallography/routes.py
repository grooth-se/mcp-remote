"""Routes for Metallographic Examination - ASTM E45/E381, ISO 4967/4969."""
import json
from datetime import datetime
from pathlib import Path

from flask import (
    render_template, redirect, url_for, flash, request,
    current_app, send_file, Response
)
from flask_login import login_required, current_user

from . import metallography_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import (TestRecord, AnalysisResult, AuditLog, Certificate, TestPhoto,
                        ReportApproval, STATUS_DRAFT, STATUS_REJECTED)


INCLUSION_LABELS = {
    'A': 'A - Sulfide',
    'B': 'B - Alumina',
    'C': 'C - Silicate',
    'D': 'D - Globular oxide',
}


def generate_metallo_test_id():
    """Generate unique test ID for a metallographic examination."""
    today = datetime.now()
    prefix = f"MET-{today.strftime('%y%m%d')}"
    count = TestRecord.query.filter(
        TestRecord.test_id.like(f'{prefix}%')
    ).count()
    return f"{prefix}-{count + 1:03d}"


def evaluate_inclusions(inclusions, limits):
    """Build inclusion rating rows with pass/fail against acceptance limits.

    Parameters
    ----------
    inclusions : dict
        {type: severity} for types in A/B/C/D (values may be None)
    limits : dict
        {type: max acceptable severity} (values may be None)

    Returns
    -------
    rows : list of dict
        {'type', 'label', 'severity', 'limit', 'status'} per rated type
    overall : str or None
        'PASS', 'FAIL', or None when no acceptance limits are given
    """
    inclusions = inclusions or {}
    limits = limits or {}
    rows = []
    overall = None
    for t in ('A', 'B', 'C', 'D'):
        sev = inclusions.get(t)
        lim = limits.get(t)
        if sev is None and lim is None:
            continue
        status = None
        if sev is not None and lim is not None:
            status = 'PASS' if sev <= lim else 'FAIL'
            overall = 'PASS' if overall in (None, 'PASS') else 'FAIL'
            if status == 'FAIL':
                overall = 'FAIL'
        rows.append({
            'type': t,
            'label': INCLUSION_LABELS[t],
            'severity': sev,
            'limit': lim,
            'status': status,
        })
    return rows, overall


@metallography_bp.route('/')
@login_required
def index():
    """List all metallographic examinations."""
    tests = TestRecord.query.filter_by(test_method='METALLO').order_by(
        TestRecord.created_at.desc()
    ).all()
    return render_template('metallography/index.html', tests=tests)


@metallography_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create a new metallographic examination."""
    form = SpecimenForm()

    certificates = Certificate.query.order_by(
        Certificate.year.desc(), Certificate.cert_id.desc()
    ).all()
    form.certificate_id.choices = [(0, '-- Select Certificate --')] + [
        (c.id, f"{c.certificate_number_with_rev} - {c.customer or 'No customer'}")
        for c in certificates
    ]

    # Pre-fill from certificate if coming from cert page
    cert_id = request.args.get('certificate', type=int)
    if cert_id and request.method == 'GET':
        form.certificate_id.data = cert_id
        cert = Certificate.query.get(cert_id)
        if cert:
            form.material.data = cert.material
            form.specimen_id.data = cert.test_article_sn
            form.customer_specimen_info.data = cert.customer_specimen_info
            form.requirement.data = cert.requirement
            form.location_orientation.data = cert.location_orientation

    if request.method == 'POST' and not form.validate():
        for field_name, errors in form.errors.items():
            for error in errors:
                flash(f'{field_name}: {error}', 'danger')

    if form.validate_on_submit():
        certificate_id = None
        cert_number = None
        if form.certificate_id.data and form.certificate_id.data != 0:
            cert = Certificate.query.get(form.certificate_id.data)
            if cert:
                certificate_id = cert.id
                cert_number = cert.certificate_number_with_rev

        test_id = generate_metallo_test_id()

        inclusions = {
            'A': form.incl_A.data, 'B': form.incl_B.data,
            'C': form.incl_C.data, 'D': form.incl_D.data,
        }
        limits = {
            'A': form.incl_A_max.data, 'B': form.incl_B_max.data,
            'C': form.incl_C_max.data, 'D': form.incl_D_max.data,
        }
        rows, overall = evaluate_inclusions(inclusions, limits)

        test_params = {
            'rating_method': form.rating_method.data,
            'magnification': form.magnification.data,
            'micro_etchant': form.micro_etchant.data,
            'inclusions': {k: v for k, v in inclusions.items() if v is not None},
            'inclusion_limits': {k: v for k, v in limits.items() if v is not None},
            'micro_observations': form.micro_observations.data,
            'macro_etchant': form.macro_etchant.data,
            'macro_evaluation': form.macro_evaluation.data,
            'location_orientation': form.location_orientation.data,
            'overall_result': overall,
            'notes': form.notes.data,
        }

        test = TestRecord(
            test_id=test_id,
            test_method='METALLO',
            specimen_id=form.specimen_id.data,
            material=form.material.data,
            test_date=form.test_date.data or datetime.now(),
            geometry=test_params,
            status='DRAFT',
            certificate_id=certificate_id,
            certificate_number=cert_number,
            operator_id=current_user.id
        )
        db.session.add(test)
        db.session.flush()

        # Store inclusion severities as analysis results (shown in cert review)
        for t in ('A', 'B', 'C', 'D'):
            sev = inclusions.get(t)
            if sev is not None:
                db.session.add(AnalysisResult(
                    test_record_id=test.id,
                    parameter_name=f'Inclusion_{t}',
                    value=sev,
                    uncertainty=None,
                    unit='rating',
                    calculated_by_id=current_user.id
                ))

        # Photos with captions
        photo_number = 0
        for i in range(1, 7):
            photo_field = getattr(form, f'photo_{i}', None)
            caption_field = getattr(form, f'photo_{i}_caption', None)
            if photo_field and photo_field.data and getattr(photo_field.data, 'filename', ''):
                photo_number += 1
                photo_file = photo_field.data
                photo_file.seek(0)
                photo_data = photo_file.read()
                caption = (caption_field.data if caption_field and caption_field.data
                           else f'Image {photo_number}')
                db_photo = TestPhoto(
                    test_record_id=test.id,
                    photo_number=photo_number,
                    description=caption,
                    uploaded_by_id=current_user.id
                )
                db_photo.set_image(photo_data, photo_file.filename)
                db.session.add(db_photo)

        if any(v is not None for v in inclusions.values()) or form.macro_evaluation.data:
            test.status = 'ANALYZED'

        audit = AuditLog(
            user_id=current_user.id,
            action='CREATE',
            table_name='test_record',
            record_id=test.id,
            new_values=json.dumps({'test_id': test.test_id, 'test_method': 'METALLO'})
        )
        db.session.add(audit)
        db.session.commit()

        result_msg = f' - Result: {overall}' if overall else ''
        flash(f'Metallographic examination {test.test_id} created.{result_msg}', 'success')
        return redirect(url_for('metallography.view', test_id=test.id))

    return render_template('metallography/new.html', form=form)


@metallography_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View metallographic examination details."""
    test = TestRecord.query.get_or_404(test_id)
    if test.test_method != 'METALLO':
        flash('Invalid test type.', 'error')
        return redirect(url_for('metallography.index'))

    test_params = test.geometry if test.geometry else {}
    rows, overall = evaluate_inclusions(
        test_params.get('inclusions', {}), test_params.get('inclusion_limits', {}))

    photos = [
        {'url': url_for('metallography.photo', test_id=test_id, photo_id=p.id),
         'caption': p.description or ''}
        for p in test.photos.order_by(TestPhoto.photo_number).all()
    ]

    return render_template('metallography/view.html',
                           test=test,
                           test_params=test_params,
                           inclusion_rows=rows,
                           overall=overall,
                           photos=photos)


@metallography_bp.route('/<int:test_id>/photo/<int:photo_id>')
@login_required
def photo(test_id, photo_id):
    """Serve photo from database."""
    p = TestPhoto.query.filter_by(id=photo_id, test_record_id=test_id).first_or_404()
    return Response(
        p.data,
        mimetype=p.mime_type or 'image/jpeg',
        headers={'Content-Disposition': f'inline; filename="{p.original_filename}"'}
    )


@metallography_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate metallographic examination report (Word)."""
    test = TestRecord.query.get_or_404(test_id)
    if test.test_method != 'METALLO':
        flash('Invalid test type.', 'error')
        return redirect(url_for('metallography.index'))

    form = ReportForm()
    if request.method == 'GET':
        form.certificate_number.data = test.certificate_number or test.test_id

    if form.validate_on_submit():
        try:
            from app.reports.routes import _generate_metallo_report

            reports_folder = Path(current_app.config['REPORTS_FOLDER'])
            drafts_folder = reports_folder / 'drafts'
            drafts_folder.mkdir(parents=True, exist_ok=True)

            safe_cert_num = (test.certificate.certificate_number_with_rev.replace(' ', '_').replace('/', '-')
                             if test.certificate else test.test_id.replace(' ', '_'))
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"{safe_cert_num}_{timestamp_str}.docx"
            output_path = drafts_folder / output_filename

            certificate = test.certificate
            _generate_metallo_report(certificate, test, output_path,
                                     include_photos=(form.include_photos.data == 'yes'))

            # Update approval record
            if test.certificate:
                approval = test.certificate.approval
                if not approval:
                    approval = ReportApproval.get_or_create_for_certificate(
                        test.certificate, current_user)
                if approval.status in (STATUS_DRAFT, STATUS_REJECTED, None):
                    approval.word_report_path = str(output_path.relative_to(reports_folder))
                    approval.status = STATUS_DRAFT

            audit = AuditLog(
                user_id=current_user.id,
                action='REPORT',
                table_name='test_record',
                record_id=test.id,
                new_values=json.dumps({'report': output_filename})
            )
            db.session.add(audit)
            db.session.commit()

            flash(f'Report generated: {output_filename}', 'success')
            if test.certificate:
                return redirect(url_for('certificates.view', cert_id=test.certificate.id))
            return send_file(
                output_path, as_attachment=True, download_name=output_filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        except Exception as e:
            flash(f'Error generating report: {e}', 'error')
            return redirect(url_for('metallography.view', test_id=test.id))

    return render_template('metallography/report.html', test=test, form=form)


@metallography_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a metallographic examination (admin only)."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('metallography.index'))

    test = TestRecord.query.get_or_404(test_id)
    if test.test_method != 'METALLO':
        flash('Invalid test type.', 'error')
        return redirect(url_for('metallography.index'))

    test_id_str = test.test_id
    audit = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        table_name='test_record',
        record_id=test.id,
        old_values=json.dumps({'test_id': test_id_str, 'test_method': 'METALLO'})
    )
    db.session.add(audit)

    AnalysisResult.query.filter_by(test_record_id=test.id).delete()
    db.session.delete(test)
    db.session.commit()

    flash(f'Metallographic examination {test_id_str} deleted.', 'success')
    return redirect(url_for('metallography.index'))
