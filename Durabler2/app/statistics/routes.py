"""Statistics routes for test data analysis and reporting."""
import io
import csv
from datetime import datetime, timedelta
from flask import render_template, request, jsonify, Response
from flask_login import login_required
from sqlalchemy import func, and_, or_

from . import statistics_bp
from app.extensions import db
from app.models import TestRecord, AnalysisResult, Certificate


# Parameter mappings for each test method
PARAMETER_LABELS = {
    'CTOD': {
        'delta_m': 'CTOD δm (mm)',
        'delta_c': 'CTOD δc (mm)',
        'delta_u': 'CTOD δu (mm)',
        'P_max': 'Max Force (kN)',
        'K_max': 'K_max (MPa√m)',
    },
    'KIC': {
        'K_IC': 'K_IC (MPa√m)',
        'K_Q': 'K_Q (MPa√m)',
        'P_max': 'Max Force (kN)',
        'P_Q': 'P_Q (kN)',
    },
    'FCGR': {
        'paris_C': 'Paris C',
        'paris_m': 'Paris m',
        'delta_K_min': 'ΔK min (MPa√m)',
        'delta_K_max': 'ΔK max (MPa√m)',
        'final_crack': 'Final Crack (mm)',
    },
    'TENSILE': {
        'Rp02': 'Rp0.2 (MPa)',
        'Rm': 'Rm (MPa)',
        'E': "Young's Modulus (GPa)",
        'A': 'Elongation (%)',
        'Z': 'Reduction of Area (%)',
    },
    'VICKERS': {
        'mean_hardness': 'Mean Hardness (HV)',
        'std_dev': 'Std Dev',
        'range': 'Range',
    },
}


@statistics_bp.route('/')
@login_required
def index():
    """Statistics dashboard."""
    # Get available test methods
    test_methods = db.session.query(TestRecord.test_method).distinct().all()
    test_methods = [m[0] for m in test_methods if m[0]]

    # Get available materials
    materials = db.session.query(TestRecord.material).distinct().filter(
        TestRecord.material.isnot(None),
        TestRecord.material != ''
    ).order_by(TestRecord.material).all()
    materials = [m[0] for m in materials]

    # Get temperature range
    temp_range = db.session.query(
        func.min(TestRecord.temperature),
        func.max(TestRecord.temperature)
    ).filter(TestRecord.temperature.isnot(None)).first()

    # Get date range
    date_range = db.session.query(
        func.min(TestRecord.test_date),
        func.max(TestRecord.test_date)
    ).filter(TestRecord.test_date.isnot(None)).first()

    # Quick stats
    total_tests = TestRecord.query.count()
    tests_this_month = TestRecord.query.filter(
        TestRecord.test_date >= datetime.now().replace(day=1)
    ).count()
    tests_this_year = TestRecord.query.filter(
        TestRecord.test_date >= datetime(datetime.now().year, 1, 1)
    ).count()

    return render_template('statistics/index.html',
                           test_methods=test_methods,
                           materials=materials,
                           temp_range=temp_range,
                           date_range=date_range,
                           total_tests=total_tests,
                           tests_this_month=tests_this_month,
                           tests_this_year=tests_this_year,
                           parameter_labels=PARAMETER_LABELS)


@statistics_bp.route('/query', methods=['POST'])
@login_required
def query():
    """Execute statistics query and return results."""
    # Get filter parameters
    test_method = request.form.get('test_method')
    parameter = request.form.get('parameter')
    material = request.form.get('material', '').strip()
    temp_min = request.form.get('temp_min', type=float)
    temp_max = request.form.get('temp_max', type=float)
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')

    if not test_method or not parameter:
        return jsonify({'error': 'Test method and parameter are required'}), 400

    # Build query
    query = db.session.query(
        AnalysisResult.value,
        AnalysisResult.uncertainty,
        TestRecord.test_id,
        TestRecord.specimen_id,
        TestRecord.material,
        TestRecord.temperature,
        TestRecord.test_date,
        Certificate.certificate_number
    ).join(TestRecord).outerjoin(Certificate)

    # Apply filters
    query = query.filter(
        TestRecord.test_method == test_method,
        AnalysisResult.parameter_name == parameter
    )

    if material:
        query = query.filter(TestRecord.material.ilike(f'%{material}%'))

    if temp_min is not None:
        query = query.filter(TestRecord.temperature >= temp_min)
    if temp_max is not None:
        query = query.filter(TestRecord.temperature <= temp_max)

    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(TestRecord.test_date >= date_from_dt)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(TestRecord.test_date <= date_to_dt)
        except ValueError:
            pass

    # Execute query
    results = query.order_by(TestRecord.test_date.desc()).all()

    if not results:
        return jsonify({
            'count': 0,
            'message': 'No results found for the selected criteria'
        })

    # Calculate statistics
    values = [r.value for r in results if r.value is not None]

    if not values:
        return jsonify({
            'count': 0,
            'message': 'No valid values found'
        })

    import numpy as np
    values_arr = np.array(values)

    stats = {
        'count': len(values),
        'mean': float(np.mean(values_arr)),
        'std_dev': float(np.std(values_arr, ddof=1)) if len(values) > 1 else 0,
        'min': float(np.min(values_arr)),
        'max': float(np.max(values_arr)),
        'median': float(np.median(values_arr)),
    }

    # Include individual results
    data = []
    for r in results:
        data.append({
            'value': r.value,
            'uncertainty': r.uncertainty,
            'test_id': r.test_id,
            'specimen_id': r.specimen_id,
            'material': r.material,
            'temperature': r.temperature,
            'test_date': r.test_date.strftime('%Y-%m-%d') if r.test_date else None,
            'certificate': r.certificate_number,
        })

    return jsonify({
        'stats': stats,
        'data': data,
        'parameter': parameter,
        'parameter_label': PARAMETER_LABELS.get(test_method, {}).get(parameter, parameter),
        'test_method': test_method,
        'filters': {
            'material': material,
            'temp_min': temp_min,
            'temp_max': temp_max,
            'date_from': date_from,
            'date_to': date_to,
        }
    })


