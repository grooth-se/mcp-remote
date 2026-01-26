"""Tensile test routes."""
import os
import json
import io
import base64
from pathlib import Path
from datetime import datetime

from flask import (render_template, redirect, url_for, flash, request,
                   current_app, session, send_file)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from . import tensile_bp
from .forms import CSVUploadForm, SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import analysis utilities
from utils.data_acquisition.mts_csv_parser import parse_mts_csv, MTSTestData
from utils.analysis.tensile_calculations import TensileAnalyzer, TensileAnalysisConfig
from utils.models.test_result import MeasuredValue


def generate_test_id():
    """Generate unique test ID."""
    today = datetime.now()
    # Count today's tests
    count = TestRecord.query.filter(
        TestRecord.test_method == 'TENSILE',
        db.func.date(TestRecord.created_at) == today.date()
    ).count()
    return f"TEN-{today.strftime('%Y%m%d')}-{count + 1:03d}"


def calculate_area(specimen_type, diameter=None, width=None, thickness=None):
    """Calculate cross-sectional area based on specimen type."""
    if specimen_type == 'round' and diameter:
        return np.pi * (diameter / 2) ** 2
    elif specimen_type == 'rectangular' and width and thickness:
        return width * thickness
    return 0


def calculate_area_uncertainty(specimen_type, diameter=None, width=None, thickness=None,
                                d_unc=0.01, w_unc=0.01, t_unc=0.01):
    """Calculate area uncertainty based on specimen type."""
    if specimen_type == 'round' and diameter:
        # A = pi * (d/2)^2, u(A) = pi * d * u(d) / 2
        return np.pi * diameter * d_unc / 2
    elif specimen_type == 'rectangular' and width and thickness:
        # A = w * t, u(A) = sqrt((t*u(w))^2 + (w*u(t))^2)
        return np.sqrt((thickness * w_unc)**2 + (width * t_unc)**2)
    return 0


def create_stress_strain_plot(strain, stress, strain_disp=None, stress_disp=None,
                               rp02_strain=None, rp02_stress=None,
                               rm_strain=None, rm_stress=None,
                               E_modulus=None):
    """Create interactive Plotly stress-strain chart."""
    fig = go.Figure()

    # Main stress-strain curve (extensometer)
    fig.add_trace(go.Scatter(
        x=strain * 100,  # Convert to %
        y=stress,
        mode='lines',
        name='Extensometer',
        line=dict(color='#0d6efd', width=2)
    ))

    # Displacement curve if available
    if strain_disp is not None and stress_disp is not None:
        fig.add_trace(go.Scatter(
            x=strain_disp * 100,
            y=stress_disp,
            mode='lines',
            name='Displacement',
            line=dict(color='#6c757d', width=1, dash='dash')
        ))

    # Mark Rp0.2 point
    if rp02_strain is not None and rp02_stress is not None:
        fig.add_trace(go.Scatter(
            x=[rp02_strain * 100],
            y=[rp02_stress],
            mode='markers',
            name=f'Rp0.2 = {rp02_stress:.1f} MPa',
            marker=dict(color='#198754', size=12, symbol='circle')
        ))

        # Draw 0.2% offset line
        if E_modulus:
            E_mpa = E_modulus * 1000
            offset_strain = np.linspace(0.002, rp02_strain * 1.2, 50)
            offset_stress = E_mpa * (offset_strain - 0.002)
            valid = offset_stress > 0
            fig.add_trace(go.Scatter(
                x=offset_strain[valid] * 100,
                y=offset_stress[valid],
                mode='lines',
                name='0.2% offset',
                line=dict(color='#198754', width=1, dash='dot')
            ))

    # Mark Rm point
    if rm_strain is not None and rm_stress is not None:
        fig.add_trace(go.Scatter(
            x=[rm_strain * 100],
            y=[rm_stress],
            mode='markers',
            name=f'Rm = {rm_stress:.1f} MPa',
            marker=dict(color='#dc3545', size=12, symbol='diamond')
        ))

    fig.update_layout(
        title='Stress-Strain Curve',
        xaxis_title='Strain (%)',
        yaxis_title='Stress (MPa)',
        template='plotly_white',
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        hovermode='closest',
        height=500
    )

    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


