"""Sonic Resonance (E1875) test routes."""
import os
from pathlib import Path
from datetime import datetime

from flask import (render_template, redirect, url_for, flash, request,
                   current_app, send_file)
from flask_login import login_required, current_user

from . import sonic_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import analysis utilities
from utils.analysis.sonic_calculations import SonicAnalyzer, SonicResults
from utils.models.sonic_specimen import SonicSpecimen, UltrasonicMeasurements
from utils.reporting.sonic_word_report import SonicReportGenerator


def generate_test_id():
    """Generate unique test ID."""
    today = datetime.now()
    count = TestRecord.query.filter(
        TestRecord.test_method == 'SONIC',
        db.func.date(TestRecord.created_at) == today.date()
    ).count()
    return f"SON-{today.strftime('%Y%m%d')}-{count + 1:03d}"


@sonic_bp.route('/')
@login_required
def index():
    """List all sonic resonance tests."""
    tests = TestRecord.query.filter_by(test_method='SONIC')\
        .order_by(TestRecord.created_at.desc()).all()
    return render_template('sonic/index.html', tests=tests)


@sonic_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new sonic resonance test."""
    form = SpecimenForm()

    # Get certificate from URL parameter if provided
    cert_id = request.args.get('certificate', type=int)
    certificate = Certificate.query.get(cert_id) if cert_id else None

    # Pre-fill from certificate
    if request.method == 'GET' and certificate:
        if certificate.material:
            form.material.data = certificate.material
        if certificate.specimen_id:
            form.specimen_id.data = certificate.specimen_id

    if form.validate_on_submit():
        try:
            # Create specimen object
            specimen = SonicSpecimen(
                specimen_id=form.specimen_id.data,
                specimen_type=form.specimen_type.data,
                diameter=form.diameter.data or 0.0,
                side_length=form.side_length.data or 0.0,
                length=form.length.data,
                mass=form.mass.data,
                material=form.material.data or ''
            )

            # Create measurements object
            measurements = UltrasonicMeasurements(
                longitudinal_velocities=[form.vl1.data, form.vl2.data, form.vl3.data],
                shear_velocities=[form.vs1.data, form.vs2.data, form.vs3.data]
            )

            # Validate specimen dimensions
            if form.specimen_type.data == 'round' and not form.diameter.data:
                flash('Diameter is required for round specimens.', 'danger')
                return render_template('sonic/new.html', form=form, certificate=certificate)
            if form.specimen_type.data == 'square' and not form.side_length.data:
                flash('Side length is required for square specimens.', 'danger')
                return render_template('sonic/new.html', form=form, certificate=certificate)

            # Run analysis
            analyzer = SonicAnalyzer()
            results = analyzer.run_analysis(specimen, measurements)

            # Build geometry dict
            geometry = {
                'type': form.specimen_type.data,
                'diameter': form.diameter.data if form.specimen_type.data == 'round' else None,
                'side_length': form.side_length.data if form.specimen_type.data == 'square' else None,
                'length': form.length.data,
                'mass': form.mass.data,
                'density': specimen.density,
                'volume': specimen.volume,
                # Store velocity measurements
                'vl1': form.vl1.data,
                'vl2': form.vl2.data,
                'vl3': form.vl3.data,
                'vs1': form.vs1.data,
                'vs2': form.vs2.data,
                'vs3': form.vs3.data,
            }

            # Create test record
            test_id = generate_test_id()
            cert_number = certificate.certificate_number_with_rev if certificate else None

            test_record = TestRecord(
                test_id=test_id,
                test_method='SONIC',
                test_standard=form.test_standard.data,
                specimen_id=form.specimen_id.data,
                material=form.material.data,
                batch_number=form.batch_number.data,
                geometry=geometry,
                test_date=datetime.now(),
                temperature=form.test_temperature.data,
                status='ANALYZED',
                certificate_id=cert_id,
                certificate_number=cert_number,
                operator_id=current_user.id
            )
            db.session.add(test_record)
            db.session.flush()

            # Store results
            results_data = [
                ('Density', results.density.value, results.density.uncertainty, 'kg/m³'),
                ('Vl', results.longitudinal_velocity.value, results.longitudinal_velocity.uncertainty, 'm/s'),
                ('Vs', results.shear_velocity.value, results.shear_velocity.uncertainty, 'm/s'),
                ('Poisson', results.poissons_ratio.value, results.poissons_ratio.uncertainty, '-'),
                ('G', results.shear_modulus.value, results.shear_modulus.uncertainty, 'GPa'),
                ('E', results.youngs_modulus.value, results.youngs_modulus.uncertainty, 'GPa'),
                ('ff', results.flexural_frequency.value, results.flexural_frequency.uncertainty, 'Hz'),
                ('ft', results.torsional_frequency.value, results.torsional_frequency.uncertainty, 'Hz'),
            ]

            for name, value, uncertainty, unit in results_data:
                result = AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name=name,
                    value=value,
                    uncertainty=uncertainty,
                    unit=unit,
                    calculated_by_id=current_user.id
                )
                db.session.add(result)

            # Store validity
            test_record.notes = f"Valid: {results.is_valid}. {results.validity_notes}"

            # Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action='CREATE',
                table_name='test_records',
                record_id=test_record.id,
                new_values={'test_id': test_id, 'specimen_id': form.specimen_id.data},
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

            flash(f'Analysis complete! Test ID: {test_id}', 'success')
            if not results.is_valid:
                flash(f'Warning: {results.validity_notes}', 'warning')

            return redirect(url_for('sonic.view', test_id=test_record.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Analysis error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('sonic/new.html', form=form, certificate=certificate)


@sonic_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View test results."""
    test = TestRecord.query.get_or_404(test_id)
    results = {r.parameter_name: r for r in test.results.all()}
    geometry = test.geometry or {}

    # Calculate averages for display
    vl_avg = (geometry.get('vl1', 0) + geometry.get('vl2', 0) + geometry.get('vl3', 0)) / 3
    vs_avg = (geometry.get('vs1', 0) + geometry.get('vs2', 0) + geometry.get('vs3', 0)) / 3

    return render_template('sonic/view.html', test=test, results=results,
                          geometry=geometry, vl_avg=vl_avg, vs_avg=vs_avg)


