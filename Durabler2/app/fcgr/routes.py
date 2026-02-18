"""FCGR (Fatigue Crack Growth Rate) test routes - ASTM E647."""
import os
from pathlib import Path
from datetime import datetime

from flask import (render_template, redirect, url_for, flash, request,
                   current_app, send_file, session, Response)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from . import fcgr_bp
from .forms import UploadForm, SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate, RawTestData, TestPhoto, ReportFile

# Import analysis utilities
from utils.analysis.fcgr_calculations import FCGRAnalyzer
from utils.models.fcgr_specimen import (
    FCGRSpecimen, FCGRMaterial, FCGRTestParameters, FCGRResult
)
from utils.data_acquisition.fcgr_excel_parser import parse_fcgr_excel
from utils.data_acquisition.fcgr_csv_parser import (
    parse_fcgr_csv, extract_cycle_extrema, calculate_compliance_per_cycle
)
from utils.data_acquisition.precrack_csv_parser import parse_precrack_csv, validate_precrack_compliance
from utils.reporting.fcgr_word_report import FCGRReportGenerator


def generate_test_id():
    """Generate unique test ID."""
    today = datetime.now()
    prefix = f"FCGR-{today.strftime('%y%m%d')}"
    count = TestRecord.query.filter(
        TestRecord.test_id.like(f'{prefix}%')
    ).count()
    return f"{prefix}-{count + 1:03d}"