@statistics_bp.route('/export', methods=['POST'])
@login_required
def export():
    """Export query results to CSV."""
    # Get filter parameters (same as query)
    test_method = request.form.get('test_method')
    parameter = request.form.get('parameter')
    material = request.form.get('material', '').strip()
    temp_min = request.form.get('temp_min', type=float)
    temp_max = request.form.get('temp_max', type=float)
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')

    if not test_method or not parameter:
        return jsonify({'error': 'Test method and parameter are required'}), 400

    # Build query
    query = db.session.query(
        AnalysisResult.value,
        AnalysisResult.uncertainty,
        AnalysisResult.unit,
        TestRecord.test_id,
        TestRecord.specimen_id,
        TestRecord.material,
        TestRecord.temperature,
        TestRecord.test_date,
        Certificate.certificate_number
    ).join(TestRecord).outerjoin(Certificate)

    query = query.filter(
        TestRecord.test_method == test_method,
        AnalysisResult.parameter_name == parameter
    )

    if material:
        query = query.filter(TestRecord.material.ilike(f'%{material}%'))
    if temp_min is not None:
        query = query.filter(TestRecord.temperature >= temp_min)
    if temp_max is not None:
        query = query.filter(TestRecord.temperature <= temp_max)
    if date_from:
        try:
            query = query.filter(TestRecord.test_date >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(TestRecord.test_date <= datetime.strptime(date_to, '%Y-%m-%d'))
        except ValueError:
            pass

    results = query.order_by(TestRecord.test_date.desc()).all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Test ID', 'Specimen ID', 'Material', 'Temperature (°C)',
        'Test Date', 'Certificate', parameter, 'Uncertainty', 'Unit'
    ])

    # Data
    for r in results:
        writer.writerow([
            r.test_id,
            r.specimen_id,
            r.material,
            r.temperature,
            r.test_date.strftime('%Y-%m-%d') if r.test_date else '',
            r.certificate_number or '',
            r.value,
            r.uncertainty or '',
            r.unit or ''
        ])

    output.seek(0)
    filename = f'statistics_{test_method}_{parameter}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@statistics_bp.route('/parameters/<test_method>')
@login_required
def get_parameters(test_method):
    """Get available parameters for a test method."""
    # Get parameters that actually have data
    params = db.session.query(AnalysisResult.parameter_name).join(TestRecord).filter(
        TestRecord.test_method == test_method
    ).distinct().all()
    params = [p[0] for p in params if p[0]]

    # Map to labels
    labels = PARAMETER_LABELS.get(test_method, {})
    result = []
    for p in params:
        result.append({
            'name': p,
            'label': labels.get(p, p)
        })

    return jsonify(result)


@statistics_bp.route('/materials/<test_method>')
@login_required
def get_materials(test_method):
    """Get materials available for a test method."""
    materials = db.session.query(TestRecord.material).filter(
        TestRecord.test_method == test_method,
        TestRecord.material.isnot(None),
        TestRecord.material != ''
    ).distinct().order_by(TestRecord.material).all()

    return jsonify([m[0] for m in materials])


@statistics_bp.route('/summary')
@login_required
def summary():
    """Get summary statistics for dashboard."""
    # Tests per method
    tests_per_method = db.session.query(
        TestRecord.test_method,
        func.count(TestRecord.id)
    ).group_by(TestRecord.test_method).all()

    # Tests per month (last 12 months)
    twelve_months_ago = datetime.now() - timedelta(days=365)
    tests_per_month = db.session.query(
        func.strftime('%Y-%m', TestRecord.test_date),
        func.count(TestRecord.id)
    ).filter(
        TestRecord.test_date >= twelve_months_ago
    ).group_by(
        func.strftime('%Y-%m', TestRecord.test_date)
    ).order_by(
        func.strftime('%Y-%m', TestRecord.test_date)
    ).all()

    # Top materials
    top_materials = db.session.query(
        TestRecord.material,
        func.count(TestRecord.id)
    ).filter(
        TestRecord.material.isnot(None),
        TestRecord.material != ''
    ).group_by(TestRecord.material).order_by(
        func.count(TestRecord.id).desc()
    ).limit(10).all()

    return jsonify({
        'tests_per_method': dict(tests_per_method),
        'tests_per_month': dict(tests_per_month),
        'top_materials': dict(top_materials),
    })
