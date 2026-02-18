"""Sonic Resonance (E1875) test routes."""
import os
import math
from pathlib import Path
from datetime import datetime

from flask import (render_template, redirect, url_for, flash, request,
                   current_app, send_file)
from flask_login import login_required, current_user

import plotly.graph_objects as go
import plotly.io as pio

from . import sonic_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import analysis utilities
from utils.analysis.sonic_calculations import SonicAnalyzer, SonicResults
from utils.models.sonic_specimen import SonicSpecimen, UltrasonicMeasurements
from utils.reporting.sonic_word_report import SonicReportGenerator


def create_velocity_chart(vl1, vl2, vl3, vs1, vs2, vs3):
    """Create Plotly bar chart showing velocity measurements."""
    fig = go.Figure()

    # Longitudinal velocities - darkred
    fig.add_trace(go.Bar(
        name='Longitudinal (Vl)',
        x=['Vl₁', 'Vl₂', 'Vl₃'],
        y=[vl1, vl2, vl3],
        marker_color='darkred',
        text=[f'{v:.0f}' for v in [vl1, vl2, vl3]],
        textposition='outside'
    ))

    # Shear velocities - black
    fig.add_trace(go.Bar(
        name='Shear (Vs)',
        x=['Vs₁', 'Vs₂', 'Vs₃'],
        y=[vs1, vs2, vs3],
        marker_color='black',
        text=[f'{v:.0f}' for v in [vs1, vs2, vs3]],
        textposition='outside'
    ))

    # Calculate averages for reference lines
    vl_avg = (vl1 + vl2 + vl3) / 3
    vs_avg = (vs1 + vs2 + vs3) / 3

    # Add average lines - thin grey with different dash styles
    fig.add_hline(y=vl_avg, line_dash="dash", line_color="grey", line_width=1,
                  annotation_text=f"Vl avg: {vl_avg:.0f} m/s",
                  annotation_position="top right")
    fig.add_hline(y=vs_avg, line_dash="dot", line_color="grey", line_width=1,
                  annotation_text=f"Vs avg: {vs_avg:.0f} m/s",
                  annotation_position="bottom right")

    fig.update_layout(
        title='Sound Velocity Measurements',
        yaxis_title='Velocity (m/s)',
        xaxis_title='Measurement',
        template='plotly_white',
        barmode='group',
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        height=400
    )

    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')


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

    # Populate certificate dropdown
    certificates = Certificate.query.order_by(
        Certificate.year.desc(),
        Certificate.cert_id.desc()
    ).limit(100).all()
    form.certificate_id.choices = [(0, '-- Select Certificate --')] + [
        (c.id, f"{c.certificate_number_with_rev} - {c.customer or 'No customer'}")
        for c in certificates
    ]

    # Get certificate from URL parameter or form selection
    cert_id = request.args.get('certificate', type=int)
    if request.method == 'GET' and cert_id:
        form.certificate_id.data = cert_id

    # Get selected certificate
    selected_cert_id = form.certificate_id.data if form.certificate_id.data and form.certificate_id.data > 0 else cert_id
    certificate = Certificate.query.get(selected_cert_id) if selected_cert_id else None

    # Pre-fill from certificate (certificate register is the master)
    if request.method == 'GET' and certificate:
        if certificate.material:
            form.material.data = certificate.material
        if certificate.test_article_sn:
            form.specimen_id.data = certificate.test_article_sn  # Specimen SN
        if certificate.product_sn:
            form.batch_number.data = certificate.product_sn
        if certificate.customer_specimen_info:
            form.customer_specimen_info.data = certificate.customer_specimen_info
        if certificate.requirement:
            form.requirement.data = certificate.requirement
        # Parse temperature - handle string format
        if certificate.temperature:
            try:
                temp_str = certificate.temperature.replace('°C', '').replace('C', '').strip()
                form.test_temperature.data = float(temp_str)
            except (ValueError, AttributeError):
                form.test_temperature.data = 23.0

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

            # Store uncertainty inputs (ISO 17025)
            geometry['uncertainty_inputs'] = {
                'velocity_pct': form.velocity_uncertainty.data or 1.0,
                'dimension_pct': form.dimension_uncertainty.data or 0.5,
                'mass_pct': form.mass_uncertainty.data or 0.1
            }

            # Calculate uncertainty budget (simplified RSS)
            vel_u = (form.velocity_uncertainty.data or 1.0) / 100
            dim_u = (form.dimension_uncertainty.data or 0.5) / 100
            mass_u = (form.mass_uncertainty.data or 0.1) / 100
            combined_u = math.sqrt(vel_u**2 + dim_u**2 + mass_u**2) * 100
            geometry['uncertainty_budget'] = {
                'combined': combined_u,
                'coverage_factor': 2,
                'expanded': combined_u * 2
            }

            # Create test record
            test_id = generate_test_id()

            # Get certificate from form selection
            selected_cert_id = form.certificate_id.data if form.certificate_id.data and form.certificate_id.data > 0 else None
            selected_cert = Certificate.query.get(selected_cert_id) if selected_cert_id else None
            cert_number = selected_cert.certificate_number_with_rev if selected_cert else None

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
                certificate_id=selected_cert_id,
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

    # Get velocity measurements
    vl1 = geometry.get('vl1', 0)
    vl2 = geometry.get('vl2', 0)
    vl3 = geometry.get('vl3', 0)
    vs1 = geometry.get('vs1', 0)
    vs2 = geometry.get('vs2', 0)
    vs3 = geometry.get('vs3', 0)

    # Calculate averages for display
    vl_avg = (vl1 + vl2 + vl3) / 3
    vs_avg = (vs1 + vs2 + vs3) / 3

    # Generate velocity chart
    velocity_chart = None
    if vl1 > 0 and vs1 > 0:
        try:
            velocity_chart = create_velocity_chart(vl1, vl2, vl3, vs1, vs2, vs3)
        except Exception as e:
            print(f"Error creating velocity chart: {e}")

    return render_template('sonic/view.html', test=test, results=results,
                          geometry=geometry, vl_avg=vl_avg, vs_avg=vs_avg,
                          velocity_chart=velocity_chart)


