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
        marker=dict(size=4, color='#0d6efd'),
        line=dict(width=1.5, color='#0d6efd')
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

    # Plot valid data points
    fig.add_trace(go.Scatter(
        x=dK_valid,
        y=dadN_valid,
        mode='markers',
        name='Valid Data',
        marker=dict(size=6, color='#0d6efd', symbol='circle')
    ))

    # Plot outliers
    if len(dK_outlier) > 0:
        fig.add_trace(go.Scatter(
            x=dK_outlier,
            y=dadN_outlier,
            mode='markers',
            name='Outliers',
            marker=dict(size=6, color='#dc3545', symbol='x')
        ))

    # Plot Paris law regression line (final - without outliers)
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
            line=dict(width=2, color='#198754')
        ))

    # Plot initial regression line (all data) as dashed
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
            line=dict(width=1.5, color='#6c757d', dash='dash')
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

    # Pre-fill from certificate
    if request.method == 'GET' and certificate:
        if certificate.material:
            form.material.data = certificate.material
        if certificate.specimen_id:
            form.specimen_id.data = certificate.specimen_id
        if certificate.batch_number:
            form.batch_number.data = certificate.batch_number

    if form.validate_on_submit():
        try:
            # Check if Excel file uploaded - parse for specimen data
            excel_data = None
            if form.excel_file.data:
                excel_file = form.excel_file.data
                filename = secure_filename(excel_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                excel_file.save(filepath)
                excel_data = parse_fcgr_excel(filepath)

                # Override form data with Excel data if available
                if excel_data.specimen_id and not form.specimen_id.data:
                    form.specimen_id.data = excel_data.specimen_id

            # Check if CSV file uploaded - parse for raw data
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

            # Create specimen object
            specimen = FCGRSpecimen(
                specimen_id=form.specimen_id.data,
                specimen_type=form.specimen_type.data,
                W=form.W.data,
                B=form.B.data,
                B_n=form.B_n.data or form.B.data,
                a_0=form.a_0.data,
                notch_height=form.notch_height.data or 0.0,
                material=form.material.data or ''
            )

            # Create material object
            material = FCGRMaterial(
                yield_strength=form.yield_strength.data or 0.0,
                ultimate_strength=form.ultimate_strength.data or 0.0,
                youngs_modulus=form.youngs_modulus.data,
                poissons_ratio=form.poissons_ratio.data or 0.3
            )

            # Create test parameters
            test_params = FCGRTestParameters(
                control_mode=form.control_mode.data,
                load_ratio=form.load_ratio.data,
                frequency=form.frequency.data or 10.0,
                wave_shape=form.wave_shape.data,
                environment=form.environment.data or 'Laboratory Air',
                temperature=form.test_temperature.data or 23.0
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
                'type': form.specimen_type.data,
                'W': float(form.W.data),
                'B': float(form.B.data),
                'B_n': float(form.B_n.data or form.B.data),
                'a_0': float(form.a_0.data),
                'notch_height': float(form.notch_height.data or 0.0),
                'yield_strength': float(form.yield_strength.data or 0.0),
                'ultimate_strength': float(form.ultimate_strength.data or 0.0),
                'youngs_modulus': float(form.youngs_modulus.data),
                'poissons_ratio': float(form.poissons_ratio.data or 0.3),
                'load_ratio': float(form.load_ratio.data),
                'frequency': float(form.frequency.data or 10.0),
                'control_mode': form.control_mode.data,
                'wave_shape': form.wave_shape.data,
                'dadn_method': form.dadn_method.data,
                'outlier_threshold': float(form.outlier_threshold.data or 30.0),
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

            if not template_path.exists():
                flash(f'Template not found: {template_path}', 'danger')
                return redirect(url_for('fcgr.view', test_id=test_id))

            # Generate plots for report
            plot1_path = None
            plot2_path = None

            cycles = geometry.get('cycles', [])
            crack_lengths = geometry.get('crack_lengths', [])
            delta_K = np.array(geometry.get('delta_K', []))
            da_dN = np.array(geometry.get('da_dN', []))
            outlier_mask = np.array(geometry.get('outlier_mask', []))

            if len(cycles) > 0:
                # Crack length plot
                fig1, ax1 = plt.subplots(figsize=(5, 3.5))
                ax1.plot(cycles, crack_lengths, 'b-', linewidth=1.5, marker='o', markersize=3)
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
                ax2.loglog(delta_K[valid_mask], da_dN[valid_mask], 'bo', markersize=4, label='Valid Data')
                if np.any(outlier_mask):
                    ax2.loglog(delta_K[outlier_mask], da_dN[outlier_mask], 'rx', markersize=5, label='Outliers')

                # Regression line
                dK_fit = np.logspace(np.log10(dK_min.value * 0.9), np.log10(dK_max.value * 1.1), 100)
                dadN_fit = paris_C.value * dK_fit ** paris_m.value
                ax2.loglog(dK_fit, dadN_fit, 'g-', linewidth=2,
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
