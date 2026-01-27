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
from utils.reporting.word_report import TensileReportGenerator

# For chart image generation
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend
import matplotlib.pyplot as plt


def generate_test_id():
    """Generate unique test ID."""
    today = datetime.now()
    # Count today's tests
    count = TestRecord.query.filter(
        TestRecord.test_method == 'TENSILE',
        db.func.date(TestRecord.created_at) == today.date()
    ).count()
    return f"TEN-{today.strftime('%Y%m%d')}-{count + 1:03d}"


def calculate_area(diameter):
    """Calculate cross-sectional area from diameter (round specimen)."""
    return np.pi * (diameter / 2) ** 2


def calculate_area_uncertainty(diameter, d_unc=0.01):
    """Calculate area uncertainty from diameter uncertainty."""
    # A = pi * (d/2)^2, u(A) = pi * d * u(d) / 2
    return np.pi * diameter * d_unc / 2


def create_stress_strain_plot(strain, stress, strain_disp=None, stress_disp=None,
                               rp02_strain=None, rp02_stress=None,
                               rm_strain=None, rm_stress=None,
                               reh_strain=None, reh_stress=None,
                               rel_strain=None, rel_stress=None,
                               E_modulus=None):
    """Create interactive Plotly stress-strain chart."""
    fig = go.Figure()

    # Main stress-strain curve (extensometer) - DARK RED
    fig.add_trace(go.Scatter(
        x=strain * 100,  # Convert to %
        y=stress,
        mode='lines',
        name='Extensometer',
        line=dict(color='#8B0000', width=2)  # Dark red
    ))

    # Displacement curve - BLACK
    if strain_disp is not None and stress_disp is not None:
        fig.add_trace(go.Scatter(
            x=strain_disp * 100,
            y=stress_disp,
            mode='lines',
            name='Displacement',
            line=dict(color='#000000', width=1.5)  # Black solid
        ))

    # Elastic slope line - GREY DOTTED
    if E_modulus:
        E_mpa = E_modulus * 1000
        max_elastic_strain = 0.01  # Up to 1%
        elastic_strain = np.linspace(0, max_elastic_strain, 50)
        elastic_stress = E_mpa * elastic_strain
        valid = elastic_stress <= np.max(stress) * 1.1
        fig.add_trace(go.Scatter(
            x=elastic_strain[valid] * 100,
            y=elastic_stress[valid],
            mode='lines',
            name=f'E = {E_modulus:.0f} GPa',
            line=dict(color='#808080', width=1, dash='dot')  # Grey dotted
        ))

    # Rp0.2 horizontal line - GREY DASHED
    if rp02_strain is not None and rp02_stress is not None:
        fig.add_trace(go.Scatter(
            x=[0, rp02_strain * 100 * 1.5],
            y=[rp02_stress, rp02_stress],
            mode='lines',
            name=f'Rp0.2 = {rp02_stress:.1f} MPa',
            line=dict(color='#808080', width=1, dash='dash')  # Grey dashed
        ))

        # Draw 0.2% offset line - GREY DOTTED
        if E_modulus:
            E_mpa = E_modulus * 1000
            offset_strain = np.linspace(0.002, rp02_strain * 1.3, 50)
            offset_stress = E_mpa * (offset_strain - 0.002)
            valid = (offset_stress > 0) & (offset_stress <= rp02_stress * 1.1)
            fig.add_trace(go.Scatter(
                x=offset_strain[valid] * 100,
                y=offset_stress[valid],
                mode='lines',
                name='0.2% offset',
                line=dict(color='#808080', width=1, dash='dot'),  # Grey dotted
                showlegend=False
            ))

    # Rm horizontal line - GREY LONGDASH
    if rm_strain is not None and rm_stress is not None:
        fig.add_trace(go.Scatter(
            x=[0, rm_strain * 100 * 1.2],
            y=[rm_stress, rm_stress],
            mode='lines',
            name=f'Rm = {rm_stress:.1f} MPa',
            line=dict(color='#808080', width=1.5, dash='longdash')  # Grey longdash
        ))

    # ReH horizontal line - GREY SOLID (thicker)
    if reh_strain is not None and reh_stress is not None:
        fig.add_trace(go.Scatter(
            x=[0, reh_strain * 100 * 1.5],
            y=[reh_stress, reh_stress],
            mode='lines',
            name=f'ReH = {reh_stress:.1f} MPa',
            line=dict(color='#606060', width=1.5, dash='solid')  # Dark grey solid
        ))

    # ReL horizontal line - GREY DASH with dots
    if rel_strain is not None and rel_stress is not None:
        fig.add_trace(go.Scatter(
            x=[0, rel_strain * 100 * 1.5],
            y=[rel_stress, rel_stress],
            mode='lines',
            name=f'ReL = {rel_stress:.1f} MPa',
            line=dict(color='#606060', width=1.5, dash='dashdot')  # Dark grey dashdot
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

    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')


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

            # Check if this is a re-analysis
            reanalyze_id = session.pop('tensile_reanalyze_id', None)

            # Get specimen type, yield method, and data source option
            specimen_type = form.specimen_type.data
            yield_method = form.yield_method.data
            use_displacement_only = form.use_displacement_only.data

            # Get common dimensions
            L0 = form.L0.data  # Extensometer length
            Lp = form.Lp.data  # Parallel length
            L1 = form.L1.data  # Final extensometer length
            Lf = form.Lf.data  # Final parallel length

            # Calculate area based on specimen type
            if specimen_type == 'round':
                D0 = form.D0.data
                D1 = form.D1.data
                area = np.pi * (D0 / 2) ** 2
                area_unc = np.pi * D0 * 0.01 / 2  # d_unc = 0.01mm
                # Final area for Z%
                if D1:
                    area_final = np.pi * (D1 / 2) ** 2
                else:
                    area_final = None
            else:  # rectangular
                a0 = form.a0.data  # Width
                b0 = form.b0.data  # Thickness
                au = form.au.data  # Final width
                bu = form.bu.data  # Final thickness
                area = a0 * b0
                area_unc = np.sqrt((b0 * 0.01)**2 + (a0 * 0.01)**2)  # 0.01mm uncertainty
                D0 = None
                D1 = None
                # Final area for Z%
                if au and bu:
                    area_final = au * bu
                else:
                    area_final = None

            # Create analyzer
            analyzer = TensileAnalyzer()

            # ===== STRESS-STRAIN CALCULATIONS =====

            # EXTENSOMETER: stress-strain from extensometer (using L0)
            stress, strain = analyzer.calculate_stress_strain(
                data.force, data.extension, area, L0
            )

            # DISPLACEMENT: stress-strain from crosshead (using Lp)
            stress_disp, strain_disp = analyzer.calculate_stress_strain(
                data.force, data.displacement, area, Lp
            )

            # ===== PRIMARY RESULTS =====

            # Rm - Ultimate tensile strength
            Rm = analyzer.calculate_ultimate_tensile_strength(data.force, area, area_unc)

            if use_displacement_only:
                # DISPLACEMENT-ONLY MODE
                # E calculated from displacement data using 10-30% Rm range
                E = analyzer.calculate_youngs_modulus_displacement(
                    stress_disp, strain_disp, area_unc, Lp, Rm.value,
                    min_stress_fraction=0.10, max_stress_fraction=0.30
                )
                E_disp = E  # Same value for display
            else:
                # NORMAL MODE: E from extensometer
                E = analyzer.calculate_youngs_modulus(stress, strain, area_unc, L0)

                # E_disp - Young's modulus from displacement (using 15-40% Rm range)
                try:
                    E_disp = analyzer.calculate_youngs_modulus_displacement(
                        stress_disp, strain_disp, area_unc, Lp, Rm.value
                    )
                except Exception:
                    E_disp = None

            # ===== YIELD STRENGTH CALCULATIONS =====
            Rp02 = Rp05 = Rp02_disp = Rp05_disp = None
            ReH = ReL = ReH_disp = ReL_disp = None

            if yield_method == 'offset':
                if use_displacement_only:
                    # DISPLACEMENT-ONLY MODE: Zero strain at 10% Rm to eliminate mechanical slack
                    # Rp0.2 from displacement with strain zeroed at 10% Rm
                    Rp02 = analyzer.calculate_yield_strength_rp02_displacement(
                        stress_disp, strain_disp, E.value, Rm.value, area, area_unc,
                        strain_zero_stress_fraction=0.10
                    )
                    # Rp0.5 from displacement with strain zeroed at 10% Rm
                    try:
                        Rp05 = analyzer.calculate_yield_strength_rp05_displacement(
                            stress_disp, strain_disp, E.value, Rm.value, area, area_unc,
                            strain_zero_stress_fraction=0.10
                        )
                    except Exception:
                        Rp05 = None
                    # No separate displacement values - they are the primary values
                    Rp02_disp = None
                    Rp05_disp = None
                else:
                    # NORMAL MODE: Extensometer for primary, displacement for secondary
                    # Rp0.2, Rp0.5 from extensometer
                    Rp02 = analyzer.calculate_yield_strength_rp02(
                        stress, strain, E.value, area, area_unc
                    )
                    try:
                        Rp05 = analyzer.calculate_yield_strength_rp05(
                            stress, strain, E.value, area, area_unc
                        )
                    except Exception:
                        Rp05 = None

                    # Rp0.2 from displacement (30% Rm reference - default)
                    try:
                        Rp02_disp = analyzer.calculate_yield_strength_rp02_displacement(
                            stress_disp, strain_disp, E_disp.value if E_disp else E.value,
                            Rm.value, area, area_unc
                        )
                    except Exception:
                        Rp02_disp = None

                    # Rp0.5 from displacement
                    try:
                        Rp05_disp = analyzer.calculate_yield_strength_rp05_displacement(
                            stress_disp, strain_disp, E_disp.value if E_disp else E.value,
                            Rm.value, area, area_unc
                        )
                    except Exception:
                        Rp05_disp = None

            else:
                # Yield point method: ReH, ReL
                # Note: These values are only valid for materials with a clear yield point
                # (Lüders band/yield plateau), typically mild steel.

                # Choose data source based on mode
                if use_displacement_only:
                    primary_stress, primary_strain = stress_disp, strain_disp
                else:
                    primary_stress, primary_strain = stress, strain

                try:
                    ReH = analyzer.calculate_upper_yield_strength_reh(primary_stress, primary_strain, area, area_unc)
                    # Validate: ReH should be at least 50% of Rm for typical steel
                    if ReH and ReH.value < Rm.value * 0.5:
                        print(f"ReH={ReH.value} MPa rejected (< 50% of Rm={Rm.value})")
                        ReH = None
                except Exception as e:
                    print(f"ReH calculation failed: {e}")
                    ReH = None

                try:
                    ReL = analyzer.calculate_lower_yield_strength_rel(primary_stress, primary_strain, area, area_unc)
                    # Validate ReL based on ReH if available, otherwise based on Rm
                    if ReH and ReL:
                        # ReL should be between 80% and 100% of ReH for valid yield plateau
                        if ReL.value < ReH.value * 0.80:
                            print(f"ReL={ReL.value} MPa rejected (< 80% of ReH={ReH.value})")
                            ReL = None
                        elif ReL.value > ReH.value:
                            print(f"ReL={ReL.value} MPa rejected (> ReH={ReH.value})")
                            ReL = None
                    elif ReL and ReL.value < Rm.value * 0.45:
                        print(f"ReL={ReL.value} MPa rejected (< 45% of Rm={Rm.value})")
                        ReL = None
                except Exception as e:
                    print(f"ReL calculation failed: {e}")
                    ReL = None

                # ReH/ReL from displacement (only in normal mode)
                if not use_displacement_only:
                    try:
                        ReH_disp = analyzer.calculate_upper_yield_strength_reh(stress_disp, strain_disp, area, area_unc)
                        if ReH_disp and ReH_disp.value < Rm.value * 0.5:
                            ReH_disp = None
                    except Exception:
                        ReH_disp = None

                    try:
                        ReL_disp = analyzer.calculate_lower_yield_strength_rel(stress_disp, strain_disp, area, area_unc)
                        if ReH_disp and ReL_disp:
                            if ReL_disp.value < ReH_disp.value * 0.80 or ReL_disp.value > ReH_disp.value:
                                ReL_disp = None
                        elif ReL_disp and ReL_disp.value < Rm.value * 0.45:
                            ReL_disp = None
                    except Exception:
                        ReL_disp = None

                # If no valid ReH/ReL found, this material likely doesn't have a yield plateau
                # User should use offset method (Rp0.2) instead
                if not ReH and not ReL:
                    flash('No clear yield point detected. Consider using Offset method (Rp0.2) for this material.', 'warning')

            # ===== ELONGATION AND REDUCTION OF AREA =====

            # A% - Elongation at fracture
            if L1 and L0:
                # Manual measurement: A% = (L1 - L0) / L0 * 100
                A_value = (L1 - L0) / L0 * 100
                # Uncertainty from measurement (assume 0.5mm for manual)
                A_unc = np.sqrt(2) * 0.5 / L0 * 100
                A_percent = MeasuredValue(round(A_value, 2), round(A_unc, 2), '%')
            else:
                # From extensometer data
                A_percent = analyzer.calculate_elongation_at_fracture(
                    data.extension, data.force, L0
                )

            # Ag - Uniform elongation (at max force)
            Ag = analyzer.calculate_uniform_elongation(
                data.extension, data.force, L0
            )

            # Z% - Reduction of area
            Z_percent = None
            if area_final is not None:
                Z_value = (area - area_final) / area * 100
                Z_unc = 2.0  # Approximate uncertainty
                Z_percent = MeasuredValue(round(Z_value, 1), round(Z_unc, 1), '%')

            # ===== TRUE STRESS =====

            # True stress at Rm = Rm * (1 + strain_at_Rm)
            rm_idx = np.argmax(data.force)
            eng_stress_rm = stress[rm_idx]
            eng_strain_rm = strain[rm_idx]
            true_stress_rm_value = eng_stress_rm * (1 + eng_strain_rm)
            true_stress_rm_unc = true_stress_rm_value * 0.01
            true_stress_rm = MeasuredValue(round(true_stress_rm_value, 1), round(true_stress_rm_unc * 2, 1), 'MPa')

            # True stress at break = F_max / A_final
            true_stress_break = None
            if area_final is not None:
                F_max = np.max(data.force) * 1000  # kN to N
                true_stress_break_value = F_max / area_final  # N/mm² = MPa
                u_rel = 0.02  # ~2% relative uncertainty
                true_stress_break_unc = true_stress_break_value * u_rel
                true_stress_break = MeasuredValue(round(true_stress_break_value, 1), round(true_stress_break_unc * 2, 1), 'MPa')

            # ===== LUDWIK PARAMETERS =====
            K = n = None
            yield_stress = Rp02.value if Rp02 else (ReH.value if ReH else None)
            if yield_stress:
                try:
                    K, n = analyzer.calculate_ludwik_parameters(stress, strain, E.value, yield_stress)
                except Exception:
                    pass

            # ===== STRAIN/STRESS RATES =====

            # Rates at Rp0.2
            try:
                stress_rate_rp02, strain_rate_rp02, disp_rate_rp02 = analyzer.calculate_rates_at_rp02(
                    data.time, stress, strain, data.displacement, E.value
                )
            except Exception:
                stress_rate_rp02 = strain_rate_rp02 = disp_rate_rp02 = None

            # Rates at Rm
            try:
                stress_rate_rm, strain_rate_rm, disp_rate_rm = analyzer.calculate_rates_at_rm(
                    data.time, stress, strain, data.displacement
                )
            except Exception:
                stress_rate_rm = strain_rate_rm = disp_rate_rm = None

            # ===== FIND PLOT COORDINATES =====

            # Find Rm position for plotting
            rm_idx = np.argmax(stress)
            rm_strain = strain[rm_idx]

            # Find Rp0.2 strain for plotting
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

            # ===== SAVE TO DATABASE =====

            # Build geometry dict based on specimen type
            if specimen_type == 'round':
                geometry = {
                    'type': 'round',
                    'D0': D0,
                    'D1': D1,
                    'L0': L0,
                    'Lp': Lp,
                    'L1': L1,
                    'Lf': Lf,
                    'area': area,
                    'area_final': area_final
                }
            else:
                geometry = {
                    'type': 'rectangular',
                    'a0': form.a0.data,
                    'b0': form.b0.data,
                    'au': form.au.data,
                    'bu': form.bu.data,
                    'L0': L0,
                    'Lp': Lp,
                    'L1': L1,
                    'Lf': Lf,
                    'area': area,
                    'area_final': area_final
                }

            # Store yield method and data source option
            geometry['yield_method'] = yield_method
            geometry['use_displacement_only'] = use_displacement_only

            # Get certificate if linked
            certificate_id = session.get('tensile_certificate_id')
            cert_number = None
            if certificate_id:
                cert = Certificate.query.get(certificate_id)
                if cert:
                    cert_number = cert.certificate_number_with_rev

            # Handle re-analysis vs new test
            if reanalyze_id:
                # Re-analysis: update existing record
                test_record = TestRecord.query.get(reanalyze_id)
                if not test_record:
                    flash('Original test record not found.', 'danger')
                    return redirect(url_for('tensile.index'))

                # Delete old results
                AnalysisResult.query.filter_by(test_record_id=test_record.id).delete()

                # Update record fields
                test_record.test_standard = form.test_standard.data
                test_record.specimen_id = form.specimen_id.data
                test_record.material = form.material.data
                test_record.batch_number = form.batch_number.data
                test_record.geometry = geometry
                test_record.temperature = form.test_temperature.data
                test_record.status = 'ANALYZED'

                # Audit log for re-analysis
                audit = AuditLog(
                    user_id=current_user.id,
                    action='REANALYZE',
                    table_name='test_records',
                    record_id=test_record.id,
                    new_values={'specimen_id': form.specimen_id.data, 'reanalyzed': True},
                    ip_address=request.remote_addr
                )
                db.session.add(audit)

                flash('Test re-analyzed successfully.', 'success')
            else:
                # New test: create new record
                test_id = generate_test_id()

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

            # Store ALL results
            results_data = [
                ('Rm', Rm.value, Rm.uncertainty, 'MPa'),
                ('E', E.value, E.uncertainty, 'GPa'),
                ('A%', A_percent.value, A_percent.uncertainty, '%'),
                ('Ag', Ag.value, Ag.uncertainty, '%'),
            ]

            # Yield strength results - based on method
            if yield_method == 'offset':
                if Rp02:
                    results_data.append(('Rp0.2', Rp02.value, Rp02.uncertainty, 'MPa'))
                if Rp05:
                    results_data.append(('Rp0.5', Rp05.value, Rp05.uncertainty, 'MPa'))
                if Rp02_disp:
                    results_data.append(('Rp0.2_disp', Rp02_disp.value, Rp02_disp.uncertainty, 'MPa'))
                if Rp05_disp:
                    results_data.append(('Rp0.5_disp', Rp05_disp.value, Rp05_disp.uncertainty, 'MPa'))
            else:
                # Yield point method
                if ReH:
                    results_data.append(('ReH', ReH.value, ReH.uncertainty, 'MPa'))
                if ReL:
                    results_data.append(('ReL', ReL.value, ReL.uncertainty, 'MPa'))
                if ReH_disp:
                    results_data.append(('ReH_disp', ReH_disp.value, ReH_disp.uncertainty, 'MPa'))
                if ReL_disp:
                    results_data.append(('ReL_disp', ReL_disp.value, ReL_disp.uncertainty, 'MPa'))

            # Z%
            if Z_percent:
                results_data.append(('Z%', Z_percent.value, Z_percent.uncertainty, '%'))

            # Displacement E
            if E_disp:
                results_data.append(('E_disp', E_disp.value, E_disp.uncertainty, 'GPa'))

            # True stress
            results_data.append(('True_stress_Rm', true_stress_rm.value, true_stress_rm.uncertainty, 'MPa'))
            if true_stress_break:
                results_data.append(('True_stress_break', true_stress_break.value, true_stress_break.uncertainty, 'MPa'))

            # Ludwik parameters
            if K and K.value > 0:
                results_data.append(('K', K.value, K.uncertainty, 'MPa'))
                results_data.append(('n', n.value, n.uncertainty, '-'))

            # Rates at Rp0.2
            if stress_rate_rp02:
                results_data.append(('Stress_rate_Rp02', stress_rate_rp02.value, stress_rate_rp02.uncertainty, 'MPa/s'))
                results_data.append(('Strain_rate_Rp02', strain_rate_rp02.value, strain_rate_rp02.uncertainty, '1/s'))
                results_data.append(('Disp_rate_Rp02', disp_rate_rp02.value, disp_rate_rp02.uncertainty, 'mm/s'))

            # Rates at Rm
            if stress_rate_rm:
                results_data.append(('Stress_rate_Rm', stress_rate_rm.value, stress_rate_rm.uncertainty, 'MPa/s'))
                results_data.append(('Strain_rate_Rm', strain_rate_rm.value, strain_rate_rm.uncertainty, '1/s'))
                results_data.append(('Disp_rate_Rm', disp_rate_rm.value, disp_rate_rm.uncertainty, 'mm/s'))

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

            # Audit log (only for new tests, re-analysis already logged above)
            if not reanalyze_id:
                audit = AuditLog(
                    user_id=current_user.id,
                    action='CREATE',
                    table_name='test_records',
                    record_id=test_record.id,
                    new_values={'test_id': test_record.test_id, 'specimen_id': form.specimen_id.data},
                    ip_address=request.remote_addr
                )
                db.session.add(audit)

            db.session.commit()

            # Clean up session - don't store plot_html (too large for cookies)
            del session['tensile_csv_path']
            del session['tensile_csv_info']
            session.pop('tensile_certificate_id', None)
            session.pop('tensile_results', None)

            if reanalyze_id:
                flash(f'Test re-analyzed successfully! Test ID: {test_record.test_id}', 'success')
            else:
                flash(f'Analysis complete! Test ID: {test_record.test_id}', 'success')
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

    # Always regenerate plot from data file
    plot_html = None
    if not plot_html and test.raw_data_filename:
        try:
            csv_path = os.path.join(current_app.config['UPLOAD_FOLDER'], test.raw_data_filename)
            if os.path.exists(csv_path):
                data = parse_mts_csv(Path(csv_path))
                geometry = test.geometry or {}
                area = geometry.get('area', 100)
                L0 = geometry.get('L0') or geometry.get('extensometer_gauge_length', 50)
                Lp = geometry.get('Lp') or geometry.get('parallel_length', 50)

                analyzer = TensileAnalyzer()

                # Calculate extensometer strain
                stress, strain = analyzer.calculate_stress_strain(
                    data.force, data.extension, area, L0
                )

                # Calculate displacement strain
                stress_disp, strain_disp = analyzer.calculate_stress_strain(
                    data.force, data.displacement, area, Lp
                )

                # Get result values for plot
                rp02_val = results.get('Rp0.2')
                rm_val = results.get('Rm')
                e_val = results.get('E')
                reh_val = results.get('ReH')
                rel_val = results.get('ReL')

                rm_idx = np.argmax(stress)
                rm_strain = strain[rm_idx]

                # Helper to find strain at a given stress level
                def find_strain_at_stress(target_stress):
                    if target_stress is None:
                        return None
                    idx = np.argmin(np.abs(stress - target_stress))
                    return strain[idx]

                # Find strain values for each result
                rp02_strain = find_strain_at_stress(rp02_val.value) if rp02_val else None
                reh_strain = find_strain_at_stress(reh_val.value) if reh_val else None
                rel_strain = find_strain_at_stress(rel_val.value) if rel_val else None

                plot_html = create_stress_strain_plot(
                    strain, stress,
                    strain_disp=strain_disp, stress_disp=stress_disp,
                    rp02_strain=rp02_strain,
                    rp02_stress=rp02_val.value if rp02_val else None,
                    rm_strain=rm_strain,
                    rm_stress=rm_val.value if rm_val else None,
                    reh_strain=reh_strain,
                    reh_stress=reh_val.value if reh_val else None,
                    rel_strain=rel_strain,
                    rel_stress=rel_val.value if rel_val else None,
                    E_modulus=e_val.value if e_val else None
                )
        except Exception as e:
            print(f"Error regenerating plot: {e}")

    return render_template('tensile/view.html', test=test, results=results, plot_html=plot_html)


@tensile_bp.route('/<int:test_id>/reanalyze', methods=['GET', 'POST'])
@login_required
def reanalyze(test_id):
    """Re-analyze test with modified specimen data."""
    test = TestRecord.query.get_or_404(test_id)
    form = SpecimenForm()
    geometry = test.geometry or {}

    # Load CSV info
    csv_path = os.path.join(current_app.config['UPLOAD_FOLDER'], test.raw_data_filename)
    if not os.path.exists(csv_path):
        flash('Original CSV file not found. Cannot re-analyze.', 'danger')
        return redirect(url_for('tensile.view', test_id=test_id))

    data = parse_mts_csv(Path(csv_path))
    csv_info = {
        'filename': test.raw_data_filename,
        'test_run_name': data.test_run_name,
        'test_date': data.test_date.strftime('%Y-%m-%d %H:%M') if hasattr(data.test_date, 'strftime') else str(data.test_date) if data.test_date else 'Unknown',
        'num_points': len(data.time),
        'max_force': float(np.max(data.force)),
        'max_extension': float(np.max(data.extension))
    }

    # Store CSV path and info in session for analysis
    session['tensile_csv_path'] = csv_path
    session['tensile_csv_info'] = csv_info
    session['tensile_reanalyze_id'] = test_id

    # Pre-fill form with existing data on GET
    if request.method == 'GET':
        form.specimen_id.data = test.specimen_id
        form.material.data = test.material
        form.batch_number.data = test.batch_number
        form.test_standard.data = test.test_standard
        form.test_temperature.data = test.temperature
        form.notes.data = getattr(test, 'notes', '')

        # Specimen type and yield method
        form.specimen_type.data = geometry.get('type', 'round')
        form.yield_method.data = geometry.get('yield_method', 'offset')
        form.use_displacement_only.data = geometry.get('use_displacement_only', False)

        # Dimensions
        form.L0.data = geometry.get('L0')
        form.Lp.data = geometry.get('Lp')
        form.L1.data = geometry.get('L1')
        form.Lf.data = geometry.get('Lf')

        if geometry.get('type') == 'round':
            form.D0.data = geometry.get('D0')
            form.D1.data = geometry.get('D1')
        else:
            form.a0.data = geometry.get('a0')
            form.b0.data = geometry.get('b0')
            form.au.data = geometry.get('au')
            form.bu.data = geometry.get('bu')

    return render_template('tensile/specimen.html', form=form, csv_info=csv_info,
                          certificate=test.certificate, reanalyze=True, test_id=test_id)


@tensile_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate test report."""
    test = TestRecord.query.get_or_404(test_id)
    form = ReportForm()

    # Pre-fill certificate number if linked
    if request.method == 'GET' and test.certificate:
        form.certificate_number.data = test.certificate.certificate_number_with_rev

    if form.validate_on_submit():
        try:
            # Get results as dictionary
            results = {r.parameter_name: r for r in test.results.all()}
            geometry = test.geometry or {}

            # Prepare test info
            test_info = {
                'test_project': test.certificate.test_project if test.certificate else '',
                'customer': test.certificate.customer if test.certificate else '',
                'customer_order': test.certificate.customer_order if test.certificate else '',
                'product_sn': test.certificate.product_sn if test.certificate else '',
                'specimen_id': test.specimen_id or '',
                'location_orientation': test.certificate.location_orientation if test.certificate else '',
                'material': test.material or '',
                'certificate_number': form.certificate_number.data or '',
                'test_date': test.test_date.strftime('%Y-%m-%d') if test.test_date else '',
                'test_engineer': current_user.username,
                'temperature': str(test.temperature) if test.temperature else '23',
                'strain_source': 'Displacement Only' if geometry.get('use_displacement_only') else 'Extensometer',
                'comments': ''
            }

            # Prepare dimensions
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

            # Convert AnalysisResult objects to MeasuredValue-like objects for report
            results_for_report = {}
            for name, result in results.items():
                # Create a simple object with value and uncertainty attributes
                class ResultValue:
                    def __init__(self, v, u):
                        self.value = v
                        self.uncertainty = u
                results_for_report[name] = ResultValue(result.value, result.uncertainty)

            # Map database result names to report template names
            result_mapping = {
                'Rp0.2': 'Rp02',
                'Rp0.5': 'Rp05',
                'A%': 'A_percent',
                'Z%': 'Z',
                'Stress_rate_Rp02': 'stress_rate_rp02',
                'Strain_rate_Rp02': 'strain_rate_rp02',
                'Stress_rate_Rm': 'stress_rate_rm',
                'Strain_rate_Rm': 'strain_rate_rm'
            }
            for db_name, report_name in result_mapping.items():
                if db_name in results_for_report:
                    results_for_report[report_name] = results_for_report[db_name]

            yield_type = geometry.get('yield_method', 'offset')

            # Prepare report data
            report_data = TensileReportGenerator.prepare_report_data(
                test_info=test_info,
                dimensions=dimensions,
                results=results_for_report,
                specimen_type=specimen_type,
                yield_type=yield_type
            )

            # Generate stress-strain chart image
            chart_path = None
            if test.raw_data_filename:
                csv_path = os.path.join(current_app.config['UPLOAD_FOLDER'], test.raw_data_filename)
                if os.path.exists(csv_path):
                    data = parse_mts_csv(Path(csv_path))
                    area = geometry.get('area', 100)
                    L0 = geometry.get('L0', 50)
                    Lp = geometry.get('Lp', 50)

                    analyzer = TensileAnalyzer()
                    stress, strain = analyzer.calculate_stress_strain(data.force, data.extension, area, L0)
                    stress_disp, strain_disp = analyzer.calculate_stress_strain(data.force, data.displacement, area, Lp)

                    # Create matplotlib figure for report
                    fig, ax = plt.subplots(figsize=(8, 5))
                    ax.plot(strain * 100, stress, 'darkred', linewidth=1.5, label='Extensometer')
                    ax.plot(strain_disp * 100, stress_disp, 'black', linewidth=1, label='Displacement')

                    # Add result markers
                    rm_val = results.get('Rm')
                    rp02_val = results.get('Rp0.2')
                    e_val = results.get('E')

                    if rm_val:
                        ax.axhline(y=rm_val.value, color='gray', linestyle='--', linewidth=1,
                                   label=f'Rm = {rm_val.value:.1f} MPa')
                    if rp02_val:
                        ax.axhline(y=rp02_val.value, color='gray', linestyle=':', linewidth=1,
                                   label=f'Rp0.2 = {rp02_val.value:.1f} MPa')

                    ax.set_xlabel('Strain (%)')
                    ax.set_ylabel('Stress (MPa)')
                    ax.set_title(f'Stress-Strain Curve - {test.specimen_id}')
                    ax.legend(loc='lower right', fontsize=8)
                    ax.grid(True, alpha=0.3)

                    # Save chart to temp file
                    chart_path = Path(current_app.config['UPLOAD_FOLDER']) / f'chart_{test_id}.png'
                    fig.savefig(chart_path, dpi=150, bbox_inches='tight')
                    plt.close(fig)

            # Get template and logo paths
            template_path = Path(current_app.root_path).parent / 'templates' / 'tensile_report_template.docx'
            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'

            if not template_path.exists():
                flash(f'Template not found: {template_path}', 'danger')
                return redirect(url_for('tensile.view', test_id=test_id))

            # Generate report
            reports_folder = Path(current_app.root_path).parent / 'reports'
            reports_folder.mkdir(exist_ok=True)

            report_filename = f"Tensile_Report_{test.specimen_id or test.test_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            output_path = reports_folder / report_filename

            generator = TensileReportGenerator(template_path)
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

            # Return file for download
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