@tensile_bp.route('/')
@login_required
def index():
    """List all tensile tests."""
    tests = TestRecord.query.filter_by(test_method='TENSILE')\
        .order_by(TestRecord.created_at.desc()).all()
    return render_template('tensile/index.html', tests=tests)


@tensile_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Start new tensile test - upload CSV."""
    form = CSVUploadForm()

    # Populate certificate dropdown
    certificates = Certificate.query.order_by(
        Certificate.year.desc(),
        Certificate.cert_id.desc()
    ).limit(100).all()
    form.certificate_id.choices = [(0, '-- No Certificate --')] + [
        (c.id, f"{c.certificate_number_with_rev} - {c.customer or 'No customer'}")
        for c in certificates
    ]

    # Pre-select certificate from URL parameter
    cert_id_param = request.args.get('certificate', type=int)
    if request.method == 'GET' and cert_id_param:
        form.certificate_id.data = cert_id_param

    if form.validate_on_submit():
        file = form.csv_file.data
        filename = secure_filename(file.filename)

        # Save file
        upload_folder = current_app.config['UPLOAD_FOLDER']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(upload_folder, saved_filename)
        file.save(filepath)

        # Parse CSV
        try:
            data = parse_mts_csv(Path(filepath))

            # Store parsed data info in session
            session['tensile_csv_path'] = filepath
            session['tensile_csv_info'] = {
                'filename': filename,
                'test_name': data.test_name,
                'test_run_name': data.test_run_name,
                'test_date': data.test_date,
                'num_points': len(data.time),
                'max_force': float(np.max(data.force)),
                'max_extension': float(np.max(data.extension))
            }

            # Store certificate selection in session
            if form.certificate_id.data and form.certificate_id.data > 0:
                session['tensile_certificate_id'] = form.certificate_id.data
            else:
                session.pop('tensile_certificate_id', None)

            flash(f'CSV loaded: {data.test_run_name} ({len(data.time)} data points)', 'success')
            return redirect(url_for('tensile.specimen'))

        except Exception as e:
            flash(f'Error parsing CSV: {str(e)}', 'danger')
            os.remove(filepath)  # Clean up

    return render_template('tensile/new.html', form=form)


@tensile_bp.route('/specimen', methods=['GET', 'POST'])
@login_required
def specimen():
    """Enter specimen geometry and run analysis."""
    # Check if CSV was uploaded
    if 'tensile_csv_path' not in session:
        flash('Please upload a CSV file first.', 'warning')
        return redirect(url_for('tensile.new'))

    csv_info = session.get('tensile_csv_info', {})
    certificate_id = session.get('tensile_certificate_id')
    certificate = Certificate.query.get(certificate_id) if certificate_id else None

    form = SpecimenForm()

    # Pre-fill from CSV and certificate
    if request.method == 'GET':
        if csv_info.get('test_run_name'):
            form.specimen_id.data = csv_info['test_run_name']
        # Pre-fill from certificate if linked
        if certificate:
            if certificate.material:
                form.material.data = certificate.material
            if certificate.specimen_id:
                form.specimen_id.data = certificate.specimen_id
            if certificate.test_standard:
                # Map certificate standard to form choices
                std_map = {
                    'ASTM E8/E8M': 'ASTM E8/E8M-22',
                    'ISO 6892-1': 'ISO 6892-1:2019'
                }
                form.test_standard.data = std_map.get(certificate.test_standard, form.test_standard.data)

    if form.validate_on_submit():
        try:
            # Load CSV data
            csv_path = session['tensile_csv_path']
            data = parse_mts_csv(Path(csv_path))

            # Calculate initial area
            area = calculate_area(
                form.specimen_type.data,
                diameter=form.diameter.data,
                width=form.width.data,
                thickness=form.thickness.data
            )
            area_unc = calculate_area_uncertainty(
                form.specimen_type.data,
                diameter=form.diameter.data,
                width=form.width.data,
                thickness=form.thickness.data
            )

            # Create analyzer and run calculations
            analyzer = TensileAnalyzer()

            # Get gauge lengths
            gauge_length = form.gauge_length.data  # L0 for A% calculation
            extensometer_gl = form.extensometer_gauge_length.data or gauge_length  # Le for strain
            parallel_length = form.parallel_length.data  # Lc

            # Calculate stress-strain from EXTENSOMETER (primary)
            stress, strain = analyzer.calculate_stress_strain(
                data.force, data.extension, area, extensometer_gl
            )

            # Calculate stress-strain from DISPLACEMENT/crosshead (secondary)
            # Use parallel length if provided, otherwise gauge length
            disp_ref_length = parallel_length or gauge_length
            stress_disp, strain_disp = analyzer.calculate_stress_strain(
                data.force, data.displacement, area, disp_ref_length
            )

            # Calculate Rm first (needed for other calculations)
            Rm = analyzer.calculate_ultimate_tensile_strength(data.force, area, area_unc)

            # Calculate E (Young's modulus) from extensometer data
            E = analyzer.calculate_youngs_modulus(stress, strain, area_unc, extensometer_gl)

            # Calculate Rp0.2 from extensometer data
            Rp02 = analyzer.calculate_yield_strength_rp02(
                stress, strain, E.value, area, area_unc
            )

            # Calculate elongation A%
            # Use manual measurement (Lu) if provided, otherwise from extensometer
            if form.final_gauge_length.data and form.gauge_length.data:
                # Manual measurement: A% = (Lu - L0) / L0 * 100
                L0 = form.gauge_length.data
                Lu = form.final_gauge_length.data
                A_value = (Lu - L0) / L0 * 100
                # Uncertainty from measurement (assume 0.5mm for manual)
                A_unc = np.sqrt(2) * 0.5 / L0 * 100
                A_percent = MeasuredValue(A_value, A_unc, '%')
            else:
                # From extensometer data
                A_percent = analyzer.calculate_elongation_at_fracture(
                    data.extension, data.force, gauge_length
                )

            # Calculate uniform elongation Ag from extensometer
            Ag = analyzer.calculate_uniform_elongation(
                data.extension, data.force, extensometer_gl
            )

            # Calculate reduction of area Z%
            Z_percent = None
            if form.specimen_type.data == 'round':
                if form.final_diameter.data and form.diameter.data:
                    Z_percent = analyzer.calculate_reduction_of_area(
                        form.diameter.data, form.final_diameter.data
                    )
            elif form.specimen_type.data == 'rectangular':
                if (form.final_width.data and form.final_thickness.data and
                    form.width.data and form.thickness.data):
                    # Z% = (A0 - Au) / A0 * 100
                    A0 = form.width.data * form.thickness.data
                    Au = form.final_width.data * form.final_thickness.data
                    Z_value = (A0 - Au) / A0 * 100
                    # Uncertainty propagation
                    u_A0 = np.sqrt((form.thickness.data * 0.01)**2 + (form.width.data * 0.01)**2)
                    u_Au = np.sqrt((form.final_thickness.data * 0.01)**2 + (form.final_width.data * 0.01)**2)
                    Z_unc = np.sqrt((u_A0/A0)**2 + (u_Au/Au)**2) * Z_value
                    Z_percent = MeasuredValue(Z_value, Z_unc, '%')

            # Find Rp0.2 and Rm positions for plotting
            rm_idx = np.argmax(stress)
            rm_strain = strain[rm_idx]

            # Find Rp0.2 strain
            offset = 0.002
            E_mpa = E.value * 1000
            offset_line = E_mpa * (strain - offset)
            curve_minus_offset = stress - offset_line
            valid_idx = strain > offset * 1.5
            if np.any(valid_idx):
                curve_segment = curve_minus_offset[valid_idx]
                strain_segment = strain[valid_idx]
                sign_changes = np.where(np.diff(np.sign(curve_segment)))[0]
                if len(sign_changes) > 0:
                    idx = sign_changes[0]
                    rp02_strain = strain_segment[idx]
                else:
                    rp02_strain = strain_segment[np.argmin(np.abs(curve_segment))]
            else:
                rp02_strain = offset * 2

            # Create plot with BOTH extensometer and displacement curves
            plot_html = create_stress_strain_plot(
                strain, stress,
                strain_disp=strain_disp, stress_disp=stress_disp,
                rp02_strain=rp02_strain, rp02_stress=Rp02.value,
                rm_strain=rm_strain, rm_stress=Rm.value,
                E_modulus=E.value
            )

            # Create test record
            test_id = generate_test_id()
            geometry = {
                'type': form.specimen_type.data,
                'gauge_length': gauge_length,
                'extensometer_gauge_length': extensometer_gl,
                'parallel_length': parallel_length,
                'area': area
            }
            if form.specimen_type.data == 'round':
                geometry['diameter'] = form.diameter.data
                if form.final_diameter.data:
                    geometry['final_diameter'] = form.final_diameter.data
            else:
                geometry['width'] = form.width.data
                geometry['thickness'] = form.thickness.data
                if form.final_width.data:
                    geometry['final_width'] = form.final_width.data
                if form.final_thickness.data:
                    geometry['final_thickness'] = form.final_thickness.data
            if form.final_gauge_length.data:
                geometry['final_gauge_length'] = form.final_gauge_length.data

            # Get certificate if linked
            certificate_id = session.get('tensile_certificate_id')
            cert_number = None
            if certificate_id:
                cert = Certificate.query.get(certificate_id)
                if cert:
                    cert_number = cert.certificate_number_with_rev

            test_record = TestRecord(
                test_id=test_id,
                test_method='TENSILE',
                test_standard=form.test_standard.data,
                specimen_id=form.specimen_id.data,
                material=form.material.data,
                batch_number=form.batch_number.data,
                geometry=geometry,
                test_date=datetime.now(),
                temperature=form.test_temperature.data,
                raw_data_filename=os.path.basename(csv_path),
                status='ANALYZED',
                certificate_id=certificate_id if certificate_id else None,
                certificate_number=cert_number,
                operator_id=current_user.id
            )
            db.session.add(test_record)
            db.session.flush()  # Get ID

            # Store results
            results_data = [
                ('Rp0.2', Rp02.value, Rp02.uncertainty, 'MPa'),
                ('Rm', Rm.value, Rm.uncertainty, 'MPa'),
                ('E', E.value, E.uncertainty, 'GPa'),
                ('A%', A_percent.value, A_percent.uncertainty, '%'),
                ('Ag', Ag.value, Ag.uncertainty, '%'),
            ]
            if Z_percent:
                results_data.append(('Z%', Z_percent.value, Z_percent.uncertainty, '%'))

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

            # Store results in session for view page
            session['tensile_results'] = {
                'test_id': test_id,
                'record_id': test_record.id,
                'specimen_id': form.specimen_id.data,
                'Rp02': {'value': Rp02.value, 'uncertainty': Rp02.uncertainty},
                'Rm': {'value': Rm.value, 'uncertainty': Rm.uncertainty},
                'E': {'value': E.value, 'uncertainty': E.uncertainty},
                'A_percent': {'value': A_percent.value, 'uncertainty': A_percent.uncertainty},
                'Ag': {'value': Ag.value, 'uncertainty': Ag.uncertainty},
                'Z_percent': {'value': Z_percent.value, 'uncertainty': Z_percent.uncertainty} if Z_percent else None,
                'plot_html': plot_html
            }

            # Clean up session
            del session['tensile_csv_path']
            del session['tensile_csv_info']
            session.pop('tensile_certificate_id', None)

            flash(f'Analysis complete! Test ID: {test_id}', 'success')
            return redirect(url_for('tensile.view', test_id=test_record.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Analysis error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('tensile/specimen.html', form=form, csv_info=csv_info, certificate=certificate)


@tensile_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View test results."""
    test = TestRecord.query.get_or_404(test_id)
    results = {r.parameter_name: r for r in test.results.all()}

    # Check if plot is in session (fresh analysis)
    plot_html = None
    if 'tensile_results' in session and session['tensile_results'].get('record_id') == test_id:
        plot_html = session['tensile_results'].get('plot_html')

    # If no plot in session, regenerate from data
    if not plot_html and test.raw_data_filename:
        try:
            csv_path = os.path.join(current_app.config['UPLOAD_FOLDER'], test.raw_data_filename)
            if os.path.exists(csv_path):
                data = parse_mts_csv(Path(csv_path))
                geometry = test.geometry or {}
                area = geometry.get('area', 100)
                extensometer_gl = geometry.get('extensometer_gauge_length') or geometry.get('gauge_length', 50)
                parallel_length = geometry.get('parallel_length')
                disp_ref_length = parallel_length or geometry.get('gauge_length', 50)

                analyzer = TensileAnalyzer()

                # Calculate extensometer strain
                stress, strain = analyzer.calculate_stress_strain(
                    data.force, data.extension, area, extensometer_gl
                )

                # Calculate displacement strain
                stress_disp, strain_disp = analyzer.calculate_stress_strain(
                    data.force, data.displacement, area, disp_ref_length
                )

                # Get result values for plot
                rp02_val = results.get('Rp0.2')
                rm_val = results.get('Rm')
                e_val = results.get('E')

                rm_idx = np.argmax(stress)
                rm_strain = strain[rm_idx]

                # Find Rp0.2 strain
                if e_val:
                    offset = 0.002
                    E_mpa = e_val.value * 1000
                    offset_line = E_mpa * (strain - offset)
                    curve_minus_offset = stress - offset_line
                    valid_idx = strain > offset * 1.5
                    if np.any(valid_idx):
                        curve_segment = curve_minus_offset[valid_idx]
                        strain_segment = strain[valid_idx]
                        sign_changes = np.where(np.diff(np.sign(curve_segment)))[0]
                        if len(sign_changes) > 0:
                            rp02_strain = strain_segment[sign_changes[0]]
                        else:
                            rp02_strain = strain_segment[np.argmin(np.abs(curve_segment))]
                    else:
                        rp02_strain = 0.004
                else:
                    rp02_strain = 0.004

                plot_html = create_stress_strain_plot(
                    strain, stress,
                    strain_disp=strain_disp, stress_disp=stress_disp,
                    rp02_strain=rp02_strain,
                    rp02_stress=rp02_val.value if rp02_val else None,
                    rm_strain=rm_strain,
                    rm_stress=rm_val.value if rm_val else None,
                    E_modulus=e_val.value if e_val else None
                )
        except Exception as e:
            print(f"Error regenerating plot: {e}")

    return render_template('tensile/view.html', test=test, results=results, plot_html=plot_html)


@tensile_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate test report."""
    test = TestRecord.query.get_or_404(test_id)
    form = ReportForm()

    if form.validate_on_submit():
        # TODO: Implement report generation using utils/reporting/tensile_word_report.py
        flash('Report generation coming soon!', 'info')
        return redirect(url_for('tensile.view', test_id=test_id))

    return render_template('tensile/report.html', test=test, form=form)


@tensile_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a test record (admin only)."""
    if current_user.role != 'admin':
        flash('Only administrators can delete records.', 'danger')
        return redirect(url_for('tensile.index'))

    test = TestRecord.query.get_or_404(test_id)

    # Audit log
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
    return redirect(url_for('tensile.index'))