@sonic_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate test report."""
    test = TestRecord.query.get_or_404(test_id)
    form = ReportForm()

    if request.method == 'GET' and test.certificate:
        form.certificate_number.data = test.certificate.certificate_number_with_rev

    if form.validate_on_submit():
        try:
            results = {r.parameter_name: r for r in test.results.all()}
            geometry = test.geometry or {}
            cert = test.certificate

            # Prepare test info
            test_info = {
                'test_project': cert.test_project if cert else '',
                'customer': cert.customer if cert else '',
                'customer_order': cert.customer_order if cert else '',
                'product_sn': cert.product_sn if cert else '',
                'specimen_id': test.specimen_id or '',
                'location_orientation': cert.location_orientation if cert else '',
                'material': test.material or '',
                'certificate_number': form.certificate_number.data or '',
                'test_date': test.test_date.strftime('%Y-%m-%d') if test.test_date else '',
                'temperature': str(test.temperature) if test.temperature else '23',
            }

            # Prepare specimen data
            specimen_data = {
                'specimen_type': 'Round' if geometry.get('type') == 'round' else 'Square',
                'diameter': geometry.get('diameter', '-'),
                'side_length': geometry.get('side_length', '-'),
                'length': geometry.get('length', ''),
                'mass': geometry.get('mass', ''),
            }

            # Prepare velocity data
            velocity_data = {
                'vl1': geometry.get('vl1', '-'),
                'vl2': geometry.get('vl2', '-'),
                'vl3': geometry.get('vl3', '-'),
                'vs1': geometry.get('vs1', '-'),
                'vs2': geometry.get('vs2', '-'),
                'vs3': geometry.get('vs3', '-'),
            }

            # Create mock results object for report generator
            class MockResults:
                pass

            mock_results = MockResults()
            mock_results.density = type('obj', (object,), {
                'value': results['Density'].value,
                'uncertainty': results['Density'].uncertainty
            })()
            mock_results.longitudinal_velocity = type('obj', (object,), {
                'value': results['Vl'].value,
                'uncertainty': results['Vl'].uncertainty
            })()
            mock_results.shear_velocity = type('obj', (object,), {
                'value': results['Vs'].value,
                'uncertainty': results['Vs'].uncertainty
            })()
            mock_results.poissons_ratio = type('obj', (object,), {
                'value': results['Poisson'].value,
                'uncertainty': results['Poisson'].uncertainty
            })()
            mock_results.shear_modulus = type('obj', (object,), {
                'value': results['G'].value,
                'uncertainty': results['G'].uncertainty
            })()
            mock_results.youngs_modulus = type('obj', (object,), {
                'value': results['E'].value,
                'uncertainty': results['E'].uncertainty
            })()
            mock_results.flexural_frequency = type('obj', (object,), {
                'value': results['ff'].value,
                'uncertainty': results['ff'].uncertainty
            })()
            mock_results.torsional_frequency = type('obj', (object,), {
                'value': results['ft'].value,
                'uncertainty': results['ft'].uncertainty
            })()
            mock_results.is_valid = 'Valid: True' in (test.notes or '')
            mock_results.validity_notes = test.notes or ''

            # Prepare report data
            report_data = SonicReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                velocity_data=velocity_data,
                results=mock_results
            )

            # Get template and logo paths
            template_path = Path(current_app.root_path).parent / 'templates' / 'sonic_e1875_report_template.docx'
            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'

            if not template_path.exists():
                flash(f'Template not found: {template_path}', 'danger')
                return redirect(url_for('sonic.view', test_id=test_id))

            # Generate report
            reports_folder = Path(current_app.root_path).parent / 'reports'
            reports_folder.mkdir(exist_ok=True)

            report_filename = f"Sonic_Report_{test.specimen_id or test.test_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            output_path = reports_folder / report_filename

            generator = SonicReportGenerator(template_path)
            generator.generate_report(
                output_path=output_path,
                data=report_data,
                logo_path=logo_path if logo_path.exists() else None
            )

            # Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action='GENERATE_REPORT',
                table_name='test_records',
                record_id=test_id,
                new_values={'report_filename': report_filename},
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

            flash(f'Report generated: {report_filename}', 'success')

            return send_file(
                output_path,
                as_attachment=True,
                download_name=report_filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            flash(f'Report generation error: {str(e)}', 'danger')
            return redirect(url_for('sonic.view', test_id=test_id))

    return render_template('sonic/report.html', test=test, form=form)


@sonic_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a test record (admin only)."""
    if current_user.role != 'admin':
        flash('Only administrators can delete records.', 'danger')
        return redirect(url_for('sonic.index'))

    test = TestRecord.query.get_or_404(test_id)

    audit = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        table_name='test_records',
        record_id=test_id,
        old_values={'test_id': test.test_id, 'specimen_id': test.specimen_id},
        ip_address=request.remote_addr,
        reason=request.form.get('reason', 'No reason provided')
    )
    db.session.add(audit)

    db.session.delete(test)
    db.session.commit()

    flash(f'Test {test.test_id} deleted.', 'success')
    return redirect(url_for('sonic.index'))