def create_crack_length_plot(cycles, crack_lengths, specimen_id):
    """Create crack length vs cycles plot."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=cycles,
        y=crack_lengths,
        mode='lines+markers',
        name='Crack Length, a (mm)',
        marker=dict(size=4, color='darkred'),
        line=dict(width=1.5, color='darkred')
    ))

    # Y-axis: 1 mm tick intervals, start at 0
    y_max = max(crack_lengths) if len(crack_lengths) > 0 else 1
    y_range_max = y_max * 1.05  # 5% margin

    fig.update_layout(
        title=f'Crack Length vs Cycles - {specimen_id}',
        xaxis_title='Cycles (N)',
        yaxis_title='Crack Length, a (mm)',
        xaxis=dict(range=[0, None]),  # Start X-axis at 0
        yaxis=dict(range=[0, y_range_max], dtick=1),  # Start Y-axis at 0, 1 mm steps
        template='plotly_white',
        height=400,
        showlegend=True,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )

    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')


def create_paris_law_plot(delta_K, da_dN, paris_result, paris_initial, outlier_mask, specimen_id):
    """Create da/dN vs Delta-K (Paris law) plot."""
    fig = go.Figure()

    # Separate valid and outlier points
    valid_mask = ~outlier_mask
    dK_valid = delta_K[valid_mask]
    dadN_valid = da_dN[valid_mask]
    dK_outlier = delta_K[outlier_mask]
    dadN_outlier = da_dN[outlier_mask]

    # Plot valid data points - darkred circles
    fig.add_trace(go.Scatter(
        x=dK_valid,
        y=dadN_valid,
        mode='markers',
        name='Valid Data',
        marker=dict(size=6, color='darkred', symbol='circle')
    ))

    # Plot outliers - grey x markers
    if len(dK_outlier) > 0:
        fig.add_trace(go.Scatter(
            x=dK_outlier,
            y=dadN_outlier,
            mode='markers',
            name='Outliers',
            marker=dict(size=6, color='grey', symbol='x')
        ))

    # Plot Paris law regression line (final - without outliers) - black
    if paris_result.C > 0 and paris_result.m > 0:
        dK_range = np.logspace(
            np.log10(paris_result.delta_K_range[0] * 0.9),
            np.log10(paris_result.delta_K_range[1] * 1.1),
            100
        )
        dadN_fit = paris_result.C * dK_range ** paris_result.m

        fig.add_trace(go.Scatter(
            x=dK_range,
            y=dadN_fit,
            mode='lines',
            name=f'Paris Law: C={paris_result.C:.2e}, m={paris_result.m:.2f}',
            line=dict(width=2, color='black')
        ))

    # Plot initial regression line (all data) - thin grey dotted
    if paris_initial and paris_initial.C > 0 and paris_initial.m > 0:
        dK_range_init = np.logspace(
            np.log10(paris_initial.delta_K_range[0] * 0.9),
            np.log10(paris_initial.delta_K_range[1] * 1.1),
            100
        )
        dadN_fit_init = paris_initial.C * dK_range_init ** paris_initial.m

        fig.add_trace(go.Scatter(
            x=dK_range_init,
            y=dadN_fit_init,
            mode='lines',
            name=f'Initial Fit: C={paris_initial.C:.2e}, m={paris_initial.m:.2f}',
            line=dict(width=1, color='grey', dash='dot')
        ))

    fig.update_layout(
        title=f'Paris Law Plot - {specimen_id}',
        xaxis_title='ΔK (MPa√m)',
        yaxis_title='da/dN (mm/cycle)',
        xaxis=dict(type='log', showgrid=True, gridwidth=1, gridcolor='lightgrey',
                   minor=dict(showgrid=True, gridwidth=0.5, gridcolor='#f0f0f0')),
        yaxis=dict(type='log', showgrid=True, gridwidth=1, gridcolor='lightgrey',
                   minor=dict(showgrid=True, gridwidth=0.5, gridcolor='#f0f0f0')),
        template='plotly_white',
        height=450,
        legend=dict(yanchor="bottom", y=0.01, xanchor="right", x=0.99)
    )

    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')


@fcgr_bp.route('/')
@login_required
def index():
    """List all FCGR tests."""
    tests = TestRecord.query.filter_by(test_method='FCGR').order_by(
        TestRecord.test_date.desc()
    ).all()
    return render_template('fcgr/index.html', tests=tests)


@fcgr_bp.route('/new', methods=['GET', 'POST'])
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

            excel_data = parse_fcgr_excel(filepath)

            # Calculate a_0 from 5-point measurements if available
            a_0_calculated = excel_data.a_0
            precrack_measurements = excel_data.precrack_measurements or []
            if len(precrack_measurements) == 5:
                a = precrack_measurements
                a_0_calculated = (0.5 * a[0] + a[1] + a[2] + a[3] + 0.5 * a[4]) / 4
                current_app.logger.info(f'FCGR: Calculated crack length from 5-point measurements: a_0={a_0_calculated:.3f} mm')

            # Store parsed data in session
            session['fcgr_excel_path'] = str(filepath)
            session['fcgr_excel_data'] = {
                'filename': filename,
                'specimen_id': excel_data.specimen_id,
                'specimen_type': excel_data.specimen_type,
                'W': excel_data.W,
                'B': excel_data.B,
                'B_n': excel_data.B_n,
                'a_0': a_0_calculated,
                'a_0_notch': excel_data.a_0,
                'notch_height': excel_data.notch_height,
                'yield_strength': excel_data.yield_strength,
                'ultimate_strength': excel_data.ultimate_strength,
                'youngs_modulus': excel_data.youngs_modulus,
                'poissons_ratio': excel_data.poissons_ratio,
                'test_temperature': excel_data.test_temperature,
                'material': excel_data.material,
                'precrack_measurements': precrack_measurements,
                'precrack_final_size': excel_data.precrack_final_size,
                'control_mode': excel_data.control_mode,
                'load_ratio': excel_data.load_ratio,
                'frequency': excel_data.frequency,
                'wave_shape': excel_data.wave_shape,
            }

            # Store certificate selection
            if form.certificate_id.data and form.certificate_id.data > 0:
                session['fcgr_certificate_id'] = form.certificate_id.data
            else:
                session.pop('fcgr_certificate_id', None)

            # Clear any existing CSV path (CSV is uploaded in Step 2)
            session.pop('fcgr_csv_path', None)

            flash(f'Excel data imported: {excel_data.specimen_id}, W={excel_data.W}mm, B={excel_data.B}mm, a₀={a_0_calculated:.2f}mm', 'success')
            return redirect(url_for('fcgr.specimen'))

        except Exception as e:
            flash(f'Error parsing Excel file: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('fcgr/upload.html', form=form)


@fcgr_bp.route('/specimen', methods=['GET', 'POST'])
@login_required
def specimen():
    """Step 2: Review imported data and run analysis."""
    # Check if Excel was uploaded
    if 'fcgr_excel_data' not in session:
        flash('Please upload an Excel file first.', 'warning')
        return redirect(url_for('fcgr.new'))

    excel_data = session.get('fcgr_excel_data', {})
    certificate_id = session.get('fcgr_certificate_id')
    certificate = Certificate.query.get(certificate_id) if certificate_id else None
    reanalyze_id = session.get('fcgr_reanalyze_id')

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
        if excel_data.get('notch_height'):
            form.notch_height.data = excel_data['notch_height']
        if excel_data.get('yield_strength'):
            form.yield_strength.data = excel_data['yield_strength']
        if excel_data.get('ultimate_strength'):
            form.ultimate_strength.data = excel_data['ultimate_strength']
        if excel_data.get('youngs_modulus'):
            form.youngs_modulus.data = excel_data['youngs_modulus']
        if excel_data.get('poissons_ratio'):
            form.poissons_ratio.data = excel_data['poissons_ratio']
        if excel_data.get('test_temperature'):
            form.test_temperature.data = excel_data['test_temperature']
        if excel_data.get('material'):
            form.material.data = excel_data['material']
        if excel_data.get('control_mode'):
            form.control_mode.data = excel_data['control_mode']
        if excel_data.get('load_ratio') is not None:
            form.load_ratio.data = excel_data['load_ratio']
        if excel_data.get('frequency'):
            form.frequency.data = excel_data['frequency']
        if excel_data.get('wave_shape'):
            form.wave_shape.data = excel_data['wave_shape']

        # Certificate data overrides Excel data
        if certificate:
            if certificate.material:
                form.material.data = certificate.material
            if certificate.test_article_sn:
                form.specimen_id.data = certificate.test_article_sn
            if certificate.product_sn:
                form.batch_number.data = certificate.product_sn
            if certificate.customer_specimen_info:
                form.customer_specimen_info.data = certificate.customer_specimen_info
            if certificate.requirement:
                form.requirement.data = certificate.requirement
            if certificate.temperature:
                try:
                    temp_str = certificate.temperature.replace('°C', '').replace('C', '').strip()
                    form.test_temperature.data = float(temp_str)
                except (ValueError, AttributeError):
                    pass
            form.certificate_id.data = certificate_id

    if form.validate_on_submit():
        try:
            # Get CSV data for analysis
            csv_path = session.get('fcgr_csv_path')
            csv_data = None
            cycles = None
            P_max = None
            P_min = None
            compliance_arr = None

            if csv_path and Path(csv_path).exists():
                csv_data = parse_fcgr_csv(csv_path)
                cycle_nums, P_max_arr, P_min_arr, COD_max, COD_min = extract_cycle_extrema(csv_data)
                _, compliance_arr = calculate_compliance_per_cycle(csv_data)
                cycles = cycle_nums.astype(float)
                P_max = P_max_arr
                P_min = P_min_arr
            elif form.csv_file.data:
                # User uploaded CSV in this step
                csv_file = form.csv_file.data
                filename = secure_filename(csv_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                csv_filepath = Path(current_app.config['UPLOAD_FOLDER']) / f"{timestamp}_{filename}"
                csv_file.save(csv_filepath)
                csv_data = parse_fcgr_csv(csv_filepath)
                cycle_nums, P_max_arr, P_min_arr, COD_max, COD_min = extract_cycle_extrema(csv_data)
                _, compliance_arr = calculate_compliance_per_cycle(csv_data)
                cycles = cycle_nums.astype(float)
                P_max = P_max_arr
                P_min = P_min_arr

            if csv_data is None or cycles is None:
                flash('Please upload CSV test data with cyclic Force-Displacement data.', 'danger')
                return render_template('fcgr/new.html', form=form, certificate=certificate,
                                     excel_data=excel_data, is_specimen_step=True)

            # Get values from form
            specimen_id = form.specimen_id.data or ''
            specimen_type = form.specimen_type.data or 'C(T)'
            W = form.W.data or 50.0
            B = form.B.data or 12.5
            B_n = form.B_n.data or B
            a_0 = form.a_0.data or 10.0
            notch_height = form.notch_height.data or 0.0
            yield_strength = form.yield_strength.data or 0.0
            ultimate_strength = form.ultimate_strength.data or 0.0
            youngs_modulus = form.youngs_modulus.data or 210.0
            poissons_ratio = form.poissons_ratio.data or 0.3
            test_temperature = form.test_temperature.data or 23.0
            material_name = form.material.data or ''
            control_mode = form.control_mode.data or 'Load Control'
            load_ratio = form.load_ratio.data if form.load_ratio.data is not None else 0.1
            frequency = form.frequency.data or 10.0
            wave_shape = form.wave_shape.data or 'Sine'

            # Validate required values
            validation_errors = []
            if not W or W <= 0:
                validation_errors.append('Width (W) is required')
            if not B or B <= 0:
                validation_errors.append('Thickness (B) is required')
            if not a_0 or a_0 <= 0:
                validation_errors.append('Initial crack length (a₀) is required')
            if not youngs_modulus or youngs_modulus <= 0:
                validation_errors.append("Young's modulus (E) is required")

            if validation_errors:
                for error in validation_errors:
                    flash(f'{error}', 'danger')
                return render_template('fcgr/new.html', form=form, certificate=certificate,
                                     excel_data=excel_data, is_specimen_step=True)

            # Create analysis objects
            specimen_obj = FCGRSpecimen(
                specimen_id=specimen_id,
                specimen_type=specimen_type,
                W=W,
                B=B,
                B_n=B_n,
                a_0=a_0,
                notch_height=notch_height,
                material=material_name
            )

            material_obj = FCGRMaterial(
                yield_strength=yield_strength,
                ultimate_strength=ultimate_strength,
                youngs_modulus=youngs_modulus,
                poissons_ratio=poissons_ratio
            )

            test_params = FCGRTestParameters(
                control_mode=control_mode,
                load_ratio=load_ratio,
                frequency=frequency,
                wave_shape=wave_shape,
                environment=form.environment.data or 'Laboratory Air',
                temperature=test_temperature
            )

            # Run analysis
            analyzer = FCGRAnalyzer(specimen_obj, material_obj, test_params)
            crack_lengths = np.array([analyzer.crack_length_from_compliance(c) for c in compliance_arr])

            results = analyzer.analyze_from_raw_data(
                cycles=cycles,
                crack_lengths=crack_lengths,
                P_max=P_max,
                P_min=P_min,
                method=form.dadn_method.data,
                outlier_threshold=form.outlier_threshold.data or 2.5
            )

            # Build geometry dict for storage
            geometry = {
                'type': specimen_type,
                'W': float(W),
                'B': float(B),
                'B_n': float(B_n),
                'a_0': float(a_0),
                'notch_height': float(notch_height),
                'yield_strength': float(yield_strength),
                'ultimate_strength': float(ultimate_strength),
                'youngs_modulus': float(youngs_modulus),
                'poissons_ratio': float(poissons_ratio),
                'load_ratio': float(load_ratio),
                'frequency': float(frequency),
                'control_mode': control_mode,
                'wave_shape': wave_shape,
                'dadn_method': form.dadn_method.data,
                'outlier_threshold': float(form.outlier_threshold.data or 2.5),
                'precrack_measurements': excel_data.get('precrack_measurements', []),
                'precrack_final_size': float(excel_data.get('precrack_final_size', 0)),
                # Raw data for crack length vs cycles plot (all points)
                'raw_cycles': [float(c) for c in cycles],
                'raw_crack_lengths': [float(a) for a in crack_lengths],
                # Processed data for Paris law plot (after da/dN calculation)
                'cycles': [float(p.cycle_count) for p in results.data_points],
                'crack_lengths': [float(p.crack_length) for p in results.data_points],
                'delta_K': [float(p.delta_K) for p in results.data_points],
                'da_dN': [float(p.da_dN) for p in results.data_points],
                'outlier_mask': [bool(p.is_outlier) for p in results.data_points],
                # Initial Paris law fit (before outlier removal)
                'paris_initial_C': float(results.paris_law_initial.C) if results.paris_law_initial else None,
                'paris_initial_m': float(results.paris_law_initial.m) if results.paris_law_initial else None,
                'paris_initial_dK_min': float(results.paris_law_initial.delta_K_range[0]) if results.paris_law_initial else None,
                'paris_initial_dK_max': float(results.paris_law_initial.delta_K_range[1]) if results.paris_law_initial else None,
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
                    filename = f"fcgr_{timestamp}_{i}_{filename}"
                    filepath = photos_folder / filename
                    photo.save(filepath)
                    photos.append({
                        'filename': filename,
                        'description': desc_field.data if desc_field else ''
                    })
            if photos:
                geometry['photos'] = photos

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
                    'notch_height': notch_height,
                    'yield_strength': yield_strength,
                    'youngs_modulus': youngs_modulus
                }
                precrack_data = parse_precrack_csv(precrack_path, precrack_geometry)

                # Estimate expected K for compliance check (initial test deltaK)
                expected_K = results.data_points[0].delta_K if results.data_points else 20.0

                # Validate compliance
                precrack_compliance = validate_precrack_compliance(
                    precrack_data,
                    expected_K=expected_K,
                    test_standard='ASTM E647',
                    specimen_geometry=precrack_geometry
                )

                geometry['precrack'] = {
                    'filename': precrack_filename,
                    'total_cycles': precrack_data['total_cycles'],
                    'K_max': precrack_data['K_max'],
                    'K_min': precrack_data['K_min'],
                    'load_ratio': precrack_data['load_ratio'],
                    'compliance': precrack_compliance
                }

            # Store uncertainty inputs
            geometry['uncertainty_inputs'] = {
                'force_pct': form.force_uncertainty.data or 1.0,
                'displacement_pct': form.displacement_uncertainty.data or 1.0,
                'dimension_pct': form.dimension_uncertainty.data or 0.5
            }

            # Calculate uncertainty budget
            force_u = (form.force_uncertainty.data or 1.0) / 100
            disp_u = (form.displacement_uncertainty.data or 1.0) / 100
            dim_u = (form.dimension_uncertainty.data or 0.5) / 100
            # Combined uncertainty (simplified RSS for FCGR)
            combined = (force_u**2 + disp_u**2 + 4*dim_u**2)**0.5 * 100
            geometry['uncertainty_budget'] = {
                'combined': combined,
                'expanded': combined * 2,
                'coverage_factor': 2.0
            }

            # Handle re-analysis vs new test
            if reanalyze_id:
                test_record = TestRecord.query.get_or_404(reanalyze_id)
                test_record.specimen_id = specimen_id
                test_record.material = material_name
                test_record.batch_number = form.batch_number.data
                test_record.temperature = test_temperature
                test_record.geometry = geometry
                test_record.status = 'REANALYZED'

                # Delete old analysis results
                AnalysisResult.query.filter_by(test_record_id=test_record.id).delete()
                db.session.flush()

                session.pop('fcgr_reanalyze_id', None)
                action = 'REANALYZE'
                test_id = test_record.test_id
            else:
                test_id = generate_test_id()
                selected_cert_id = form.certificate_id.data if form.certificate_id.data and form.certificate_id.data > 0 else None
                selected_cert = Certificate.query.get(selected_cert_id) if selected_cert_id else None
                cert_number = selected_cert.certificate_number_with_rev if selected_cert else None

                test_record = TestRecord(
                    test_id=test_id,
                    test_method='FCGR',
                    test_standard=form.test_standard.data,
                    specimen_id=specimen_id,
                    material=material_name,
                    batch_number=form.batch_number.data,
                    geometry=geometry,
                    test_date=datetime.now(),
                    temperature=test_temperature,
                    status='ANALYZED',
                    certificate_id=selected_cert_id,
                    certificate_number=cert_number,
                    operator_id=current_user.id
                )
                db.session.add(test_record)
                db.session.flush()
                action = 'CREATE'

            # Store analysis results
            results_data = [
                ('paris_C', float(results.paris_law.C), float(results.paris_law.std_error_C), '-'),
                ('paris_m', float(results.paris_law.m), float(results.paris_law.std_error_m), '-'),
                ('r_squared', float(results.paris_law.r_squared), 0, '-'),
                ('n_points', float(results.paris_law.n_points), 0, '-'),
                ('delta_K_min', float(results.paris_law.delta_K_range[0]), 0, 'MPa√m'),
                ('delta_K_max', float(results.paris_law.delta_K_range[1]), 0, 'MPa√m'),
                ('final_crack', float(results.final_crack_length), 0, 'mm'),
                ('total_cycles', float(results.total_cycles), 0, 'cycles'),
            ]

            for name, value, uncertainty, unit in results_data:
                db.session.add(AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name=name,
                    value=value,
                    uncertainty=uncertainty,
                    unit=unit,
                    calculated_by_id=current_user.id
                ))

            # Update geometry with validity info
            geometry['is_valid'] = results.is_valid
            geometry['validity_notes'] = results.validity_notes
            test_record.geometry = geometry

            # Store photos in database for data persistence
            for i in range(1, 4):
                photo_field = getattr(form, f'photo_{i}', None)
                desc_field = getattr(form, f'photo_description_{i}', None)
                if photo_field and photo_field.data:
                    photo_file = photo_field.data
                    photo_file.seek(0)
                    photo_data = photo_file.read()
                    db_photo = TestPhoto(
                        test_record_id=test_record.id,
                        photo_number=i,
                        description=desc_field.data if desc_field else '',
                        uploaded_by_id=current_user.id
                    )
                    db_photo.set_image(photo_data, photo_file.filename)
                    db.session.add(db_photo)

            # Store raw CSV data in database
            csv_path = session.get('fcgr_csv_path')
            if csv_path and Path(csv_path).exists():
                with open(csv_path, 'rb') as f:
                    csv_raw = RawTestData(
                        test_record_id=test_record.id,
                        data_type='csv',
                        original_filename=Path(csv_path).name,
                        mime_type='text/csv',
                        uploaded_by_id=current_user.id
                    )
                    csv_raw.set_data(f.read())
                    db.session.add(csv_raw)

            # Store Excel data in database
            excel_path = session.get('fcgr_excel_path')
            if excel_path and Path(excel_path).exists():
                with open(excel_path, 'rb') as f:
                    excel_raw = RawTestData(
                        test_record_id=test_record.id,
                        data_type='excel',
                        original_filename=Path(excel_path).name,
                        mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        uploaded_by_id=current_user.id
                    )
                    excel_raw.set_data(f.read())
                    db.session.add(excel_raw)

            # Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action=action,
                table_name='test_records',
                record_id=test_record.id,
                new_values={'test_id': test_id, 'specimen_id': specimen_id},
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

            # Clear session data
            session.pop('fcgr_excel_path', None)
            session.pop('fcgr_excel_data', None)
            session.pop('fcgr_csv_path', None)
            session.pop('fcgr_certificate_id', None)

            if action == 'REANALYZE':
                flash(f'Re-analysis complete! Test ID: {test_id}', 'success')
            else:
                flash(f'FCGR analysis complete! Test ID: {test_id}', 'success')

            if not results.is_valid:
                flash('Warning: Test validity issues detected.', 'warning')

            return redirect(url_for('fcgr.view', test_id=test_record.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Analysis error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('fcgr/new.html', form=form, certificate=certificate,
                         excel_data=excel_data, is_specimen_step=True)


@fcgr_bp.route('/<int:test_id>/reanalyze', methods=['GET', 'POST'])
@login_required
def reanalyze(test_id):
    """Re-analyze test with modified parameters."""
    test = TestRecord.query.get_or_404(test_id)
    geometry = test.geometry or {}

    # Store test data in session for the specimen step
    session['fcgr_excel_data'] = {
        'filename': f'(Re-analysis of {test.test_id})',
        'specimen_id': test.specimen_id,
        'specimen_type': geometry.get('type', 'C(T)'),
        'W': geometry.get('W'),
        'B': geometry.get('B'),
        'B_n': geometry.get('B_n'),
        'a_0': geometry.get('a_0'),
        'notch_height': geometry.get('notch_height'),
        'yield_strength': geometry.get('yield_strength'),
        'ultimate_strength': geometry.get('ultimate_strength'),
        'youngs_modulus': geometry.get('youngs_modulus'),
        'poissons_ratio': geometry.get('poissons_ratio'),
        'test_temperature': test.temperature,
        'material': test.material,
        'precrack_measurements': geometry.get('precrack_measurements', []),
        'precrack_final_size': geometry.get('precrack_final_size', 0),
        'control_mode': geometry.get('control_mode'),
        'load_ratio': geometry.get('load_ratio'),
        'frequency': geometry.get('frequency'),
        'wave_shape': geometry.get('wave_shape'),
    }

    # Mark this as a re-analysis
    session['fcgr_reanalyze_id'] = test_id

    # Store certificate if linked
    if test.certificate_id:
        session['fcgr_certificate_id'] = test.certificate_id
    else:
        session.pop('fcgr_certificate_id', None)

    # Clear any old CSV path - user must re-upload for re-analysis
    session.pop('fcgr_csv_path', None)

    flash(f'Loaded test {test.test_id} for re-analysis. Please upload the CSV test data and modify parameters as needed.', 'info')
    return redirect(url_for('fcgr.specimen'))


@fcgr_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View test results."""
    test = TestRecord.query.get_or_404(test_id)
    results = {r.parameter_name: r for r in test.results.all()}
    geometry = test.geometry or {}

    # Get raw data for crack length plot (all points, no outlier filtering)
    raw_cycles = geometry.get('raw_cycles', geometry.get('cycles', []))
    raw_crack_lengths = geometry.get('raw_crack_lengths', geometry.get('crack_lengths', []))

    # Get processed data for Paris law plot (with outlier info)
    delta_K = np.array(geometry.get('delta_K', []))
    da_dN = np.array(geometry.get('da_dN', []))
    outlier_mask = np.array(geometry.get('outlier_mask', []))

    # Create plots
    crack_plot = None
    paris_plot = None

    if len(raw_cycles) > 0:
        crack_plot = create_crack_length_plot(raw_cycles, raw_crack_lengths, test.specimen_id)

    if len(delta_K) > 0:
        # Create mock Paris law result for plotting
        class MockParis:
            def __init__(self, C, m, dK_range, dadN_range):
                self.C = C
                self.m = m
                self.delta_K_range = dK_range
                self.da_dN_range = dadN_range

        paris_C = results.get('paris_C')
        paris_m = results.get('paris_m')
        dK_min = results.get('delta_K_min')
        dK_max = results.get('delta_K_max')

        if paris_C and paris_m:
            paris_result = MockParis(
                paris_C.value, paris_m.value,
                (dK_min.value if dK_min else 1, dK_max.value if dK_max else 100),
                (1e-7, 1e-3)
            )

            # Create initial Paris law object (before outlier removal)
            paris_initial = None
            paris_init_C = geometry.get('paris_initial_C')
            paris_init_m = geometry.get('paris_initial_m')
            paris_init_dK_min = geometry.get('paris_initial_dK_min')
            paris_init_dK_max = geometry.get('paris_initial_dK_max')
            if paris_init_C and paris_init_m:
                paris_initial = MockParis(
                    paris_init_C, paris_init_m,
                    (paris_init_dK_min or 1, paris_init_dK_max or 100),
                    (1e-7, 1e-3)
                )

            paris_plot = create_paris_law_plot(
                delta_K, da_dN, paris_result, paris_initial, outlier_mask, test.specimen_id
            )

    # Build photo URLs - prefer database photos, fall back to file system
    photo_urls = []
    db_photos = test.photos.all()
    if db_photos:
        for photo in db_photos:
            photo_urls.append({
                'url': url_for('fcgr.photo', test_id=test_id, photo_id=photo.id),
                'description': photo.description or ''
            })
    else:
        for photo in geometry.get('photos', []):
            photo_urls.append({
                'url': url_for('static', filename=f"uploads/{photo['filename']}"),
                'description': photo.get('description', '')
            })

    return render_template('fcgr/view.html', test=test, results=results,
                          geometry=geometry, crack_plot=crack_plot, paris_plot=paris_plot,
                          photo_urls=photo_urls)


