"""Routes for Vickers Hardness test module - ASTM E92 / ISO 6507."""
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

from . import vickers_bp
from .forms import SpecimenForm, ReportForm
from app.extensions import db
from app.models import TestRecord, AnalysisResult, AuditLog, Certificate

# Import calculation utilities
from utils.analysis.vickers_calculations import VickersAnalyzer, VickersResult
from utils.models.vickers_specimen import VickersTestData, VickersReading, VickersLoadLevel


def create_hardness_profile_plot(readings, load_level):
    """Create interactive Hardness Profile plot using Plotly.

    Parameters
    ----------
    readings : list
        List of VickersReading objects or dicts
    load_level : str
        Load level designation (e.g., "HV 10")

    Returns
    -------
    str
        HTML string with Plotly figure
    """
    import plotly.graph_objects as go
    import numpy as np

    # Extract data
    locations = []
    values = []
    for i, r in enumerate(readings, 1):
        if isinstance(r, dict):
            locations.append(r.get('location', f'Point {i}'))
            values.append(r.get('hardness_value', 0))
        else:
            locations.append(r.location or f'Point {i}')
            values.append(r.hardness_value)

    # Calculate statistics
    mean_val = np.mean(values)
    std_val = np.std(values, ddof=1) if len(values) > 1 else 0

    fig = go.Figure()

    # Bar chart for readings
    fig.add_trace(go.Bar(
        x=list(range(1, len(values) + 1)),
        y=values,
        text=[f'{v:.1f}' for v in values],
        textposition='outside',
        name='Readings',
        marker_color='steelblue',
        hovertemplate='%{customdata}<br>%{y:.1f} ' + load_level + '<extra></extra>',
        customdata=locations
    ))

    # Mean line
    fig.add_hline(
        y=mean_val,
        line_dash='dash',
        line_color='red',
        annotation_text=f'Mean: {mean_val:.1f}',
        annotation_position='right'
    )

    # +/- 1 std dev band
    if std_val > 0:
        fig.add_hrect(
            y0=mean_val - std_val,
            y1=mean_val + std_val,
            fillcolor='rgba(255, 0, 0, 0.1)',
            line_width=0,
            annotation_text=f'+/-1s: {std_val:.1f}',
            annotation_position='left'
        )

    fig.update_layout(
        title=f'Hardness Profile ({load_level})',
        xaxis_title='Reading Number',
        yaxis_title=f'Hardness ({load_level})',
        template='plotly_white',
        showlegend=False,
        height=400,
        yaxis=dict(range=[0, max(values) * 1.2])
    )

    return fig.to_html(full_html=False, include_plotlyjs='cdn')


@vickers_bp.route('/')
@login_required
def index():
    """List all Vickers tests."""
    tests = TestRecord.query.filter_by(test_method='VICKERS').order_by(
        TestRecord.created_at.desc()
    ).all()
    return render_template('vickers/index.html', tests=tests)


