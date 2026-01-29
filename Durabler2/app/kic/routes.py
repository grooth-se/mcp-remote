"""Routes for KIC (Fracture Toughness) test module - ASTM E399."""
import os
import json
from datetime import datetime
from pathlib import Path

from flask import (
    render_template, redirect, url_for, flash, request,
    current_app, send_file, session
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from . import kic_bp
from .forms import UploadForm, SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import calculation utilities
from utils.data_acquisition.kic_csv_parser import parse_kic_csv, KICTestData
from utils.data_acquisition.kic_excel_parser import parse_kic_excel
from utils.data_acquisition.precrack_csv_parser import parse_precrack_csv, validate_precrack_compliance
from utils.analysis.kic_calculations import KICAnalyzer
from utils.models.kic_specimen import KICSpecimen, KICMaterial
from utils.reporting.kic_word_report import KICReportGenerator


def create_force_displacement_plot(force, displacement, P_Q=None, P_max=None, secant_line=None):
    """Create interactive Force vs Displacement plot using Plotly.

    Parameters
    ----------
    force : array-like
        Force data in kN
    displacement : array-like
        Displacement data in mm
    P_Q : float, optional
        PQ force from 5% secant offset (kN)
    P_max : float, optional
        Maximum force (kN)
    secant_line : dict, optional
        Secant line data with 'x' and 'y' arrays

    Returns
    -------
    str
        HTML string with Plotly figure
    """
    import plotly.graph_objects as go

    fig = go.Figure()

    # Main force-displacement curve - darkred
    fig.add_trace(go.Scatter(
        x=list(displacement),
        y=list(force),
        mode='lines',
        name='Force vs Displacement',
        line=dict(color='darkred', width=2)
    ))

    # Add 5% secant offset line - black
    if secant_line:
        fig.add_trace(go.Scatter(
            x=secant_line['x'],
            y=secant_line['y'],
            mode='lines',
            name='5% Secant Offset',
            line=dict(color='black', width=1.5, dash='dash')
        ))

    # Mark PQ point - grey diamond
    if P_Q is not None:
        # Find displacement at PQ
        import numpy as np
        force_arr = np.array(force)
        disp_arr = np.array(displacement)
        idx = np.argmin(np.abs(force_arr - P_Q))
        disp_at_PQ = disp_arr[idx]

        fig.add_trace(go.Scatter(
            x=[disp_at_PQ],
            y=[P_Q],
            mode='markers',
            name=f'PQ = {P_Q:.2f} kN',
            marker=dict(color='grey', size=12, symbol='diamond-open', line=dict(width=2, color='grey'))
        ))

    # Mark Pmax point - grey square
    if P_max is not None:
        import numpy as np
        force_arr = np.array(force)
        disp_arr = np.array(displacement)
        idx = np.argmax(force_arr)
        disp_at_max = disp_arr[idx]

        fig.add_trace(go.Scatter(
            x=[disp_at_max],
            y=[P_max],
            mode='markers',
            name=f'Pmax = {P_max:.2f} kN',
            marker=dict(color='grey', size=12, symbol='square-open', line=dict(width=2, color='grey'))
        ))

    # Limit Y-axis to 1.1 times max force
    import numpy as np
    max_force = float(np.max(force)) if len(force) > 0 else 1
    y_max = max_force * 1.1
    y_tick = y_max / 12  # 12 steps on Y-axis

    fig.update_layout(
        title='Force vs Displacement (ASTM E399)',
        xaxis_title='Displacement (mm)',
        yaxis_title='Force (kN)',
        xaxis=dict(dtick=1),  # 1 mm steps on X-axis
        yaxis=dict(range=[0, y_max], dtick=y_tick),  # 12 steps on Y-axis
        template='plotly_white',
        showlegend=True,
        legend=dict(yanchor='top', y=0.99, xanchor='right', x=0.99),
        height=500
    )

    return fig.to_html(full_html=False, include_plotlyjs='cdn')


@kic_bp.route('/')
@login_required
def index():
    """List all KIC tests."""
    tests = TestRecord.query.filter_by(test_method='KIC').order_by(
        TestRecord.created_at.desc()
    ).all()
    return render_template('kic/index.html', tests=tests)


def generate_test_id():
    """Generate unique KIC test ID."""
    today = datetime.now()
    prefix = f"KIC-{today.strftime('%y%m%d')}"
    count = TestRecord.query.filter(
        TestRecord.test_id.like(f'{prefix}%')
    ).count()
    return f"{prefix}-{count + 1:03d}"


@kic_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Step 1: Upload Excel file and verify imported data."""
    form = UploadForm()

    # Populate certificate dropdown
    certificates = Certificate.query.order_by(
        Certificate.year.desc(),
        Certificate.cert_id.desc()
    ).limit(100).all()
    form.certificate_id.choices = [(0, '-- Select Certificate --')] + [
        (c.id, f"{c.certificate_number_with_rev} - {c.customer or 'No customer'}")
        for c in certificates
    ]

    # Get certificate from URL parameter
    cert_id = request.args.get('certificate', type=int)
    if request.method == 'GET' and cert_id:
        form.certificate_id.data = cert_id

    if form.validate_on_submit():
        try:
            # Save and parse Excel file
            excel_file = form.excel_file.data
            filename = secure_filename(excel_file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{filename}"
            filepath = Path(current_app.config['UPLOAD_FOLDER']) / saved_filename
            excel_file.save(filepath)

            excel_data = parse_kic_excel(filepath)

            # Calculate a_0 from 5-point measurements if available
            a_0_calculated = excel_data.a_0
            crack_measurements = excel_data.precrack_measurements or []
            if len(crack_measurements) == 5:
                a = crack_measurements
                a_0_calculated = (0.5 * a[0] + a[1] + a[2] + a[3] + 0.5 * a[4]) / 4
                current_app.logger.info(f'KIC: Calculated crack length from 5-point measurements: a_0={a_0_calculated:.3f} mm')

            # Store parsed data in session
            session['kic_excel_path'] = str(filepath)
            session['kic_excel_data'] = {
                'filename': filename,
                'specimen_id': excel_data.specimen_id,
                'specimen_type': excel_data.specimen_type,
                'W': excel_data.W,
                'B': excel_data.B,
                'B_n': excel_data.B_n,
                'a_0': a_0_calculated,
                'a_0_notch': excel_data.a_0,
                'S': excel_data.S,
                'yield_strength': excel_data.yield_strength,
                'ultimate_strength': excel_data.ultimate_strength,
                'youngs_modulus': excel_data.youngs_modulus,
                'poissons_ratio': excel_data.poissons_ratio,
                'test_temperature': excel_data.test_temperature,
                'material': excel_data.material,
                'crack_measurements': crack_measurements,
                'precrack_final_size': excel_data.precrack_final_size,
                'kic_results': excel_data.kic_results,
            }

            # Store certificate selection
            if form.certificate_id.data and form.certificate_id.data > 0:
                session['kic_certificate_id'] = form.certificate_id.data
            else:
                session.pop('kic_certificate_id', None)

            # Handle optional CSV file
            if form.csv_file.data:
                csv_file = form.csv_file.data
                csv_filename = secure_filename(csv_file.filename)
                csv_saved = f"{timestamp}_{csv_filename}"
                csv_filepath = Path(current_app.config['UPLOAD_FOLDER']) / csv_saved
                csv_file.save(csv_filepath)
                session['kic_csv_path'] = str(csv_filepath)
            else:
                session.pop('kic_csv_path', None)

            flash(f'Excel data imported: {excel_data.specimen_id}, W={excel_data.W}mm, B={excel_data.B}mm, a₀={a_0_calculated:.2f}mm', 'success')
            return redirect(url_for('kic.specimen'))

        except Exception as e:
            flash(f'Error parsing Excel file: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('kic/upload.html', form=form)


@kic_bp.route('/specimen', methods=['GET', 'POST'])
@login_required
def specimen():
    """Step 2: Review imported data and run analysis."""
    # Check if Excel was uploaded
    if 'kic_excel_data' not in session:
        flash('Please upload an Excel file first.', 'warning')
        return redirect(url_for('kic.new'))

    excel_data = session.get('kic_excel_data', {})
    certificate_id = session.get('kic_certificate_id')
    certificate = Certificate.query.get(certificate_id) if certificate_id else None
    reanalyze_id = session.get('kic_reanalyze_id')

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

    # Pre-fill form from Excel data and certificate
    if request.method == 'GET':
        # Generate test ID
        form.test_id.data = generate_test_id()

        # Pre-fill from Excel data
        if excel_data.get('specimen_id'):
            form.specimen_id.data = excel_data['specimen_id']
        if excel_data.get('specimen_type'):
            form.specimen_type.data = excel_data['specimen_type']
        if excel_data.get('W'):
            form.W.data = excel_data['W']
        if excel_data.get('B'):
            form.B.data = excel_data['B']
        if excel_data.get('B_n'):
            form.B_n.data = excel_data['B_n']
        if excel_data.get('a_0'):
            form.a_0.data = excel_data['a_0']
        if excel_data.get('S'):
            form.S.data = excel_data['S']
        if excel_data.get('yield_strength'):
            form.yield_strength.data = excel_data['yield_strength']
        if excel_data.get('ultimate_strength'):
            form.ultimate_strength.data = excel_data['ultimate_strength']
        if excel_data.get('youngs_modulus'):
            form.youngs_modulus.data = excel_data['youngs_modulus']
        if excel_data.get('poissons_ratio'):
            form.poissons_ratio.data = excel_data['poissons_ratio']
        if excel_data.get('test_temperature'):
            form.temperature.data = excel_data['test_temperature']
        if excel_data.get('material'):
            form.material.data = excel_data['material']

        # Pre-fill 5-point crack measurements
        crack_measurements = excel_data.get('crack_measurements', [])
        if len(crack_measurements) == 5:
            for i, val in enumerate(crack_measurements):
                getattr(form, f'crack_{i+1}').data = val

        # Certificate data overrides Excel data
        if certificate:
            if certificate.material:
                form.material.data = certificate.material
            if certificate.test_article_sn:
                form.specimen_id.data = certificate.test_article_sn
            if certificate.customer_specimen_info:
                form.customer_specimen_info.data = certificate.customer_specimen_info
            if certificate.requirement:
                form.requirement.data = certificate.requirement
            if certificate.location_orientation:
                form.location_orientation.data = certificate.location_orientation
            if certificate.temperature:
                try:
                    temp_str = certificate.temperature.replace('°C', '').replace('C', '').strip()
                    form.temperature.data = float(temp_str)
                except (ValueError, AttributeError):
                    pass
            form.certificate_id.data = certificate_id

    if form.validate_on_submit():
        try:
            # Get CSV data for analysis
            csv_path = session.get('kic_csv_path')
            force = None
            displacement = None

            if csv_path and Path(csv_path).exists():
                test_data = parse_kic_csv(csv_path)
                force = test_data.force
                displacement = test_data.displacement
            elif form.csv_file.data:
                # User uploaded CSV in this step
                csv_file = form.csv_file.data
                filename = secure_filename(csv_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                csv_filepath = Path(current_app.config['UPLOAD_FOLDER']) / f"{timestamp}_{filename}"
                csv_file.save(csv_filepath)
                test_data = parse_kic_csv(csv_filepath)
                force = test_data.force
                displacement = test_data.displacement

            if force is None or displacement is None:
                flash('Please upload CSV test data with Force and Displacement columns.', 'danger')
                return render_template('kic/new.html', form=form, certificate=certificate,
                                     excel_data=excel_data, is_specimen_step=True)

            # Get values from form
            specimen_id = form.specimen_id.data or ''
            specimen_type = form.specimen_type.data or 'SE(B)'
            W = form.W.data or 25.0
            B = form.B.data or 12.0
            B_n = form.B_n.data or B
            a_0 = form.a_0.data or 12.5
            S = form.S.data if specimen_type == 'SE(B)' else None
            yield_strength = form.yield_strength.data or 500.0
            ultimate_strength = form.ultimate_strength.data
            youngs_modulus = form.youngs_modulus.data or 210.0
            poissons_ratio = form.poissons_ratio.data or 0.3
            temperature = form.temperature.data or 23.0
            material_name = form.material.data or ''

            # Get crack measurements from form
            crack_measurements = []
            for i in range(1, 6):
                val = getattr(form, f'crack_{i}').data
                if val is not None and val > 0:
                    crack_measurements.append(val)

            # Recalculate a_0 if 5-point measurements provided
            if len(crack_measurements) == 5:
                a = crack_measurements
                a_0 = (0.5 * a[0] + a[1] + a[2] + a[3] + 0.5 * a[4]) / 4
                current_app.logger.info(f'KIC: Using calculated crack length from 5-point measurements: a_0={a_0:.3f} mm')

            # Validate required values
            validation_errors = []
            if not W or W <= 0:
                validation_errors.append('Width (W) is required')
            if not B or B <= 0:
                validation_errors.append('Thickness (B) is required')
            if not a_0 or a_0 <= 0:
                validation_errors.append('Initial crack length (a₀) is required')
            if not yield_strength or yield_strength <= 0:
                validation_errors.append('Yield strength is required')

            if validation_errors:
                for error in validation_errors:
                    flash(f'{error}', 'danger')
                return render_template('kic/new.html', form=form, certificate=certificate,
                                     excel_data=excel_data, is_specimen_step=True)

            # Create specimen and material objects
            import numpy as np
            specimen_obj = KICSpecimen(
                specimen_id=specimen_id,
                specimen_type=specimen_type,
                W=W,
                B=B,
                B_n=B_n,
                a_0=a_0,
                S=S or 0.0
            )

            material_obj = KICMaterial(
                yield_strength=yield_strength,
                youngs_modulus=youngs_modulus,
                poissons_ratio=poissons_ratio
            )

            # Run analysis
            analyzer = KICAnalyzer()
            result = analyzer.run_analysis(np.array(force), np.array(displacement), specimen_obj, material_obj)

            # Build geometry dict for storage
            specimen_geometry = {
                'type': specimen_type,
                'W': W,
                'B': B,
                'B_n': B_n,
                'a_0': a_0,
                'S': S,
            }
            if len(crack_measurements) == 5:
                specimen_geometry['crack_measurements'] = crack_measurements

            material_props = {
                'yield_strength': yield_strength,
                'ultimate_strength': ultimate_strength,
                'youngs_modulus': youngs_modulus,
                'poissons_ratio': poissons_ratio,
            }

            raw_data = {
                'force': force.tolist() if hasattr(force, 'tolist') else list(force),
                'displacement': displacement.tolist() if hasattr(displacement, 'tolist') else list(displacement),
                'mts_results': excel_data.get('kic_results', {}),
            }

            geometry_data = {
                'specimen_geometry': specimen_geometry,
                'material_properties': material_props,
                'location_orientation': form.location_orientation.data,
                'notes': form.notes.data,
                'raw_data': raw_data,
            }

            # Handle photo uploads (save to static/uploads for serving)
            photos = []
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            photos_folder = Path(current_app.root_path) / 'static' / 'uploads'
            photos_folder.mkdir(parents=True, exist_ok=True)
            for i in range(1, 4):
                photo_field = getattr(form, f'photo_{i}', None)
                desc_field = getattr(form, f'photo_description_{i}', None)
                if photo_field and photo_field.data:
                    photo = photo_field.data
                    filename = secure_filename(photo.filename)
                    filename = f"kic_{timestamp}_{i}_{filename}"
                    filepath = photos_folder / filename
                    photo.save(filepath)
                    photos.append({
                        'filename': filename,
                        'description': desc_field.data if desc_field else ''
                    })
            if photos:
                geometry_data['photos'] = photos

            # Handle pre-crack CSV
            if form.precrack_csv_file.data:
                precrack_file = form.precrack_csv_file.data
                precrack_filename = secure_filename(precrack_file.filename)
                precrack_path = Path(current_app.config['UPLOAD_FOLDER']) / f"precrack_{timestamp}_{precrack_filename}"
                precrack_file.save(precrack_path)

                # Parse pre-crack data
                precrack_geometry = {
                    'W': W,
                    'B': B,
                    'a_0': a_0,
                    'specimen_type': specimen_type,
                    'S': S,
                    'yield_strength': yield_strength,
                    'youngs_modulus': youngs_modulus
                }
                precrack_data = parse_precrack_csv(precrack_path, precrack_geometry)

                # Estimate expected K for compliance check (use K_Q estimate)
                expected_K = result.K_Q.value if result else 50.0

                # Validate compliance
                precrack_compliance = validate_precrack_compliance(
                    precrack_data,
                    expected_K=expected_K,
                    test_standard='ASTM E399',
                    specimen_geometry=precrack_geometry
                )

                geometry_data['precrack'] = {
                    'filename': precrack_filename,
                    'total_cycles': precrack_data['total_cycles'],
                    'K_max': precrack_data['K_max'],
                    'K_min': precrack_data['K_min'],
                    'load_ratio': precrack_data['load_ratio'],
                    'compliance': precrack_compliance
                }

            # Store uncertainty inputs
            geometry_data['uncertainty_inputs'] = {
                'force_pct': form.force_uncertainty.data or 1.0,
                'displacement_pct': form.displacement_uncertainty.data or 1.0,
                'dimension_pct': form.dimension_uncertainty.data or 0.5
            }

            # Calculate uncertainty budget
            force_u = (form.force_uncertainty.data or 1.0) / 100
            disp_u = (form.displacement_uncertainty.data or 1.0) / 100
            dim_u = (form.dimension_uncertainty.data or 0.5) / 100
            # Combined uncertainty (simplified RSS)
            combined = (force_u**2 + disp_u**2 + 4*dim_u**2)**0.5 * 100  # approx for K
            geometry_data['uncertainty_budget'] = {
                'combined': combined,
                'expanded': combined * 2,
                'coverage_factor': 2.0
            }

            # Handle re-analysis vs new test
            if reanalyze_id:
                test = TestRecord.query.get_or_404(reanalyze_id)
                test.specimen_id = specimen_id
                test.material = material_name
                test.temperature = temperature
                test.geometry = geometry_data
                test.status = 'REANALYZED'

                # Delete old analysis results
                AnalysisResult.query.filter_by(test_record_id=test.id).delete()
                db.session.flush()

                session.pop('kic_reanalyze_id', None)
                action = 'REANALYZE'
                test_id = test.test_id
            else:
                test_id = form.test_id.data
                selected_cert_id = form.certificate_id.data if form.certificate_id.data and form.certificate_id.data > 0 else None
                selected_cert = Certificate.query.get(selected_cert_id) if selected_cert_id else None
                cert_number = selected_cert.certificate_number_with_rev if selected_cert else None

                test = TestRecord(
                    test_id=test_id,
                    test_method='KIC',
                    specimen_id=specimen_id,
                    material=material_name,
                    test_date=form.test_date.data or datetime.now().date(),
                    temperature=temperature,
                    geometry=geometry_data,
                    status='ANALYZED',
                    certificate_id=selected_cert_id,
                    certificate_number=cert_number,
                    operator_id=current_user.id
                )
                db.session.add(test)
                db.session.flush()
                action = 'CREATE'

            # Store analysis results
            results_to_store = [
                ('P_max', result.P_max.value, result.P_max.uncertainty, 'kN'),
                ('P_Q', result.P_Q.value, result.P_Q.uncertainty, 'kN'),
                ('K_Q', result.K_Q.value, result.K_Q.uncertainty, 'MPa*m^0.5'),
                ('P_ratio', result.P_ratio, None, '-'),
                ('compliance', result.compliance, None, 'mm/kN'),
            ]
            if result.K_IC:
                results_to_store.append(('K_IC', result.K_IC.value, result.K_IC.uncertainty, 'MPa*m^0.5'))

            for param_name, value, uncertainty, unit in results_to_store:
                analysis = AnalysisResult(
                    test_record_id=test.id,
                    parameter_name=param_name,
                    value=value,
                    uncertainty=uncertainty,
                    unit=unit,
                    is_valid=result.is_valid,
                    validity_notes=', '.join(result.validity_notes) if result.validity_notes else None,
                    calculated_by_id=current_user.id
                )
                db.session.add(analysis)

            # Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action=action,
                table_name='test_record',
                record_id=test.id,
                new_values=json.dumps({'test_id': test_id, 'test_method': 'KIC'})
            )
            db.session.add(audit)
            db.session.commit()

            # Clear session data
            session.pop('kic_excel_path', None)
            session.pop('kic_excel_data', None)
            session.pop('kic_csv_path', None)
            session.pop('kic_certificate_id', None)

            if action == 'REANALYZE':
                flash(f'Re-analysis complete! Test ID: {test_id}', 'success')
            else:
                flash(f'KIC analysis complete! Test ID: {test_id}', 'success')

            if not result.is_valid:
                flash(f'Warning: {", ".join(result.validity_notes)}', 'warning')

            return redirect(url_for('kic.view', test_id=test.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Analysis error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('kic/new.html', form=form, certificate=certificate,
                         excel_data=excel_data, is_specimen_step=True)


@kic_bp.route('/<int:test_id>/reanalyze', methods=['GET', 'POST'])
@login_required
def reanalyze(test_id):
    """Re-analyze test with modified parameters."""
    test = TestRecord.query.get_or_404(test_id)
    geometry_data = test.geometry or {}
    geometry = geometry_data.get('specimen_geometry', {})
    material_props = geometry_data.get('material_properties', {})

    # Store test data in session for the specimen step
    session['kic_excel_data'] = {
        'filename': f'(Re-analysis of {test.test_id})',
        'specimen_id': test.specimen_id,
        'specimen_type': geometry.get('type', 'SE(B)'),
        'W': geometry.get('W'),
        'B': geometry.get('B'),
        'B_n': geometry.get('B_n'),
        'a_0': geometry.get('a_0'),
        'S': geometry.get('S'),
        'yield_strength': material_props.get('yield_strength'),
        'ultimate_strength': material_props.get('ultimate_strength'),
        'youngs_modulus': material_props.get('youngs_modulus'),
        'poissons_ratio': material_props.get('poissons_ratio'),
        'test_temperature': test.temperature,
        'material': test.material,
        'crack_measurements': geometry.get('crack_measurements', []),
        'kic_results': geometry_data.get('raw_data', {}).get('mts_results', {}),
    }

    # Mark this as a re-analysis
    session['kic_reanalyze_id'] = test_id

    # Store certificate if linked
    if test.certificate_id:
        session['kic_certificate_id'] = test.certificate_id
    else:
        session.pop('kic_certificate_id', None)

    # Clear any old CSV path - user must re-upload for re-analysis
    session.pop('kic_csv_path', None)

    flash(f'Loaded test {test.test_id} for re-analysis. Please upload the CSV test data and modify parameters as needed.', 'info')
    return redirect(url_for('kic.specimen'))


@kic_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View KIC test details and results."""
    test = TestRecord.query.get_or_404(test_id)

    if test.test_method != 'KIC':
        flash('Invalid test type.', 'error')
        return redirect(url_for('kic.index'))

    # Parse stored data (geometry is JSON dict, not string)
    geometry_data = test.geometry if test.geometry else {}
    geometry = geometry_data.get('specimen_geometry', {})
    material_props = geometry_data.get('material_properties', {})
    raw_data = geometry_data.get('raw_data', {})

    # Get analysis results (individual records per parameter)
    results = {}
    analysis_records = AnalysisResult.query.filter_by(test_record_id=test.id).all()
    validity_notes = []
    is_valid = True
    for ar in analysis_records:
        if ar.parameter_name in ('P_max', 'P_Q', 'K_Q', 'K_IC'):
            results[ar.parameter_name] = {'value': ar.value, 'uncertainty': ar.uncertainty}
        else:
            results[ar.parameter_name] = ar.value
        if ar.validity_notes:
            validity_notes.append(ar.validity_notes)
        if not ar.is_valid:
            is_valid = False
    results['is_valid'] = is_valid
    results['validity_notes'] = validity_notes

    # Create plot if we have data
    force_disp_plot = None
    if 'force' in raw_data and 'displacement' in raw_data:
        P_Q = results.get('P_Q', {}).get('value') if results.get('P_Q') else None
        P_max = results.get('P_max', {}).get('value') if results.get('P_max') else None
        force_disp_plot = create_force_displacement_plot(
            raw_data['force'],
            raw_data['displacement'],
            P_Q=P_Q,
            P_max=P_max
        )

    # Build photo URLs
    photo_urls = []
    for photo in geometry_data.get('photos', []):
        photo_urls.append({
            'url': url_for('static', filename=f"uploads/{photo['filename']}"),
            'description': photo.get('description', '')
        })

    # Merge geometry_data into geometry for template access
    geometry.update({
        'precrack': geometry_data.get('precrack'),
        'uncertainty_inputs': geometry_data.get('uncertainty_inputs'),
        'uncertainty_budget': geometry_data.get('uncertainty_budget'),
    })

    return render_template('kic/view.html',
                           test=test,
                           geometry=geometry,
                           material_props=material_props,
                           results=results,
                           force_disp_plot=force_disp_plot,
                           photo_urls=photo_urls)


@kic_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate KIC test report."""
    test = TestRecord.query.get_or_404(test_id)

    if test.test_method != 'KIC':
        flash('Invalid test type.', 'error')
        return redirect(url_for('kic.index'))

    form = ReportForm()

    # Pre-fill certificate number
    if request.method == 'GET':
        form.certificate_number.data = test.certificate_number or test.test_id

    if form.validate_on_submit():
        try:
            # Parse stored data (geometry is JSON dict, not string)
            geometry_data = test.geometry if test.geometry else {}
            geometry = geometry_data.get('specimen_geometry', {})
            material_props = geometry_data.get('material_properties', {})
            raw_data = geometry_data.get('raw_data', {})

            # Get analysis results (individual records per parameter)
            results = {}
            analysis_records = AnalysisResult.query.filter_by(test_record_id=test.id).all()
            validity_notes = []
            is_valid = True
            for ar in analysis_records:
                if ar.parameter_name in ('P_max', 'P_Q', 'K_Q', 'K_IC'):
                    results[ar.parameter_name] = {'value': ar.value, 'uncertainty': ar.uncertainty}
                else:
                    results[ar.parameter_name] = ar.value
                if ar.validity_notes:
                    validity_notes.append(ar.validity_notes)
                if not ar.is_valid:
                    is_valid = False
            results['is_valid'] = is_valid
            results['validity_notes'] = validity_notes

            # Generate chart image for report
            chart_path = None
            if 'force' in raw_data and 'displacement' in raw_data:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt
                import numpy as np

                fig, ax = plt.subplots(figsize=(8, 6))
                force = np.array(raw_data['force'])
                displacement = np.array(raw_data['displacement'])

                ax.plot(displacement, force, color='darkred', linewidth=1.5, label='Force vs Displacement')

                # Mark PQ - grey diamond
                P_Q_data = results.get('P_Q')
                if P_Q_data and isinstance(P_Q_data, dict):
                    P_Q = P_Q_data.get('value')
                    if P_Q:
                        idx = np.argmin(np.abs(force - P_Q))
                        ax.plot(displacement[idx], P_Q, 'D', color='grey', markersize=10,
                               markerfacecolor='none', markeredgewidth=2, label=f'PQ = {P_Q:.2f} kN')

                # Mark Pmax - grey square
                P_max_data = results.get('P_max')
                if P_max_data and isinstance(P_max_data, dict):
                    P_max = P_max_data.get('value')
                    if P_max:
                        idx = np.argmax(force)
                        ax.plot(displacement[idx], P_max, 's', color='grey', markersize=12,
                               markerfacecolor='none', markeredgewidth=2, label=f'Pmax = {P_max:.2f} kN')

                ax.set_xlabel('Displacement (mm)')
                ax.set_ylabel('Force (kN)')
                ax.set_title('Force vs Displacement (ASTM E399)')
                ax.legend()
                ax.grid(True, alpha=0.3)

                chart_path = Path(current_app.config['REPORTS_FOLDER']) / f'kic_chart_{test.id}.png'
                fig.savefig(chart_path, dpi=150, bbox_inches='tight')
                plt.close(fig)

            # Prepare report data
            test_info = {
                'certificate_number': form.certificate_number.data or test.test_id,
                'test_project': test.certificate.test_project if test.certificate else '',
                'customer': test.certificate.customer if test.certificate else '',
                'specimen_id': test.specimen_id or '',
                'material': test.material or '',
                'test_date': test.test_date.strftime('%Y-%m-%d') if test.test_date else '',
                'temperature': test.temperature or '23',
            }

            dimensions = {
                'specimen_type': geometry.get('type', 'SE(B)'),
                'W': str(geometry.get('W', '')),
                'B': str(geometry.get('B', '')),
                'B_n': str(geometry.get('B_n', '')),
                'a_0': str(geometry.get('a_0', '')),
                'S': str(geometry.get('S', '-')),
            }

            mat_props = {
                'yield_strength': str(material_props.get('yield_strength', '')),
                'ultimate_strength': str(material_props.get('ultimate_strength', '')),
                'youngs_modulus': str(material_props.get('youngs_modulus', '')),
                'poissons_ratio': str(material_props.get('poissons_ratio', '0.3')),
            }

            # Create result object for report generator
            class ResultProxy:
                def __init__(self, data):
                    self._data = data

                @property
                def P_max(self):
                    d = self._data.get('P_max', {})
                    if isinstance(d, dict):
                        return type('MV', (), {'value': d.get('value', 0), 'uncertainty': d.get('uncertainty', 0)})()
                    return type('MV', (), {'value': 0, 'uncertainty': 0})()

                @property
                def P_Q(self):
                    d = self._data.get('P_Q', {})
                    if isinstance(d, dict):
                        return type('MV', (), {'value': d.get('value', 0), 'uncertainty': d.get('uncertainty', 0)})()
                    return type('MV', (), {'value': 0, 'uncertainty': 0})()

                @property
                def K_Q(self):
                    d = self._data.get('K_Q', {})
                    if isinstance(d, dict):
                        return type('MV', (), {'value': d.get('value', 0), 'uncertainty': d.get('uncertainty', 0)})()
                    return type('MV', (), {'value': 0, 'uncertainty': 0})()

                @property
                def K_IC(self):
                    d = self._data.get('K_IC')
                    if d and isinstance(d, dict):
                        return type('MV', (), {'value': d.get('value', 0), 'uncertainty': d.get('uncertainty', 0)})()
                    return None

                @property
                def P_ratio(self):
                    return self._data.get('P_ratio', 0)

                @property
                def compliance(self):
                    return self._data.get('compliance', 0)

                @property
                def is_valid(self):
                    return self._data.get('is_valid', False)

                @property
                def validity_notes(self):
                    return self._data.get('validity_notes', [])

            result_proxy = ResultProxy(results)

            # Get logo path
            logo_path = Path(current_app.root_path) / 'static' / 'images' / 'logo.png'
            if not logo_path.exists():
                logo_path = Path('templates') / 'logo.png'

            # Get crack measurements
            crack_measurements = geometry.get('crack_measurements', [])

            # Generate report
            generator = KICReportGenerator()
            output_filename = f"KIC_Report_{test.test_id.replace(' ', '_')}.docx"
            output_path = Path(current_app.config['REPORTS_FOLDER']) / output_filename

            generator.generate_report(
                output_path=output_path,
                test_info=test_info,
                dimensions=dimensions,
                material_props=mat_props,
                results=result_proxy,
                chart_path=chart_path if chart_path and chart_path.exists() else None,
                logo_path=logo_path if logo_path.exists() else None,
                precrack_measurements=crack_measurements if len(crack_measurements) == 5 else None
            )

            # Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action='REPORT',
                table_name='test_record',
                record_id=test.id,
                new_values=json.dumps({'report': output_filename})
            )
            db.session.add(audit)
            db.session.commit()

            return send_file(
                output_path,
                as_attachment=True,
                download_name=output_filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

        except Exception as e:
            flash(f'Error generating report: {e}', 'error')
            return redirect(url_for('kic.view', test_id=test.id))

    return render_template('kic/report.html', test=test, form=form)


@kic_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a KIC test (admin only)."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('kic.index'))

    test = TestRecord.query.get_or_404(test_id)

    if test.test_method != 'KIC':
        flash('Invalid test type.', 'error')
        return redirect(url_for('kic.index'))

    test_id_str = test.test_id

    # Audit log before deletion
    audit = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        table_name='test_record',
        record_id=test.id,
        old_values=json.dumps({'test_id': test_id_str, 'test_method': 'KIC'})
    )
    db.session.add(audit)

    # Delete analysis results first
    AnalysisResult.query.filter_by(test_record_id=test.id).delete()
    db.session.delete(test)
    db.session.commit()

    flash(f'KIC test {test_id_str} deleted.', 'success')
    return redirect(url_for('kic.index'))