@sonic_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate test report."""
    # Import matplotlib for chart generation
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

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
            vl1 = geometry.get('vl1', 0)
            vl2 = geometry.get('vl2', 0)
            vl3 = geometry.get('vl3', 0)
            vs1 = geometry.get('vs1', 0)
            vs2 = geometry.get('vs2', 0)
            vs3 = geometry.get('vs3', 0)

            velocity_data = {
                'vl1': vl1 if vl1 else '-',
                'vl2': vl2 if vl2 else '-',
                'vl3': vl3 if vl3 else '-',
                'vs1': vs1 if vs1 else '-',
                'vs2': vs2 if vs2 else '-',
                'vs3': vs3 if vs3 else '-',
            }

            # Helper to get result value with default
            def get_result(key, default_val=0, default_unc=0):
                r = results.get(key)
                if r:
                    return r.value, r.uncertainty
                return default_val, default_unc

            # Create mock results object for report generator
            class MockValue:
                def __init__(self, value, uncertainty):
                    self.value = value
                    self.uncertainty = uncertainty

            class MockResults:
                pass

            mock_results = MockResults()
            v, u = get_result('Density')
            mock_results.density = MockValue(v, u)
            v, u = get_result('Vl')
            mock_results.longitudinal_velocity = MockValue(v, u)
            v, u = get_result('Vs')
            mock_results.shear_velocity = MockValue(v, u)
            v, u = get_result('Poisson')
            mock_results.poissons_ratio = MockValue(v, u)
            v, u = get_result('G')
            mock_results.shear_modulus = MockValue(v, u)
            v, u = get_result('E')
            mock_results.youngs_modulus = MockValue(v, u)
            v, u = get_result('ff')
            mock_results.flexural_frequency = MockValue(v, u)
            v, u = get_result('ft')
            mock_results.torsional_frequency = MockValue(v, u)
            notes = geometry.get('notes', '')
            mock_results.is_valid = 'Valid: True' in (notes or '')
            mock_results.validity_notes = notes or ''

            # Prepare report data
            report_data = SonicReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                velocity_data=velocity_data,
                results=mock_results
            )

            # Get logo path (use from-scratch report generation)
            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'

            # Generate velocity chart for report
            chart_path = None
            if vl1 > 0 and vs1 > 0:
                try:
                    fig, ax = plt.subplots(figsize=(7, 4))

                    x_vl = [0.8, 1.0, 1.2]
                    x_vs = [1.8, 2.0, 2.2]

                    # Plot bars - darkred for longitudinal, black for shear
                    bars_vl = ax.bar(x_vl, [vl1, vl2, vl3], width=0.15, label='Longitudinal (Vl)',
                                    color='darkred', edgecolor='black')
                    bars_vs = ax.bar(x_vs, [vs1, vs2, vs3], width=0.15, label='Shear (Vs)',
                                    color='black', edgecolor='black')

                    # Add value labels
                    for bar, val in zip(bars_vl, [vl1, vl2, vl3]):
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50,
                               f'{val:.0f}', ha='center', va='bottom', fontsize=8)
                    for bar, val in zip(bars_vs, [vs1, vs2, vs3]):
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50,
                               f'{val:.0f}', ha='center', va='bottom', fontsize=8, color='white')

                    # Add average lines - thin grey with different linestyles
                    vl_avg = (vl1 + vl2 + vl3) / 3
                    vs_avg = (vs1 + vs2 + vs3) / 3
                    ax.axhline(y=vl_avg, xmin=0.1, xmax=0.45, color='grey',
                              linestyle='--', linewidth=1)
                    ax.axhline(y=vs_avg, xmin=0.55, xmax=0.9, color='grey',
                              linestyle=':', linewidth=1)

                    ax.set_ylabel('Velocity (m/s)')
                    ax.set_title(f'Sound Velocity Measurements - {test.specimen_id}')
                    ax.set_xticks([1.0, 2.0])
                    ax.set_xticklabels(['Longitudinal', 'Shear'])
                    ax.legend(loc='upper right')
                    ax.grid(True, alpha=0.3, axis='y')

                    # Set y-axis to start near the minimum value
                    min_val = min(vl1, vl2, vl3, vs1, vs2, vs3) * 0.9
                    max_val = max(vl1, vl2, vl3) * 1.1
                    ax.set_ylim(min_val, max_val)

                    chart_path = Path(current_app.config['UPLOAD_FOLDER']) / f'sonic_chart_{test_id}.png'
                    fig.savefig(chart_path, dpi=150, bbox_inches='tight')
                    plt.close(fig)
                except Exception as chart_error:
                    print(f"Chart generation error: {chart_error}")
                    chart_path = None

            # Generate report
            reports_folder = Path(current_app.root_path).parent / 'reports'
            reports_folder.mkdir(exist_ok=True)

            report_filename = f"Sonic_Report_{test.specimen_id or test.test_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            output_path = reports_folder / report_filename

            generator = SonicReportGenerator(None)  # Use from-scratch generation
            generator.generate_report(
                output_path=output_path,
                data=report_data,
                chart_path=chart_path,
                logo_path=logo_path if logo_path.exists() else None
            )

            # Clean up chart temp file
            if chart_path and chart_path.exists():
                os.remove(chart_path)

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
