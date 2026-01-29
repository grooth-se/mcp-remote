"""FCGR (Fatigue Crack Growth Rate) test routes - ASTM E647."""
import os
from pathlib import Path
from datetime import datetime

from flask import (render_template, redirect, url_for, flash, request,
                   current_app, send_file)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from . import fcgr_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import analysis utilities
from utils.analysis.fcgr_calculations import FCGRAnalyzer
from utils.models.fcgr_specimen import (
    FCGRSpecimen, FCGRMaterial, FCGRTestParameters, FCGRResult
)
from utils.data_acquisition.fcgr_excel_parser import parse_fcgr_excel
from utils.data_acquisition.fcgr_csv_parser import (
    parse_fcgr_csv, extract_cycle_extrema, calculate_compliance_per_cycle
)
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
        name='Crack Length',
        marker=dict(size=4, color='darkred'),
        line=dict(width=1.5, color='darkred')
    ))

    fig.update_layout(
        title=f'Crack Length vs Cycles - {specimen_id}',
        xaxis_title='Cycles (N)',
        yaxis_title='Crack Length, a (mm)',
        template='plotly_white',
        height=400,
        showlegend=False
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

    # Plot initial regression line (all data) - thin grey dashed
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
            name=f'Initial Fit (all data)',
            line=dict(width=1, color='grey', dash='dash')
        ))

    fig.update_layout(
        title=f'Paris Law Plot - {specimen_id}',
        xaxis_title='ΔK (MPa√m)',
        yaxis_title='da/dN (mm/cycle)',
        xaxis_type='log',
        yaxis_type='log',
        template='plotly_white',
        height=450,
        legend=dict(yanchor="bottom", y=0.01, xanchor="left", x=0.01)
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
    """Create new FCGR test."""
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
            # ============================================================
            # STEP 1: Parse Excel file first (primary data source)
            # ============================================================
            excel_data = None
            if form.excel_file.data:
                excel_file = form.excel_file.data
                filename = secure_filename(excel_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                excel_file.save(filepath)
                excel_data = parse_fcgr_excel(filepath)
                flash(f'Excel data imported: Specimen {excel_data.specimen_id}, W={excel_data.W}mm, B={excel_data.B}mm', 'info')

            # ============================================================
            # STEP 2: Parse CSV file for raw test data
            # ============================================================
            csv_data = None
            cycles = None
            crack_lengths = None
            P_max = None
            P_min = None

            if form.csv_file.data:
                csv_file = form.csv_file.data
                filename = secure_filename(csv_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                csv_file.save(filepath)
                csv_data = parse_fcgr_csv(filepath)

                # Extract cycle extrema (P_max, P_min per cycle)
                cycle_nums, P_max_arr, P_min_arr, COD_max, COD_min = extract_cycle_extrema(csv_data)

                # Calculate compliance per cycle
                _, compliance_arr = calculate_compliance_per_cycle(csv_data)

                cycles = cycle_nums.astype(float)
                P_max = P_max_arr
                P_min = P_min_arr

            # ============================================================
            # STEP 3: Extract values - Excel takes precedence over form
            # ============================================================

            # Specimen identification - Excel first, then form
            if excel_data and excel_data.specimen_id:
                specimen_id = excel_data.specimen_id
            else:
                specimen_id = form.specimen_id.data or ''

            # Specimen type - Excel first, then form
            if excel_data and excel_data.specimen_type:
                specimen_type = excel_data.specimen_type
            else:
                specimen_type = form.specimen_type.data or 'C(T)'

            # Specimen dimensions - Excel takes precedence
            if excel_data and excel_data.W > 0:
                W = excel_data.W
            else:
                W = form.W.data or 50.0

            if excel_data and excel_data.B > 0:
                B = excel_data.B
            else:
                B = form.B.data or 12.5

            if excel_data and excel_data.B_n > 0:
                B_n = excel_data.B_n
            else:
                B_n = form.B_n.data or B

            if excel_data and excel_data.a_0 > 0:
                a_0 = excel_data.a_0
            else:
                a_0 = form.a_0.data or 10.0

            if excel_data and excel_data.notch_height > 0:
                notch_height = excel_data.notch_height
            else:
                notch_height = form.notch_height.data or 0.0

            # Material properties - Excel takes precedence
            if excel_data and excel_data.yield_strength > 0:
                yield_strength = excel_data.yield_strength
            else:
                yield_strength = form.yield_strength.data or 0.0

            if excel_data and excel_data.ultimate_strength > 0:
                ultimate_strength = excel_data.ultimate_strength
            else:
                ultimate_strength = form.ultimate_strength.data or 0.0

            if excel_data and excel_data.youngs_modulus > 0:
                youngs_modulus = excel_data.youngs_modulus
            else:
                youngs_modulus = form.youngs_modulus.data or 210.0

            if excel_data and excel_data.poissons_ratio > 0:
                poissons_ratio = excel_data.poissons_ratio
            else:
                poissons_ratio = form.poissons_ratio.data or 0.3

            # Test parameters - Excel takes precedence
            if excel_data and excel_data.control_mode:
                control_mode = excel_data.control_mode
            else:
                control_mode = form.control_mode.data or 'Load Control'

            if excel_data and excel_data.load_ratio is not None:
                load_ratio = excel_data.load_ratio
            elif form.load_ratio.data is not None:
                load_ratio = form.load_ratio.data
            else:
                load_ratio = 0.1

            if excel_data and excel_data.frequency > 0:
                frequency = excel_data.frequency
            else:
                frequency = form.frequency.data or 10.0

            if excel_data and excel_data.wave_shape:
                wave_shape = excel_data.wave_shape
            else:
                wave_shape = form.wave_shape.data or 'Sine'

            if excel_data and excel_data.test_temperature != 23.0:
                test_temperature = excel_data.test_temperature
            elif form.test_temperature.data is not None:
                test_temperature = form.test_temperature.data
            else:
                test_temperature = 23.0

            # Material name - form takes precedence (user may want to specify)
            material_name = form.material.data or ''

            # Log extracted values
            current_app.logger.info(f'FCGR Analysis - Specimen: {specimen_id}, W={W}, B={B}, a_0={a_0}')
            current_app.logger.info(f'FCGR Analysis - Material: yield={yield_strength} MPa, E={youngs_modulus} GPa')
            current_app.logger.info(f'FCGR Analysis - Test params: R={load_ratio}, f={frequency} Hz')

            # ============================================================
            # STEP 3b: Validate required values after Excel/form merge
            # ============================================================
            validation_errors = []
            if not W or W <= 0:
                validation_errors.append('Width (W) is required')
            if not B or B <= 0:
                validation_errors.append('Thickness (B) is required')
            if not a_0 or a_0 <= 0:
                validation_errors.append('Initial notch length (a₀) is required')
            if not youngs_modulus or youngs_modulus <= 0:
                validation_errors.append("Young's modulus (E) is required")

            if validation_errors:
                for error in validation_errors:
                    flash(f'{error}. Please provide in form or upload Excel file with this data.', 'danger')
                return render_template('fcgr/new.html', form=form, certificate=certificate)

            # ============================================================
            # STEP 4: Create analysis objects and run analysis
            # ============================================================

            # Create specimen object
            specimen = FCGRSpecimen(
                specimen_id=specimen_id,
                specimen_type=specimen_type,
                W=W,
                B=B,
                B_n=B_n,
                a_0=a_0,
                notch_height=notch_height,
                material=material_name
            )

            # Create material object
            material = FCGRMaterial(
                yield_strength=yield_strength,
                ultimate_strength=ultimate_strength,
                youngs_modulus=youngs_modulus,
                poissons_ratio=poissons_ratio
            )

            # Create test parameters
            test_params = FCGRTestParameters(
                control_mode=control_mode,
                load_ratio=load_ratio,
                frequency=frequency,
                wave_shape=wave_shape,
                environment=form.environment.data or 'Laboratory Air',
                temperature=test_temperature
            )

            # Run analysis
            analyzer = FCGRAnalyzer(specimen, material, test_params)

            if csv_data and cycles is not None:
                # Calculate crack lengths from compliance
                crack_lengths = np.array([
                    analyzer.crack_length_from_compliance(c) for c in compliance_arr
                ])

                # Use raw data from CSV
                results = analyzer.analyze_from_raw_data(
                    cycles=cycles,
                    crack_lengths=crack_lengths,
                    P_max=P_max,
                    P_min=P_min,
                    method=form.dadn_method.data,
                    outlier_percentage=form.outlier_threshold.data or 30.0
                )
            elif excel_data:
                # Use MTS analysis data
                # Create synthetic data from Excel results for now
                flash('Excel-only analysis not fully implemented. Please also upload CSV data.', 'warning')
                return render_template('fcgr/new.html', form=form, certificate=certificate)
            else:
                flash('Please upload test data (CSV or Excel file).', 'danger')
                return render_template('fcgr/new.html', form=form, certificate=certificate)

            # Store geometry and parameters in JSON
            # Ensure all values are JSON serializable (convert numpy types to Python)
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
                'outlier_threshold': float(form.outlier_threshold.data or 30.0),
                # Store precrack measurements from Excel if available
                'precrack_measurements': excel_data.precrack_measurements if excel_data else [],
                'precrack_final_size': float(excel_data.precrack_final_size) if excel_data else 0.0,
                # Store data arrays for plotting
                'cycles': [float(p.cycle_count) for p in results.data_points],
                'crack_lengths': [float(p.crack_length) for p in results.data_points],
                'delta_K': [float(p.delta_K) for p in results.data_points],
                'da_dN': [float(p.da_dN) for p in results.data_points],
                'outlier_mask': [bool(p.is_outlier) for p in results.data_points],
            }

            # Create test record
            test_id = generate_test_id()

            # Get certificate from form selection
            selected_cert_id = form.certificate_id.data if form.certificate_id.data and form.certificate_id.data > 0 else None
            selected_cert = Certificate.query.get(selected_cert_id) if selected_cert_id else None
            cert_number = selected_cert.certificate_number_with_rev if selected_cert else None

            test_record = TestRecord(
                test_id=test_id,
                test_method='FCGR',
                test_standard=form.test_standard.data,
                specimen_id=specimen_id,
                material=form.material.data or (excel_data.material if excel_data else ''),
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

            # Store results (ensure all values are Python floats)
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
                result = AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name=name,
                    value=value,
                    uncertainty=uncertainty,
                    unit=unit,
                    calculated_by_id=current_user.id
                )
                db.session.add(result)

            # Store validity in geometry
            geometry['is_valid'] = results.is_valid
            geometry['validity_notes'] = results.validity_notes
            test_record.geometry = geometry  # Update with validity info

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
                flash(f'Warning: Test validity issues detected.', 'warning')

            return redirect(url_for('fcgr.view', test_id=test_record.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Analysis error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('fcgr/new.html', form=form, certificate=certificate)


@fcgr_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View test results."""
    test = TestRecord.query.get_or_404(test_id)
    results = {r.parameter_name: r for r in test.results.all()}
    geometry = test.geometry or {}

    # Get data arrays for plotting
    cycles = geometry.get('cycles', [])
    crack_lengths = geometry.get('crack_lengths', [])
    delta_K = np.array(geometry.get('delta_K', []))
    da_dN = np.array(geometry.get('da_dN', []))
    outlier_mask = np.array(geometry.get('outlier_mask', []))

    # Create plots
    crack_plot = None
    paris_plot = None

    if len(cycles) > 0:
        crack_plot = create_crack_length_plot(cycles, crack_lengths, test.specimen_id)

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
            paris_plot = create_paris_law_plot(
                delta_K, da_dN, paris_result, None, outlier_mask, test.specimen_id
            )

    return render_template('fcgr/view.html', test=test, results=results,
                          geometry=geometry, crack_plot=crack_plot, paris_plot=paris_plot)


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
                'outlier_threshold': geometry.get('outlier_threshold', 30),
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
            template_path = Path(current_app.root_path).parent / 'templates' / 'fcgr_e647_report_template.docx'
            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'

            # Template is optional - will fall back to from-scratch generation
            if not template_path.exists():
                template_path = None
                current_app.logger.info('FCGR template not found, using from-scratch generation')

            # Generate plots for report
            plot1_path = None
            plot2_path = None

            cycles = geometry.get('cycles', [])
            crack_lengths = geometry.get('crack_lengths', [])
            delta_K = np.array(geometry.get('delta_K', []))
            da_dN = np.array(geometry.get('da_dN', []))
            outlier_mask = np.array(geometry.get('outlier_mask', []))

            if len(cycles) > 0:
                # Crack length plot - darkred
                fig1, ax1 = plt.subplots(figsize=(5, 3.5))
                ax1.plot(cycles, crack_lengths, color='darkred', linewidth=1.5, marker='o', markersize=3)
                ax1.set_xlabel('Cycles (N)')
                ax1.set_ylabel('Crack Length, a (mm)')
                ax1.set_title(f'Crack Growth - {test.specimen_id}')
                ax1.grid(True, alpha=0.3)
                plot1_path = Path(current_app.config['UPLOAD_FOLDER']) / f'fcgr_plot1_{test_id}.png'
                fig1.savefig(plot1_path, dpi=150, bbox_inches='tight')
                plt.close(fig1)

            if len(delta_K) > 0 and paris_C:
                # Paris law plot
                fig2, ax2 = plt.subplots(figsize=(5, 3.5))

                valid_mask = ~outlier_mask
                # Valid data - darkred circles
                ax2.loglog(delta_K[valid_mask], da_dN[valid_mask], 'o', color='darkred',
                          markersize=4, label='Valid Data')
                # Outliers - grey x markers
                if np.any(outlier_mask):
                    ax2.loglog(delta_K[outlier_mask], da_dN[outlier_mask], 'x', color='grey',
                              markersize=5, label='Outliers')

                # Regression line - black
                dK_fit = np.logspace(np.log10(dK_min.value * 0.9), np.log10(dK_max.value * 1.1), 100)
                dadN_fit = paris_C.value * dK_fit ** paris_m.value
                ax2.loglog(dK_fit, dadN_fit, '-', color='black', linewidth=2,
                          label=f'C={paris_C.value:.2e}, m={paris_m.value:.2f}')

                ax2.set_xlabel('ΔK (MPa√m)')
                ax2.set_ylabel('da/dN (mm/cycle)')
                ax2.set_title(f'Paris Law - {test.specimen_id}')
                ax2.legend(fontsize=8)
                ax2.grid(True, alpha=0.3, which='both')
                plot2_path = Path(current_app.config['UPLOAD_FOLDER']) / f'fcgr_plot2_{test_id}.png'
                fig2.savefig(plot2_path, dpi=150, bbox_inches='tight')
                plt.close(fig2)

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
                logo_path=logo_path if logo_path.exists() else None
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
