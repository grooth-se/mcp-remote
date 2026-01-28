"""CTOD (Crack Tip Opening Displacement) test routes - ASTM E1290."""
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

from . import ctod_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import analysis utilities
from utils.analysis.ctod_calculations import CTODAnalyzer, CTODResult
from utils.models.ctod_specimen import CTODSpecimen, CTODMaterial
from utils.data_acquisition.ctod_excel_parser import parse_ctod_excel
from utils.data_acquisition.ctod_csv_parser import parse_ctod_test_csv as parse_ctod_csv
from utils.reporting.ctod_word_report import CTODReportGenerator


def generate_test_id():
    """Generate unique test ID."""
    today = datetime.now()
    prefix = f"CTOD-{today.strftime('%y%m%d')}"
    count = TestRecord.query.filter(
        TestRecord.test_id.like(f'{prefix}%')
    ).count()
    return f"{prefix}-{count + 1:03d}"


def create_force_cmod_plot(force, cmod, specimen_id, elastic_coeffs=None, ctod_points=None):
    """Create Force vs CMOD plot with elastic line and CTOD points."""
    fig = go.Figure()

    # Main test data
    fig.add_trace(go.Scatter(
        x=cmod,
        y=force,
        mode='lines',
        name='Test Data',
        line=dict(width=2, color='#0d6efd')
    ))

    # Elastic loading line
    if elastic_coeffs is not None:
        slope, intercept = elastic_coeffs
        cmod_elastic = np.linspace(0, max(cmod) * 0.6, 100)
        force_elastic = (cmod_elastic - intercept) / slope
        force_elastic = np.maximum(force_elastic, 0)

        fig.add_trace(go.Scatter(
            x=cmod_elastic,
            y=force_elastic,
            mode='lines',
            name='Elastic Line',
            line=dict(width=1.5, color='#6c757d', dash='dash')
        ))

    # Mark CTOD points
    if ctod_points:
        markers = {'delta_m': ('Max Force (δm)', '#198754', 'circle'),
                   'delta_c': ('Cleavage (δc)', '#dc3545', 'diamond'),
                   'delta_u': ('Instability (δu)', '#fd7e14', 'square')}

        for key, (label, color, symbol) in markers.items():
            point = ctod_points.get(key)
            if point:
                idx, P, V, delta = point
                fig.add_trace(go.Scatter(
                    x=[V],
                    y=[P],
                    mode='markers',
                    name=f'{label}: δ={delta:.4f} mm',
                    marker=dict(size=12, color=color, symbol=symbol)
                ))

    fig.update_layout(
        title=f'Force vs CMOD - {specimen_id}',
        xaxis_title='CMOD (mm)',
        yaxis_title='Force (kN)',
        template='plotly_white',
        height=450,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )

    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')


@ctod_bp.route('/')
@login_required
def index():
    """List all CTOD tests."""
    tests = TestRecord.query.filter_by(test_method='CTOD').order_by(
        TestRecord.test_date.desc()
    ).all()
    return render_template('ctod/index.html', tests=tests)


