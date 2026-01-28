"""Routes for KIC (Fracture Toughness) test module - ASTM E399."""
import os
import json
from datetime import datetime
from pathlib import Path

from flask import (
    render_template, redirect, url_for, flash, request,
    current_app, send_file
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from . import kic_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import calculation utilities
from utils.data_acquisition.kic_csv_parser import parse_kic_csv, KICTestData
from utils.data_acquisition.kic_excel_parser import parse_kic_excel
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

    # Main force-displacement curve
    fig.add_trace(go.Scatter(
        x=list(displacement),
        y=list(force),
        mode='lines',
        name='Force vs Displacement',
        line=dict(color='blue', width=2)
    ))

    # Add 5% secant offset line if available
    if secant_line:
        fig.add_trace(go.Scatter(
            x=secant_line['x'],
            y=secant_line['y'],
            mode='lines',
            name='5% Secant Offset',
            line=dict(color='red', width=1.5, dash='dash')
        ))

    # Mark PQ point
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
            marker=dict(color='red', size=12, symbol='diamond')
        ))

    # Mark Pmax point
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
            marker=dict(color='green', size=12, symbol='star')
        ))

    fig.update_layout(
        title='Force vs Displacement (ASTM E399)',
        xaxis_title='Displacement (mm)',
        yaxis_title='Force (kN)',
        template='plotly_white',
        showlegend=True,
        legend=dict(yanchor='top', y=0.99, xanchor='left', x=0.01),
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


@kic_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create a new KIC test."""
    form = SpecimenForm()

    # Populate certificate dropdown
    certificates = Certificate.query.order_by(
        Certificate.year.desc(),
        Certificate.cert_id.desc()
    ).all()
    form.certificate_id.choices = [(0, '-- Select Certificate --')] + [
        (c.id, f"{c.certificate_number_with_rev} - {c.customer or 'No customer'}")
        for c in certificates
    ]

    # Check if coming from certificate page
    cert_id = request.args.get('certificate', type=int)
    if cert_id and request.method == 'GET':
        form.certificate_id.data = cert_id
        cert = Certificate.query.get(cert_id)
        if cert:
            # Pre-fill form from certificate data
            form.material.data = cert.material
            form.specimen_id.data = cert.specimen_id
            form.temperature.data = float(cert.temperature) if cert.temperature else 23.0
            form.location_orientation.data = cert.location_orientation

    if form.validate_on_submit():
        try:
            # ============================================================
            # STEP 1: Parse Excel file first (primary data source)
            # ============================================================
            excel_data = None
            raw_data = {}

            if form.excel_file.data:
                excel_file = form.excel_file.data
                filename = secure_filename(excel_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                excel_file.save(filepath)

                try:
                    excel_data = parse_kic_excel(filepath)
                    raw_data['excel_file'] = filename
                    raw_data['mts_results'] = excel_data.kic_results
                    current_app.logger.info(f'KIC Excel import: Specimen {excel_data.specimen_id}, W={excel_data.W}, B={excel_data.B}')
                    flash(f'Excel data imported: Specimen {excel_data.specimen_id}, W={excel_data.W}mm, B={excel_data.B}mm', 'info')
                except Exception as e:
                    current_app.logger.warning(f'Error parsing Excel: {e}')
                    flash(f'Error parsing Excel: {e}', 'warning')

            # ============================================================
            # STEP 2: Parse CSV file for raw force-displacement data
            # ============================================================
            if form.csv_file.data:
                csv_file = form.csv_file.data
                filename = secure_filename(csv_file.filename)
                filepath = Path(current_app.config['UPLOAD_FOLDER']) / filename
                csv_file.save(filepath)

                try:
                    test_data = parse_kic_csv(filepath)
                    raw_data['force'] = test_data.force.tolist()
                    raw_data['displacement'] = test_data.displacement.tolist()
                    raw_data['time'] = test_data.time.tolist()
                    raw_data['csv_file'] = filename
                    flash('CSV data imported successfully.', 'success')
                except Exception as e:
                    current_app.logger.warning(f'Error parsing CSV: {e}')
                    flash(f'Error parsing CSV: {e}', 'warning')

            # ============================================================
            # STEP 3: Extract values - Excel takes precedence over form
            # ============================================================

            # Specimen identification - Excel first, then form
            if excel_data and excel_data.specimen_id:
                specimen_id = excel_data.specimen_id
            else:
                specimen_id = form.specimen_id.data or ''

            # Specimen type
            if excel_data and excel_data.specimen_type:
                specimen_type = excel_data.specimen_type
            else:
                specimen_type = form.specimen_type.data or 'SE(B)'

            # Specimen dimensions - Excel takes precedence
            if excel_data and excel_data.W > 0:
                W = excel_data.W
            else:
                W = form.W.data or 25.0

            if excel_data and excel_data.B > 0:
                B = excel_data.B
            else:
                B = form.B.data or 12.0

            if excel_data and excel_data.B_n > 0:
                B_n = excel_data.B_n
            else:
                B_n = form.B_n.data or B

            if excel_data and excel_data.a_0 > 0:
                a_0 = excel_data.a_0
            else:
                a_0 = form.a_0.data or 12.5

            if excel_data and excel_data.S > 0:
                S = excel_data.S
            else:
                S = form.S.data if specimen_type == 'SE(B)' else None

            # Crack measurements - Excel first
            crack_measurements = []
            if excel_data and excel_data.precrack_measurements:
                crack_measurements = excel_data.precrack_measurements
            else:
                # Collect from form
                for i in range(1, 6):
                    val = getattr(form, f'crack_{i}').data
                    if val is not None and val > 0:
                        crack_measurements.append(val)

            # Precrack final size
            precrack_final_size = None
            if excel_data and excel_data.precrack_final_size > 0:
                precrack_final_size = excel_data.precrack_final_size

            # Material properties - Excel takes precedence
            if excel_data and excel_data.yield_strength > 0:
                yield_strength = excel_data.yield_strength
            else:
                yield_strength = form.yield_strength.data or 500.0

            if excel_data and excel_data.ultimate_strength > 0:
                ultimate_strength = excel_data.ultimate_strength
            else:
                ultimate_strength = form.ultimate_strength.data

            if excel_data and excel_data.youngs_modulus > 0:
                youngs_modulus = excel_data.youngs_modulus
            else:
                youngs_modulus = form.youngs_modulus.data or 210.0

            if excel_data and excel_data.poissons_ratio > 0:
                poissons_ratio = excel_data.poissons_ratio
            else:
                poissons_ratio = form.poissons_ratio.data or 0.3

            # Temperature - Excel first
            if excel_data and excel_data.test_temperature != 23.0:
                temperature = excel_data.test_temperature
            else:
                temperature = form.temperature.data if form.temperature.data else 23.0

            # Log extracted values
            current_app.logger.info(f'KIC Analysis - Specimen: {specimen_id}, W={W}, B={B}, a_0={a_0}')
            current_app.logger.info(f'KIC Analysis - Material: yield={yield_strength} MPa, E={youngs_modulus} GPa')
            if crack_measurements:
                current_app.logger.info(f'KIC Analysis - Crack measurements: {crack_measurements}')

            # ============================================================
            # STEP 4: Build data structures and create test record
            # ============================================================

            # Link to certificate if selected
            certificate_id = None
            cert_number = None
            if form.certificate_id.data and form.certificate_id.data != 0:
                cert = Certificate.query.get(form.certificate_id.data)
                if cert:
                    certificate_id = cert.id
                    cert_number = cert.certificate_number_with_rev

            # Build specimen geometry dictionary
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
            if precrack_final_size:
                specimen_geometry['precrack_final_size'] = precrack_final_size

            # Build material properties dictionary
            material_props = {
                'yield_strength': yield_strength,
                'ultimate_strength': ultimate_strength,
                'youngs_modulus': youngs_modulus,
                'poissons_ratio': poissons_ratio,
            }

            # Build complete geometry dict (stores all structured data)
            geometry_data = {
                'specimen_geometry': specimen_geometry,
                'material_properties': material_props,
                'location_orientation': form.location_orientation.data,
                'notes': form.notes.data,
                'raw_data': raw_data,
            }

            # Create test record
            test = TestRecord(
                test_id=form.test_id.data,
                test_method='KIC',
                specimen_id=specimen_id,
                material=form.material.data,
                test_date=form.test_date.data or datetime.now().date(),
                temperature=temperature,
                geometry=geometry_data,
                status='DRAFT',
                certificate_id=certificate_id,
                certificate_number=cert_number,
                operator_id=current_user.id
            )

            # Add test to session and flush to get ID before creating analysis records
            db.session.add(test)
            db.session.flush()

            # Run analysis if we have force-displacement data
            if 'force' in raw_data and 'displacement' in raw_data:
                # Create specimen and material objects
                specimen = KICSpecimen(
                    specimen_id=specimen_id,
                    specimen_type=specimen_geometry['type'],
                    W=specimen_geometry['W'],
                    B=specimen_geometry['B'],
                    B_n=specimen_geometry.get('B_n', specimen_geometry['B']),
                    a_0=specimen_geometry['a_0'],
                    S=specimen_geometry.get('S') or 0.0
                )

                material = KICMaterial(
                    yield_strength=material_props['yield_strength'],
                    youngs_modulus=material_props['youngs_modulus'],
                    poissons_ratio=material_props.get('poissons_ratio', 0.3)
                )

                import numpy as np
                force = np.array(raw_data['force'])
                displacement = np.array(raw_data['displacement'])

                # Run KIC analysis
                analyzer = KICAnalyzer()
                result = analyzer.run_analysis(force, displacement, specimen, material)

                # Store results as individual AnalysisResult records
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

                test.status = 'ANALYZED'
                flash('KIC analysis completed.', 'success')

            # Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action='CREATE',
                table_name='test_record',
                record_id=test.id,
                new_values=json.dumps({'test_id': test.test_id, 'test_method': 'KIC'})
            )
            db.session.add(audit)
            db.session.commit()

            flash(f'KIC test {test.test_id} created.', 'success')
            return redirect(url_for('kic.view', test_id=test.id))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error creating KIC test: {e}')
            flash(f'Error creating test: {e}', 'error')

    return render_template('kic/new.html', form=form)


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

    return render_template('kic/view.html',
                           test=test,
                           geometry=geometry,
                           material_props=material_props,
                           results=results,
                           force_disp_plot=force_disp_plot)


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

                ax.plot(displacement, force, 'b-', linewidth=1.5, label='Force vs Displacement')

                # Mark PQ
                P_Q_data = results.get('P_Q')
                if P_Q_data and isinstance(P_Q_data, dict):
                    P_Q = P_Q_data.get('value')
                    if P_Q:
                        idx = np.argmin(np.abs(force - P_Q))
                        ax.plot(displacement[idx], P_Q, 'rd', markersize=10, label=f'PQ = {P_Q:.2f} kN')

                # Mark Pmax
                P_max_data = results.get('P_max')
                if P_max_data and isinstance(P_max_data, dict):
                    P_max = P_max_data.get('value')
                    if P_max:
                        idx = np.argmax(force)
                        ax.plot(displacement[idx], P_max, 'g*', markersize=12, label=f'Pmax = {P_max:.2f} kN')

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