@fcgr_bp.route('/<int:test_id>/photo/<int:photo_id>')
@login_required
def photo(test_id, photo_id):
    """Serve photo from database."""
    photo = TestPhoto.query.filter_by(id=photo_id, test_record_id=test_id).first_or_404()
    return Response(
        photo.data,
        mimetype=photo.mime_type or 'image/jpeg',
        headers={'Content-Disposition': f'inline; filename="{photo.original_filename}"'}
    )


@fcgr_bp.route('/<int:test_id>/raw-data/<int:data_id>')
@login_required
def raw_data(test_id, data_id):
    """Download raw test data from database."""
    data = RawTestData.query.filter_by(id=data_id, test_record_id=test_id).first_or_404()
    return Response(
        data.get_data(),
        mimetype=data.mime_type or 'application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename="{data.original_filename}"'}
    )


@fcgr_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate test report."""
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
                'specimen_id': test.specimen_id or '',
                'material': test.material or '',
                'certificate_number': form.certificate_number.data or '',
                'test_date': test.test_date.strftime('%Y-%m-%d') if test.test_date else '',
                'requirement': cert.requirement if cert else '',
            }

            # Prepare specimen data
            specimen_data = {
                'specimen_type': geometry.get('type', 'C(T)'),
                'W': geometry.get('W', ''),
                'B': geometry.get('B', ''),
                'B_n': geometry.get('B_n', ''),
                'a_0': geometry.get('a_0', ''),
                'notch_height': geometry.get('notch_height', 0),
            }

            # Prepare material data
            material_data = {
                'yield_strength': geometry.get('yield_strength', ''),
                'ultimate_strength': geometry.get('ultimate_strength', ''),
                'youngs_modulus': geometry.get('youngs_modulus', ''),
                'poissons_ratio': geometry.get('poissons_ratio', 0.3),
            }

            # Prepare test parameters
            test_params = {
                'control_mode': geometry.get('control_mode', 'Load Control'),
                'load_ratio': geometry.get('load_ratio', 0.1),
                'frequency': geometry.get('frequency', 10),
                'temperature': test.temperature or 23,
                'wave_shape': geometry.get('wave_shape', 'Sine'),
                'environment': 'Laboratory Air',
                'dadn_method': geometry.get('dadn_method', 'Secant'),
                'outlier_threshold': geometry.get('outlier_threshold', 2.5),
            }

            # Create mock results object for report
            class MockParis:
                def __init__(self, C, m, r2, n, dK_range, dadN_range, C_err, m_err):
                    self.C = C
                    self.m = m
                    self.r_squared = r2
                    self.n_points = n
                    self.delta_K_range = dK_range
                    self.da_dN_range = dadN_range
                    self.std_error_C = C_err
                    self.std_error_m = m_err

            class MockResults:
                def __init__(self):
                    self.paris_law = None
                    self.paris_law_initial = None
                    self.n_valid_points = 0
                    self.n_outliers = 0
                    self.total_cycles = 0
                    self.final_crack_length = 0
                    self.threshold_delta_K = 0
                    self.is_valid = True
                    self.validity_notes = []

            mock_results = MockResults()

            paris_C = results.get('paris_C')
            paris_m = results.get('paris_m')
            r_squared = results.get('r_squared')
            n_points = results.get('n_points')
            dK_min = results.get('delta_K_min')
            dK_max = results.get('delta_K_max')
            final_crack = results.get('final_crack')
            total_cycles = results.get('total_cycles')

            if paris_C and paris_m:
                mock_results.paris_law = MockParis(
                    paris_C.value, paris_m.value,
                    r_squared.value if r_squared else 0,
                    int(n_points.value) if n_points else 0,
                    (dK_min.value if dK_min else 0, dK_max.value if dK_max else 0),
                    (1e-7, 1e-3),
                    paris_C.uncertainty, paris_m.uncertainty
                )
            mock_results.n_valid_points = int(n_points.value) if n_points else 0
            mock_results.n_outliers = sum(geometry.get('outlier_mask', []))
            mock_results.total_cycles = int(total_cycles.value) if total_cycles else 0
            mock_results.final_crack_length = final_crack.value if final_crack else 0
            mock_results.is_valid = geometry.get('is_valid', False)
            mock_results.validity_notes = geometry.get('validity_notes', [])

            # Prepare report data
            report_data = FCGRReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                material_data=material_data,
                test_params=test_params,
                results=mock_results
            )

            # Get template and logo paths
            # Skip template - use from-scratch generation for better plot layout
            template_path = None
            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'
            current_app.logger.info('FCGR: Using from-scratch report generation')

            # Generate plots for report
            plot1_path = None
            plot2_path = None

            # Raw data for crack length plot (all points)
            raw_cycles = geometry.get('raw_cycles', geometry.get('cycles', []))
            raw_crack_lengths = geometry.get('raw_crack_lengths', geometry.get('crack_lengths', []))
            # Processed data for Paris law plot
            delta_K = np.array(geometry.get('delta_K', []))
            da_dN = np.array(geometry.get('da_dN', []))
            outlier_mask = np.array(geometry.get('outlier_mask', []))

            if len(raw_cycles) > 0:
                # Crack length plot - darkred (larger figure for full-width report)
                fig1, ax1 = plt.subplots(figsize=(8, 5))
                ax1.plot(raw_cycles, raw_crack_lengths, color='darkred', linewidth=1.5, marker='o', markersize=3,
                        label='Crack Length, a (mm)')
                ax1.set_xlabel('Cycles (N)')
                ax1.set_ylabel('Crack Length, a (mm)')
                ax1.set_title(f'Crack Growth - {test.specimen_id}')

                # Start both axes at 0
                ax1.set_xlim(left=0)
                ax1.set_ylim(bottom=0)

                # Y-axis with 1 mm steps
                ax1.yaxis.set_major_locator(plt.MultipleLocator(1))

                ax1.legend(fontsize=7, loc='upper left')
                ax1.grid(True, alpha=0.3)
                plot1_path = Path(current_app.config['UPLOAD_FOLDER']) / f'fcgr_plot1_{test_id}.png'
                fig1.savefig(plot1_path, dpi=150, bbox_inches='tight')
                plt.close(fig1)

            if len(delta_K) > 0 and paris_C:
                # Paris law plot (larger figure for full-width report)
                fig2, ax2 = plt.subplots(figsize=(8, 5))

                valid_mask = ~outlier_mask
                # Valid data - darkred circles
                ax2.loglog(delta_K[valid_mask], da_dN[valid_mask], 'o', color='darkred',
                          markersize=4, label='Valid Data')
                # Outliers - grey x markers
                if np.any(outlier_mask):
                    ax2.loglog(delta_K[outlier_mask], da_dN[outlier_mask], 'x', color='grey',
                              markersize=5, label='Outliers')

                # Initial regression line (all data) - grey dotted
                paris_init_C = geometry.get('paris_initial_C')
                paris_init_m = geometry.get('paris_initial_m')
                paris_init_dK_min = geometry.get('paris_initial_dK_min')
                paris_init_dK_max = geometry.get('paris_initial_dK_max')
                if paris_init_C and paris_init_m:
                    dK_fit_init = np.logspace(np.log10(paris_init_dK_min * 0.9), np.log10(paris_init_dK_max * 1.1), 100)
                    dadN_fit_init = paris_init_C * dK_fit_init ** paris_init_m
                    ax2.loglog(dK_fit_init, dadN_fit_init, ':', color='grey', linewidth=1,
                              label=f'Initial: C={paris_init_C:.2e}, m={paris_init_m:.2f}')

                # Final regression line (without outliers) - black solid
                dK_fit = np.logspace(np.log10(dK_min.value * 0.9), np.log10(dK_max.value * 1.1), 100)
                dadN_fit = paris_C.value * dK_fit ** paris_m.value
                ax2.loglog(dK_fit, dadN_fit, '-', color='black', linewidth=2,
                          label=f'Final: C={paris_C.value:.2e}, m={paris_m.value:.2f}')

                ax2.set_xlabel('ΔK (MPa√m)')
                ax2.set_ylabel('da/dN (mm/cycle)')
                ax2.set_title(f'Paris Law - {test.specimen_id}')
                ax2.legend(fontsize=6, loc='lower right')
                ax2.grid(True, alpha=0.3, which='both')
                plot2_path = Path(current_app.config['UPLOAD_FOLDER']) / f'fcgr_plot2_{test_id}.png'
                fig2.savefig(plot2_path, dpi=150, bbox_inches='tight')
                plt.close(fig2)

            # Build photo paths from geometry
            photo_paths = []
            for photo in geometry.get('photos', []):
                photo_path = Path(current_app.root_path) / 'static' / 'uploads' / photo['filename']
                if photo_path.exists():
                    photo_paths.append(photo_path)

            # Generate report
            reports_folder = Path(current_app.root_path).parent / 'reports'
            reports_folder.mkdir(exist_ok=True)

            report_filename = f"FCGR_Report_{test.specimen_id or test.test_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            output_path = reports_folder / report_filename

            generator = FCGRReportGenerator(template_path)
            generator.generate_report(
                output_path=output_path,
                data=report_data,
                plot1_path=plot1_path,
                plot2_path=plot2_path,
                logo_path=logo_path if logo_path.exists() else None,
                photo_paths=photo_paths if photo_paths else None
            )

            # Clean up plot temp files
            if plot1_path and plot1_path.exists():
                os.remove(plot1_path)
            if plot2_path and plot2_path.exists():
                os.remove(plot2_path)

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
            return redirect(url_for('fcgr.view', test_id=test_id))

    return render_template('fcgr/report.html', test=test, form=form)


@fcgr_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a test record (admin only)."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('fcgr.index'))

    test = TestRecord.query.get_or_404(test_id)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        table_name='test_records',
        record_id=test_id,
        old_values={'test_id': test.test_id, 'specimen_id': test.specimen_id},
        ip_address=request.remote_addr
    )
    db.session.add(audit)

    # Delete results first
    AnalysisResult.query.filter_by(test_record_id=test_id).delete()
    db.session.delete(test)
    db.session.commit()

    flash(f'Test {test.test_id} deleted.', 'success')
    return redirect(url_for('fcgr.index'))