@ctod_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new CTOD test."""
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
        if certificate.product_sn:
            form.batch_number.data = certificate.product_sn

    if form.validate_on_submit():
        try:
            # Parse Excel file if uploaded
            excel_data = None
            if form.excel_file.data:
                excel_file = form.excel_file.data
                filename = secure_filename(excel_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                excel_file.save(filepath)
                excel_data = parse_ctod_excel(filepath)

            # Parse CSV file if uploaded
            csv_data = None
            force = None
            cmod = None

            if form.csv_file.data:
                csv_file = form.csv_file.data
                filename = secure_filename(csv_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                csv_file.save(filepath)
                csv_data = parse_ctod_csv(filepath)
                force = csv_data.force
                cmod = csv_data.cod  # COD = CMOD (Crack Mouth Opening Displacement)

            # Get specimen dimensions (prefer form, fallback to Excel)
            W = form.W.data or (excel_data.W if excel_data else 25.0)
            B = form.B.data or (excel_data.B if excel_data else 12.5)
            B_n = form.B_n.data or (excel_data.B_n if excel_data else B)
            a_0 = form.a_0.data or (excel_data.a_0 if excel_data else W * 0.5)
            S = form.S.data or (excel_data.S if excel_data else W * 4)

            # Get 9-point crack measurements
            crack_measurements = []
            for field_name in ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9']:
                val = getattr(form, field_name).data
                if val and val > 0:
                    crack_measurements.append(val)

            if len(crack_measurements) != 9 and excel_data:
                crack_measurements = excel_data.precrack_measurements

            # Calculate average crack length if measurements available
            if len(crack_measurements) == 9:
                a_avg = (0.5 * crack_measurements[0] + sum(crack_measurements[1:8]) +
                        0.5 * crack_measurements[8]) / 8
                a_0 = a_avg

            # Create specimen object
            specimen = CTODSpecimen(
                specimen_id=form.specimen_id.data,
                specimen_type=form.specimen_type.data,
                W=W,
                B=B,
                a_0=a_0,
                S=S,
                B_n=B_n,
                material=form.material.data or ''
            )

            # Get material properties (prefer form, fallback to Excel)
            yield_strength = form.yield_strength.data or (excel_data.yield_strength if excel_data else 500)
            ultimate_strength = form.ultimate_strength.data or (excel_data.ultimate_strength if excel_data else 600)
            youngs_modulus = form.youngs_modulus.data or (excel_data.youngs_modulus if excel_data else 210)
            poissons_ratio = form.poissons_ratio.data or (excel_data.poissons_ratio if excel_data else 0.3)

            material = CTODMaterial(
                yield_strength=yield_strength,
                ultimate_strength=ultimate_strength,
                youngs_modulus=youngs_modulus,
                poissons_ratio=poissons_ratio
            )

            # Run analysis
            if force is None or cmod is None:
                flash('Please upload CSV test data with Force and CMOD columns.', 'danger')
                return render_template('ctod/new.html', form=form, certificate=certificate)

            analyzer = CTODAnalyzer()
            results = analyzer.run_analysis(force, cmod, specimen, material)

            # Store geometry, parameters, and raw data
            # Ensure all values are JSON serializable (convert numpy types to Python)
            geometry = {
                'type': form.specimen_type.data,
                'W': float(W),
                'B': float(B),
                'B_n': float(B_n),
                'a_0': float(a_0),
                'S': float(S),
                'yield_strength': float(yield_strength),
                'ultimate_strength': float(ultimate_strength) if ultimate_strength else None,
                'youngs_modulus': float(youngs_modulus),
                'poissons_ratio': float(poissons_ratio),
                'crack_measurements': [float(x) for x in crack_measurements] if crack_measurements else [],
                'notch_type': form.notch_type.data,
                # Store data for plotting (subsample if large)
                'force': [float(x) for x in force[::max(1, len(force)//500)]],
                'cmod': [float(x) for x in cmod[::max(1, len(cmod)//500)]],
                'elastic_coeffs': [float(np.real(c)) for c in results.get('elastic_coeffs', [0, 0])],
            }

            # Store CTOD points for plotting
            ctod_points = {}
            for ctod_type in ['delta_c', 'delta_u', 'delta_m']:
                ctod_result = results.get(ctod_type)
                if ctod_result:
                    ctod_points[ctod_type] = {
                        'force': float(ctod_result.force.value),
                        'cmod': float(ctod_result.cmod.value),
                        'ctod': float(ctod_result.ctod_value.value)
                    }
            geometry['ctod_points'] = ctod_points

            # Create test record
            test_id = generate_test_id()

            selected_cert_id = form.certificate_id.data if form.certificate_id.data and form.certificate_id.data > 0 else None
            selected_cert = Certificate.query.get(selected_cert_id) if selected_cert_id else None
            cert_number = selected_cert.certificate_number_with_rev if selected_cert else None

            test_record = TestRecord(
                test_id=test_id,
                test_method='CTOD',
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
            # P_max
            P_max = results.get('P_max')
            if P_max:
                db.session.add(AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name='P_max',
                    value=P_max.value,
                    uncertainty=P_max.uncertainty,
                    unit='kN',
                    calculated_by_id=current_user.id
                ))

            # CMOD_max
            CMOD_max = results.get('CMOD_max')
            if CMOD_max:
                db.session.add(AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name='CMOD_max',
                    value=CMOD_max.value,
                    uncertainty=CMOD_max.uncertainty,
                    unit='mm',
                    calculated_by_id=current_user.id
                ))

            # K_max
            K_max = results.get('K_max')
            if K_max:
                db.session.add(AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name='K_max',
                    value=K_max.value,
                    uncertainty=K_max.uncertainty,
                    unit='MPa√m',
                    calculated_by_id=current_user.id
                ))

            # CTOD values
            for ctod_type in ['delta_c', 'delta_u', 'delta_m']:
                ctod_result = results.get(ctod_type)
                if ctod_result:
                    db.session.add(AnalysisResult(
                        test_record_id=test_record.id,
                        parameter_name=ctod_type,
                        value=ctod_result.ctod_value.value,
                        uncertainty=ctod_result.ctod_value.uncertainty,
                        unit='mm',
                        calculated_by_id=current_user.id
                    ))

            # a/W ratio
            a_W = results.get('a_W_ratio')
            if a_W:
                db.session.add(AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name='a_W_ratio',
                    value=a_W.value,
                    uncertainty=a_W.uncertainty,
                    unit='-',
                    calculated_by_id=current_user.id
                ))

            # Compliance
            compliance = results.get('compliance')
            if compliance:
                db.session.add(AnalysisResult(
                    test_record_id=test_record.id,
                    parameter_name='compliance',
                    value=float(compliance),
                    uncertainty=0,
                    unit='mm/kN',
                    calculated_by_id=current_user.id
                ))

            # Store validity info in geometry
            geometry['is_valid'] = results.get('is_valid', False)
            geometry['validity_summary'] = results.get('validity_summary', '')
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
            if not results.get('is_valid', False):
                flash('Warning: Test validity issues detected.', 'warning')

            return redirect(url_for('ctod.view', test_id=test_record.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Analysis error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    return render_template('ctod/new.html', form=form, certificate=certificate)


@ctod_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View test results."""
    test = TestRecord.query.get_or_404(test_id)
    results = {r.parameter_name: r for r in test.results.all()}
    geometry = test.geometry or {}

    # Get data for plotting
    force = np.array(geometry.get('force', []))
    cmod = np.array(geometry.get('cmod', []))
    elastic_coeffs = geometry.get('elastic_coeffs')

    # Reconstruct CTOD points for plot
    ctod_points_raw = geometry.get('ctod_points', {})
    ctod_points = {}
    for key, data in ctod_points_raw.items():
        if data:
            ctod_points[key] = (0, data['force'], data['cmod'], data['ctod'])

    # Create plot
    force_cmod_plot = None
    if len(force) > 0 and len(cmod) > 0:
        force_cmod_plot = create_force_cmod_plot(
            force, cmod, test.specimen_id,
            elastic_coeffs=elastic_coeffs,
            ctod_points=ctod_points
        )

    return render_template('ctod/view.html', test=test, results=results,
                          geometry=geometry, force_cmod_plot=force_cmod_plot)