@vickers_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create a new Vickers test."""
    form = SpecimenForm()

    # Populate certificate dropdown
    certificates = Certificate.query.order_by(Certificate.certificate_number.desc()).all()
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
        # Create test record
        test = TestRecord(
            test_id=form.test_id.data,
            test_method='VICKERS',
            specimen_id=form.specimen_id.data,
            material=form.material.data,
            test_date=form.test_date.data or datetime.now().date(),
            temperature=str(form.temperature.data) if form.temperature.data else '23',
            location_orientation=form.location_orientation.data,
            notes=form.notes.data,
            status='DRAFT',
            created_by=current_user.id
        )

        # Link to certificate if selected
        if form.certificate_id.data and form.certificate_id.data != 0:
            cert = Certificate.query.get(form.certificate_id.data)
            if cert:
                test.certificate_id = cert.id
                test.certificate_number = cert.certificate_number_with_rev

        # Build test parameters
        test_params = {
            'load_level': form.load_level.data,
            'dwell_time': form.dwell_time.data,
        }
        test.specimen_geometry = json.dumps(test_params)

        # Collect readings
        readings = []
        for i in range(1, 11):
            location = getattr(form, f'reading_{i}_location').data
            value = getattr(form, f'reading_{i}_value').data
            if value is not None and value > 0:
                readings.append({
                    'reading_number': len(readings) + 1,
                    'location': location or f'Point {len(readings) + 1}',
                    'hardness_value': value,
                })

        # Store readings as raw data
        raw_data = {'readings': readings}

        # Handle photo upload
        if form.photo.data:
            photo = form.photo.data
            filename = secure_filename(photo.filename)
            # Add test_id prefix to avoid collisions
            filename = f"vickers_{form.test_id.data}_{filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            photo.save(filepath)
            raw_data['photo_path'] = filename

        test.raw_data = json.dumps(raw_data)

        # Run analysis if we have readings
        if readings:
            try:
                # Create VickersReading objects
                reading_objects = [
                    VickersReading(
                        reading_number=r['reading_number'],
                        location=r['location'],
                        hardness_value=r['hardness_value']
                    )
                    for r in readings
                ]

                # Create load level
                load_value = float(form.load_level.data.replace('HV ', ''))
                load_level = VickersLoadLevel(form.load_level.data, load_value)

                # Create test data
                test_data = VickersTestData(
                    readings=reading_objects,
                    load_level=load_level,
                    specimen_id=form.specimen_id.data or '',
                    material=form.material.data or ''
                )

                # Run analysis
                analyzer = VickersAnalyzer()
                result = analyzer.run_analysis(test_data)

                # Get uncertainty budget
                import numpy as np
                values = np.array([r['hardness_value'] for r in readings])
                uncertainty_budget = analyzer.get_uncertainty_budget(values, result.mean_hardness.value)

                # Store results
                results_dict = {
                    'mean_hardness': {
                        'value': result.mean_hardness.value,
                        'uncertainty': result.mean_hardness.uncertainty
                    },
                    'std_dev': result.std_dev,
                    'range_value': result.range_value,
                    'min_value': result.min_value,
                    'max_value': result.max_value,
                    'n_readings': result.n_readings,
                    'load_level': result.load_level,
                    'uncertainty_budget': uncertainty_budget,
                }

                # Create AnalysisResult record
                analysis = AnalysisResult(
                    test_record=test,
                    analysis_type='VICKERS_E92',
                    result_data=json.dumps(results_dict),
                    created_by=current_user.id
                )
                db.session.add(analysis)
                test.status = 'ANALYZED'
                flash(f'Analysis completed: Mean = {result.mean_hardness.value:.1f} +/- {result.mean_hardness.uncertainty:.1f} {result.load_level}', 'success')
            except Exception as e:
                flash(f'Analysis error: {e}', 'warning')
                test.status = 'DRAFT'
        else:
            flash('No hardness readings entered.', 'warning')

        db.session.add(test)

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='CREATE',
            table_name='test_record',
            record_id=test.id,
            new_values=json.dumps({'test_id': test.test_id, 'test_method': 'VICKERS'})
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Vickers test {test.test_id} created.', 'success')
        return redirect(url_for('vickers.view', test_id=test.id))

    return render_template('vickers/new.html', form=form)


@vickers_bp.route('/<int:test_id>')
@login_required
def view(test_id):
    """View Vickers test details and results."""
    test = TestRecord.query.get_or_404(test_id)

    if test.test_method != 'VICKERS':
        flash('Invalid test type.', 'error')
        return redirect(url_for('vickers.index'))

    # Parse stored data
    test_params = json.loads(test.specimen_geometry) if test.specimen_geometry else {}
    raw_data = json.loads(test.raw_data) if test.raw_data else {}
    readings = raw_data.get('readings', [])

    # Get analysis results
    results = {}
    analysis = AnalysisResult.query.filter_by(test_record_id=test.id).first()
    if analysis:
        results = json.loads(analysis.result_data) if analysis.result_data else {}

    # Create plot if we have readings
    hardness_plot = None
    if readings:
        load_level = test_params.get('load_level', 'HV')
        hardness_plot = create_hardness_profile_plot(readings, load_level)

    # Get photo path
    photo_url = None
    if raw_data.get('photo_path'):
        photo_url = url_for('static', filename=f'uploads/{raw_data["photo_path"]}')

    return render_template('vickers/view.html',
                           test=test,
                           test_params=test_params,
                           readings=readings,
                           results=results,
                           hardness_plot=hardness_plot,
                           photo_url=photo_url)


@vickers_bp.route('/<int:test_id>/report', methods=['GET', 'POST'])
@login_required
def report(test_id):
    """Generate Vickers test report."""
    test = TestRecord.query.get_or_404(test_id)

    if test.test_method != 'VICKERS':
        flash('Invalid test type.', 'error')
        return redirect(url_for('vickers.index'))

    form = ReportForm()

    # Pre-fill certificate number
    if request.method == 'GET':
        form.certificate_number.data = test.certificate_number or test.test_id

    if form.validate_on_submit():
        try:
            # Parse stored data
            test_params = json.loads(test.specimen_geometry) if test.specimen_geometry else {}
            raw_data = json.loads(test.raw_data) if test.raw_data else {}
            readings = raw_data.get('readings', [])

            # Get analysis results
            analysis = AnalysisResult.query.filter_by(test_record_id=test.id).first()
            results = json.loads(analysis.result_data) if analysis and analysis.result_data else {}

            # Generate chart image for report
            chart_path = None
            if readings:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt
                import numpy as np

                values = [r['hardness_value'] for r in readings]
                mean_val = np.mean(values)
                std_val = np.std(values, ddof=1) if len(values) > 1 else 0

                fig, ax = plt.subplots(figsize=(8, 5))

                # Bar chart
                x = range(1, len(values) + 1)
                bars = ax.bar(x, values, color='steelblue', edgecolor='black')

                # Add value labels
                for bar, val in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                            f'{val:.1f}', ha='center', va='bottom', fontsize=9)

                # Mean line
                ax.axhline(y=mean_val, color='red', linestyle='--',
                           label=f'Mean: {mean_val:.1f}')

                # +/- 1 std dev
                if std_val > 0:
                    ax.axhspan(mean_val - std_val, mean_val + std_val,
                               alpha=0.2, color='red', label=f'+/-1s: {std_val:.1f}')

                ax.set_xlabel('Reading Number')
                ax.set_ylabel(f'Hardness ({test_params.get("load_level", "HV")})')
                ax.set_title('Hardness Profile')
                ax.legend()
                ax.set_ylim(0, max(values) * 1.25)
                ax.grid(True, alpha=0.3, axis='y')

                chart_path = Path(current_app.config['REPORTS_FOLDER']) / f'vickers_chart_{test.id}.png'
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
                'load_level': test_params.get('load_level', 'HV 10'),
                'dwell_time': test_params.get('dwell_time', '15'),
            }

            # Create VickersResult for report
            class ResultProxy:
                def __init__(self, data, readings_list):
                    self._data = data
                    self._readings = readings_list

                @property
                def mean_hardness(self):
                    d = self._data.get('mean_hardness', {})
                    return type('MV', (), {
                        'value': d.get('value', 0),
                        'uncertainty': d.get('uncertainty', 0)
                    })()

                @property
                def std_dev(self):
                    return self._data.get('std_dev', 0)

                @property
                def range_value(self):
                    return self._data.get('range_value', 0)

                @property
                def min_value(self):
                    return self._data.get('min_value', 0)

                @property
                def max_value(self):
                    return self._data.get('max_value', 0)

                @property
                def n_readings(self):
                    return self._data.get('n_readings', 0)

                @property
                def load_level(self):
                    return self._data.get('load_level', 'HV')

                @property
                def readings(self):
                    return [
                        type('R', (), {
                            'reading_number': r.get('reading_number', i),
                            'location': r.get('location', f'Point {i}'),
                            'hardness_value': r.get('hardness_value', 0)
                        })()
                        for i, r in enumerate(self._readings, 1)
                    ]

            result_proxy = ResultProxy(results, readings)
            uncertainty_budget = results.get('uncertainty_budget', {})

            # Create report from scratch (no template dependency)
            from docx import Document
            from docx.shared import Inches, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            doc = Document()

            # Title
            title = doc.add_heading('Vickers Hardness Test Report', level=0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER

            subtitle = doc.add_paragraph('ASTM E92 / ISO 6507')
            subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

            doc.add_paragraph()

            # Test Information
            doc.add_heading('Test Information', level=1)
            table = doc.add_table(rows=6, cols=2)
            table.style = 'Table Grid'

            info_data = [
                ('Certificate Number:', test_info['certificate_number']),
                ('Specimen ID:', test_info['specimen_id']),
                ('Material:', test_info['material']),
                ('Test Date:', test_info['test_date']),
                ('Load Level:', test_info['load_level']),
                ('Dwell Time:', f"{test_info['dwell_time']} s"),
            ]

            for i, (label, value) in enumerate(info_data):
                table.rows[i].cells[0].text = label
                table.rows[i].cells[1].text = str(value)
                table.rows[i].cells[0].paragraphs[0].runs[0].bold = True

            doc.add_paragraph()

            # Results Summary
            doc.add_heading('Results Summary', level=1)
            table = doc.add_table(rows=7, cols=3)
            table.style = 'Table Grid'

            headers = ['Parameter', 'Value', 'Unit']
            for i, h in enumerate(headers):
                table.rows[0].cells[i].text = h
                table.rows[0].cells[i].paragraphs[0].runs[0].bold = True

            results_data = [
                ('Mean Hardness', f'{result_proxy.mean_hardness.value:.1f} +/- {result_proxy.mean_hardness.uncertainty:.1f}', result_proxy.load_level),
                ('Standard Deviation', f'{result_proxy.std_dev:.1f}', result_proxy.load_level),
                ('Range', f'{result_proxy.range_value:.1f}', result_proxy.load_level),
                ('Minimum', f'{result_proxy.min_value:.1f}', result_proxy.load_level),
                ('Maximum', f'{result_proxy.max_value:.1f}', result_proxy.load_level),
                ('Number of Readings', str(result_proxy.n_readings), '-'),
            ]

            for i, (param, value, unit) in enumerate(results_data):
                table.rows[i+1].cells[0].text = param
                table.rows[i+1].cells[1].text = value
                table.rows[i+1].cells[2].text = unit

            doc.add_paragraph()

            # Individual Readings
            doc.add_heading('Individual Readings', level=1)
            table = doc.add_table(rows=len(readings) + 1, cols=3)
            table.style = 'Table Grid'

            headers = ['#', 'Location', 'Hardness']
            for i, h in enumerate(headers):
                table.rows[0].cells[i].text = h
                table.rows[0].cells[i].paragraphs[0].runs[0].bold = True

            for i, r in enumerate(readings):
                table.rows[i+1].cells[0].text = str(r.get('reading_number', i+1))
                table.rows[i+1].cells[1].text = r.get('location', f'Point {i+1}')
                table.rows[i+1].cells[2].text = f"{r.get('hardness_value', 0):.1f}"

            doc.add_paragraph()

            # Uncertainty Budget (if requested)
            if form.include_uncertainty_budget.data == 'yes' and uncertainty_budget:
                doc.add_heading('Uncertainty Budget (k=2)', level=1)
                table = doc.add_table(rows=6, cols=2)
                table.style = 'Table Grid'

                unc_data = [
                    ('Type A (Repeatability)', f"{uncertainty_budget.get('u_A', 0):.2f}"),
                    ('Machine Calibration', f"{uncertainty_budget.get('u_machine', 0):.2f}"),
                    ('Diagonal Measurement', f"{uncertainty_budget.get('u_diagonal', 0):.2f}"),
                    ('Force Application', f"{uncertainty_budget.get('u_force', 0):.2f}"),
                    ('Combined Standard (u_c)', f"{uncertainty_budget.get('u_combined', 0):.2f}"),
                    ('Expanded (U, k=2)', f"{uncertainty_budget.get('U_expanded', 0):.2f}"),
                ]

                for i, (comp, val) in enumerate(unc_data):
                    table.rows[i].cells[0].text = comp
                    table.rows[i].cells[1].text = val

                doc.add_paragraph()

            # Chart
            if chart_path and chart_path.exists():
                doc.add_heading('Hardness Profile', level=1)
                doc.add_picture(str(chart_path), width=Inches(5.5))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

            doc.add_paragraph()

            # Footer
            footer = doc.add_paragraph()
            footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
            from datetime import datetime
            footer.add_run(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font.size = Pt(9)

            # Save document
            output_filename = f"Vickers_Report_{test.test_id.replace(' ', '_')}.docx"
            output_path = Path(current_app.config['REPORTS_FOLDER']) / output_filename
            doc.save(output_path)

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
            return redirect(url_for('vickers.view', test_id=test.id))

    return render_template('vickers/report.html', test=test, form=form)


@vickers_bp.route('/<int:test_id>/delete', methods=['POST'])
@login_required
def delete(test_id):
    """Delete a Vickers test (admin only)."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('vickers.index'))

    test = TestRecord.query.get_or_404(test_id)

    if test.test_method != 'VICKERS':
        flash('Invalid test type.', 'error')
        return redirect(url_for('vickers.index'))

    test_id_str = test.test_id

    # Audit log before deletion
    audit = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        table_name='test_record',
        record_id=test.id,
        old_values=json.dumps({'test_id': test_id_str, 'test_method': 'VICKERS'})
    )
    db.session.add(audit)

    # Delete analysis results first
    AnalysisResult.query.filter_by(test_record_id=test.id).delete()
    db.session.delete(test)
    db.session.commit()

    flash(f'Vickers test {test_id_str} deleted.', 'success')
    return redirect(url_for('vickers.index'))