@ctod_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
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
                'temperature': str(test.temperature) if test.temperature else '23',
            }

            # Prepare specimen data
            specimen_data = {
                'specimen_type': geometry.get('type', 'SE(B)'),
                'W': geometry.get('W', ''),
                'B': geometry.get('B', ''),
                'B_n': geometry.get('B_n', ''),
                'a_0': geometry.get('a_0', ''),
                'S': geometry.get('S', ''),
                'notch_type': geometry.get('notch_type', 'fatigue'),
            }

            # Prepare material data
            material_data = {
                'yield_strength': geometry.get('yield_strength', ''),
                'ultimate_strength': geometry.get('ultimate_strength', ''),
                'youngs_modulus': geometry.get('youngs_modulus', ''),
                'poissons_ratio': geometry.get('poissons_ratio', 0.3),
            }

            # Build results dict with MeasuredValue-like objects
            class MockMeasured:
                def __init__(self, value, uncertainty):
                    self.value = value
                    self.uncertainty = uncertainty

            class MockCTODResult:
                def __init__(self, ctod_val, force_val, cmod_val, is_valid):
                    self.ctod_value = MockMeasured(ctod_val[0], ctod_val[1])
                    self.force = MockMeasured(force_val[0], force_val[1])
                    self.cmod = MockMeasured(cmod_val[0], cmod_val[1])
                    self.is_valid = is_valid

            report_results = {}

            P_max = results.get('P_max')
            if P_max:
                report_results['P_max'] = MockMeasured(P_max.value, P_max.uncertainty)

            CMOD_max = results.get('CMOD_max')
            if CMOD_max:
                report_results['CMOD_max'] = MockMeasured(CMOD_max.value, CMOD_max.uncertainty)

            K_max = results.get('K_max')
            if K_max:
                report_results['K_max'] = MockMeasured(K_max.value, K_max.uncertainty)

            # CTOD results
            ctod_points = geometry.get('ctod_points', {})
            for ctod_type in ['delta_c', 'delta_u', 'delta_m']:
                r = results.get(ctod_type)
                pt = ctod_points.get(ctod_type, {})
                if r and pt:
                    report_results[ctod_type] = MockCTODResult(
                        (r.value, r.uncertainty),
                        (pt.get('force', 0), 0.1),
                        (pt.get('cmod', 0), 0.01),
                        geometry.get('is_valid', False)
                    )

            report_results['compliance'] = results.get('compliance').value if results.get('compliance') else None
            report_results['is_valid'] = geometry.get('is_valid', False)
            report_results['validity_summary'] = geometry.get('validity_summary', '')

            # Prepare report data
            report_data = CTODReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                material_data=material_data,
                results=report_results,
                crack_measurements=geometry.get('crack_measurements', [])
            )

            # Get template and logo paths
            template_path = Path(current_app.root_path).parent / 'templates' / 'ctod_e1290_report_template.docx'
            logo_path = Path(current_app.root_path).parent / 'templates' / 'logo.png'

            if not template_path.exists():
                flash(f'Template not found: {template_path}', 'danger')
                return redirect(url_for('ctod.view', test_id=test_id))

            # Generate chart
            chart_path = None
            force = np.array(geometry.get('force', []))
            cmod = np.array(geometry.get('cmod', []))

            if len(force) > 0 and len(cmod) > 0:
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.plot(cmod, force, 'b-', linewidth=1.5)

                # Mark CTOD points
                for ctod_type, color, marker in [('delta_m', 'g', 'o'), ('delta_c', 'r', 'd'), ('delta_u', 'orange', 's')]:
                    pt = ctod_points.get(ctod_type)
                    if pt:
                        ax.plot(pt['cmod'], pt['force'], marker, color=color, markersize=10,
                               label=f'{ctod_type}: δ={pt["ctod"]:.4f} mm')

                ax.set_xlabel('CMOD (mm)')
                ax.set_ylabel('Force (kN)')
                ax.set_title(f'Force vs CMOD - {test.specimen_id}')
                ax.legend(fontsize=8)
                ax.grid(True, alpha=0.3)

                chart_path = Path(current_app.config['UPLOAD_FOLDER']) / f'ctod_chart_{test_id}.png'
                fig.savefig(chart_path, dpi=150, bbox_inches='tight')
                plt.close(fig)

            # Generate report
            reports_folder = Path(current_app.root_path).parent / 'reports'
            reports_folder.mkdir(exist_ok=True)

            report_filename = f"CTOD_Report_{test.specimen_id or test.test_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            output_path = reports_folder / report_filename

            generator = CTODReportGenerator(template_path)
            generator.generate_report(
                output_path=output_path,
                data=report_data,
                chart_path=chart_path,
                logo_path=logo_path if logo_path.exists() else None
            )

            # Clean up chart
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
            return redirect(url_for('ctod.view', test_id=test_id))

    return render_template('ctod/report.html', test=test, form=form)


@ctod_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a test record (admin only)."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('ctod.index'))

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

    AnalysisResult.query.filter_by(test_record_id=test_id).delete()
    db.session.delete(test)
    db.session.commit()

    flash(f'Test {test.test_id} deleted.', 'success')
    return redirect(url_for('ctod.index'))
