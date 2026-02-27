"""Routes for TTT/CCT diagram viewing and JMAK parameter management."""
import io
import json
import logging

from flask import (
    render_template, redirect, url_for, flash, request,
    Response, jsonify
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import SteelGrade
from app.models.ttt_parameters import (
    TTTParameters, JMAKParameters, MartensiteParameters,
    TTTCalibrationData, TTTCurve,
    B_MODEL_GAUSSIAN,
)
from app.services.phase_transformation import (
    PhasePredictor, calculate_critical_temperatures,
)

from . import ttt_cct_bp
from .forms import (
    TTTParametersForm, JMAKParametersForm,
    MartensiteForm, CalibrationUploadForm,
)

logger = logging.getLogger(__name__)


@ttt_cct_bp.route('/')
@login_required
def index():
    """List all steel grades with TTT/CCT parameter status."""
    grades = SteelGrade.query.order_by(SteelGrade.designation).all()

    grade_info = []
    for g in grades:
        ttt = TTTParameters.query.filter_by(steel_grade_id=g.id).first()
        has_jmak = ttt.has_jmak_data if ttt else False
        has_diagram = g.phase_diagrams.filter_by(diagram_type='CCT').first() is not None
        has_comp = g.composition is not None

        predictor = PhasePredictor(g)
        tier = predictor.tier

        grade_info.append({
            'grade': g,
            'has_ttt_params': ttt is not None,
            'has_jmak': has_jmak,
            'has_diagram': has_diagram,
            'has_composition': has_comp,
            'prediction_tier': tier,
        })

    return render_template('ttt_cct/index.html', grades=grade_info)


@ttt_cct_bp.route('/grade/<int:grade_id>')
@login_required
def view(grade_id):
    """View TTT/CCT diagrams and parameters for a steel grade."""
    grade = SteelGrade.query.get_or_404(grade_id)
    ttt = TTTParameters.query.filter_by(steel_grade_id=grade_id).first()

    predictor = PhasePredictor(grade)
    trans_temps = predictor.get_transformation_temps()

    jmak_phases = {}
    if ttt:
        for jmak in ttt.jmak_parameters.all():
            jmak_phases[jmak.phase] = {
                'n': jmak.n_value,
                'model': jmak.b_model_type,
                'nose_temp': jmak.nose_temperature,
                'nose_time': jmak.nose_time,
            }

    martensite = ttt.martensite_parameters if ttt else None

    return render_template('ttt_cct/view.html',
                           grade=grade,
                           ttt=ttt,
                           trans_temps=trans_temps,
                           jmak_phases=jmak_phases,
                           martensite=martensite,
                           prediction_tier=predictor.tier)


@ttt_cct_bp.route('/grade/<int:grade_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_parameters(grade_id):
    """Edit TTT transformation parameters for a steel grade."""
    grade = SteelGrade.query.get_or_404(grade_id)
    ttt = TTTParameters.query.filter_by(steel_grade_id=grade_id).first()

    form = TTTParametersForm(obj=ttt)

    if form.validate_on_submit():
        if ttt is None:
            ttt = TTTParameters(steel_grade_id=grade_id)
            db.session.add(ttt)

        ttt.ae1 = form.ae1.data
        ttt.ae3 = form.ae3.data
        ttt.bs = form.bs.data
        ttt.ms = form.ms.data
        ttt.mf = form.mf.data
        ttt.austenitizing_temperature = form.austenitizing_temperature.data
        ttt.grain_size_astm = form.grain_size_astm.data
        ttt.data_source = form.data_source.data
        ttt.notes = form.notes.data

        # Invalidate cached curves
        TTTCurve.query.filter_by(ttt_parameters_id=ttt.id).delete()

        db.session.commit()
        flash('TTT parameters saved.', 'success')
        return redirect(url_for('ttt_cct.view', grade_id=grade_id))

    return render_template('ttt_cct/edit_parameters.html',
                           grade=grade, ttt=ttt, form=form)


@ttt_cct_bp.route('/grade/<int:grade_id>/jmak/<phase>', methods=['GET', 'POST'])
@login_required
def edit_jmak(grade_id, phase):
    """Edit JMAK parameters for a specific phase."""
    grade = SteelGrade.query.get_or_404(grade_id)
    ttt = TTTParameters.query.filter_by(steel_grade_id=grade_id).first()

    if ttt is None:
        flash('Create TTT parameters first.', 'warning')
        return redirect(url_for('ttt_cct.edit_parameters', grade_id=grade_id))

    jmak = ttt.jmak_parameters.filter_by(phase=phase).first()

    form = JMAKParametersForm()
    if request.method == 'GET' and jmak:
        form.phase.data = phase
        form.n_value.data = jmak.n_value
        form.b_model_type.data = jmak.b_model_type
        form.nose_temperature.data = jmak.nose_temperature
        form.nose_time.data = jmak.nose_time
        form.temp_range_min.data = jmak.temp_range_min
        form.temp_range_max.data = jmak.temp_range_max

        b_params = jmak.b_params_dict
        if jmak.b_model_type == 'gaussian':
            form.b_max.data = b_params.get('b_max')
            form.t_nose.data = b_params.get('t_nose')
            form.sigma.data = b_params.get('sigma')
        elif jmak.b_model_type == 'arrhenius':
            form.b0.data = b_params.get('b0')
            form.Q.data = b_params.get('Q')

    if form.validate_on_submit():
        if jmak is None:
            jmak = JMAKParameters(ttt_parameters_id=ttt.id, phase=phase)
            db.session.add(jmak)

        jmak.n_value = form.n_value.data
        jmak.b_model_type = form.b_model_type.data
        jmak.nose_temperature = form.nose_temperature.data
        jmak.nose_time = form.nose_time.data
        jmak.temp_range_min = form.temp_range_min.data
        jmak.temp_range_max = form.temp_range_max.data

        # Build b_parameters JSON
        if form.b_model_type.data == 'gaussian':
            b_params = {
                'b_max': form.b_max.data,
                't_nose': form.t_nose.data,
                'sigma': form.sigma.data,
            }
        elif form.b_model_type.data == 'arrhenius':
            b_params = {
                'b0': form.b0.data,
                'Q': form.Q.data,
            }
        else:
            b_params = {}
        jmak.set_b_params(b_params)

        # Invalidate cached curves
        TTTCurve.query.filter_by(ttt_parameters_id=ttt.id).delete()

        db.session.commit()
        flash(f'JMAK parameters for {phase} saved.', 'success')
        return redirect(url_for('ttt_cct.view', grade_id=grade_id))

    return render_template('ttt_cct/edit_jmak.html',
                           grade=grade, phase=phase, form=form)


@ttt_cct_bp.route('/grade/<int:grade_id>/martensite', methods=['GET', 'POST'])
@login_required
def edit_martensite(grade_id):
    """Edit Koistinen-Marburger martensite parameters."""
    grade = SteelGrade.query.get_or_404(grade_id)
    ttt = TTTParameters.query.filter_by(steel_grade_id=grade_id).first()

    if ttt is None:
        flash('Create TTT parameters first.', 'warning')
        return redirect(url_for('ttt_cct.edit_parameters', grade_id=grade_id))

    mart = ttt.martensite_parameters
    form = MartensiteForm(obj=mart)

    if form.validate_on_submit():
        if mart is None:
            mart = MartensiteParameters(ttt_parameters_id=ttt.id)
            db.session.add(mart)

        mart.ms = form.ms.data
        mart.mf = form.mf.data
        mart.alpha_m = form.alpha_m.data

        db.session.commit()
        flash('Martensite parameters saved.', 'success')
        return redirect(url_for('ttt_cct.view', grade_id=grade_id))

    return render_template('ttt_cct/edit_martensite.html',
                           grade=grade, form=form)


@ttt_cct_bp.route('/grade/<int:grade_id>/auto-generate', methods=['POST'])
@login_required
def auto_generate(grade_id):
    """Auto-generate TTT parameters from steel composition."""
    grade = SteelGrade.query.get_or_404(grade_id)

    if not grade.composition:
        flash('Steel composition required for auto-generation.', 'warning')
        return redirect(url_for('ttt_cct.view', grade_id=grade_id))

    comp = grade.composition.to_dict()
    temps = calculate_critical_temperatures(comp)

    ttt = TTTParameters.query.filter_by(steel_grade_id=grade_id).first()
    if ttt is None:
        ttt = TTTParameters(steel_grade_id=grade_id)
        db.session.add(ttt)

    ttt.ae1 = temps['Ae1']
    ttt.ae3 = temps['Ae3']
    ttt.bs = temps['Bs']
    ttt.ms = temps['Ms']
    ttt.mf = temps['Mf']
    ttt.data_source = 'empirical'
    ttt.notes = 'Auto-generated from composition using Andrews/Steven-Haynes'

    db.session.flush()

    # Create martensite parameters
    mart = ttt.martensite_parameters
    if mart is None:
        mart = MartensiteParameters(ttt_parameters_id=ttt.id)
        db.session.add(mart)
    mart.ms = temps['Ms']
    mart.mf = temps['Mf']
    mart.alpha_m = 0.011

    # Auto-generate JMAK parameters (estimated from composition)
    _auto_generate_jmak(ttt, comp, temps)

    # Invalidate cached curves
    TTTCurve.query.filter_by(ttt_parameters_id=ttt.id).delete()

    db.session.commit()
    flash('TTT parameters auto-generated from composition.', 'success')
    return redirect(url_for('ttt_cct.view', grade_id=grade_id))


def _auto_generate_jmak(ttt, comp, temps):
    """Generate estimated JMAK parameters from composition."""
    import math

    C = comp.get('C', 0.0)
    Mn = comp.get('Mn', 0.0)
    Cr = comp.get('Cr', 0.0)
    Mo = comp.get('Mo', 0.0)

    # Hardenability factor (shifts nose time)
    hf = (1 + 6*C) * (1 + 1.2*Mn) * (1 + 0.6*Cr) * (1 + 1.5*Mo)

    ae1 = temps['Ae1']
    ae3 = temps['Ae3']
    bs = temps['Bs']
    ms = temps['Ms']

    phase_configs = []

    # Ferrite
    if C < 0.8 and ae3 > ae1:
        undercooling = 30 + 10*Cr + 10*Mo + 5*Mn
        nose_t = ae1 - undercooling
        nose_t = max(nose_t, bs + 30)
        nose_time = 1.5 * hf  # seconds at nose for 1% start
        b_max = math.log(100) / (nose_time ** 2.0)  # for n=2

        phase_configs.append({
            'phase': 'ferrite',
            'n': 2.0,
            'b_max': b_max,
            't_nose': nose_t,
            'sigma': max((ae1 - nose_t) / 1.5, 30),
            'nose_temp': nose_t,
            'nose_time': nose_time,
            'temp_min': bs + 20,
            'temp_max': ae3,
        })

    # Pearlite
    pearlite_nose_t = ae1 - 70
    pearlite_retard = (1 + 0.8*Cr) * (1 + 1.2*Mo)
    pearlite_nose_time = 3.0 * hf * pearlite_retard / max(C, 0.15)
    pearlite_b_max = math.log(100) / (pearlite_nose_time ** 1.5)

    phase_configs.append({
        'phase': 'pearlite',
        'n': 1.5,
        'b_max': pearlite_b_max,
        't_nose': pearlite_nose_t,
        'sigma': max((ae1 - pearlite_nose_t + 30) / 1.5, 30),
        'nose_temp': pearlite_nose_t,
        'nose_time': pearlite_nose_time,
        'temp_min': bs,
        'temp_max': ae1,
    })

    # Bainite
    if bs > ms + 20:
        bainite_nose_t = ms + 0.5 * (bs - ms)
        bainite_retard = (1 + 0.8*Cr) * (1 + 1.5*Mo)
        bainite_nose_time = 0.5 * hf * bainite_retard
        bainite_b_max = math.log(100) / (bainite_nose_time ** 2.5)

        phase_configs.append({
            'phase': 'bainite',
            'n': 2.5,
            'b_max': bainite_b_max,
            't_nose': bainite_nose_t,
            'sigma': max((bs - bainite_nose_t) / 1.5, 30),
            'nose_temp': bainite_nose_t,
            'nose_time': bainite_nose_time,
            'temp_min': ms + 10,
            'temp_max': bs,
        })

    # Create/update JMAKParameters
    for cfg in phase_configs:
        jmak = ttt.jmak_parameters.filter_by(phase=cfg['phase']).first()
        if jmak is None:
            jmak = JMAKParameters(ttt_parameters_id=ttt.id, phase=cfg['phase'])
            db.session.add(jmak)

        jmak.n_value = cfg['n']
        jmak.b_model_type = B_MODEL_GAUSSIAN
        jmak.set_b_params({
            'b_max': cfg['b_max'],
            't_nose': cfg['t_nose'],
            'sigma': cfg['sigma'],
        })
        jmak.nose_temperature = cfg['nose_temp']
        jmak.nose_time = cfg['nose_time']
        jmak.temp_range_min = cfg['temp_min']
        jmak.temp_range_max = cfg['temp_max']


@ttt_cct_bp.route('/grade/<int:grade_id>/calibrate', methods=['GET', 'POST'])
@login_required
def calibrate(grade_id):
    """Upload dilatometry data and calibrate JMAK parameters."""
    grade = SteelGrade.query.get_or_404(grade_id)
    ttt = TTTParameters.query.filter_by(steel_grade_id=grade_id).first()

    if ttt is None:
        flash('Create TTT parameters first.', 'warning')
        return redirect(url_for('ttt_cct.edit_parameters', grade_id=grade_id))

    form = CalibrationUploadForm()

    if form.validate_on_submit():
        import csv
        from app.services.phase_transformation.parameter_calibration import (
            calibrate_isothermal, calibrate_from_cct
        )

        # Parse CSV
        csv_data = form.csv_file.data.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(csv_data))

        data_points = []
        for row in reader:
            try:
                point = {
                    'temperature': float(row.get('temperature', 0)),
                    'time': float(row.get('time', 0)),
                    'fraction_transformed': float(row.get('fraction', row.get('fraction_transformed', 0))),
                }
                if form.test_type.data == 'continuous_cooling':
                    point['cooling_rate'] = float(row.get('cooling_rate', 0))
                    if 'start_temperature' in row:
                        point['start_temperature'] = float(row['start_temperature'])
                data_points.append(point)
            except (ValueError, KeyError):
                continue

        if len(data_points) < 3:
            flash('Insufficient data points (need at least 3).', 'danger')
            return redirect(url_for('ttt_cct.calibrate', grade_id=grade_id))

        # Store calibration data
        for dp in data_points:
            cal = TTTCalibrationData(
                ttt_parameters_id=ttt.id,
                test_type=form.test_type.data,
                phase=form.phase.data,
                temperature=dp['temperature'],
                time=dp['time'],
                fraction_transformed=dp['fraction_transformed'],
                cooling_rate=dp.get('cooling_rate'),
            )
            db.session.add(cal)

        # Calibrate
        try:
            phase = form.phase.data
            if form.test_type.data == 'isothermal':
                n_val, model_type, b_params = calibrate_isothermal(data_points, phase)
            else:
                n_val, model_type, b_params = calibrate_from_cct(data_points)

            # Update JMAK parameters
            jmak = ttt.jmak_parameters.filter_by(phase=phase).first()
            if jmak is None:
                jmak = JMAKParameters(ttt_parameters_id=ttt.id, phase=phase)
                db.session.add(jmak)

            jmak.n_value = n_val
            jmak.b_model_type = model_type
            jmak.set_b_params(b_params)
            if model_type == 'gaussian':
                jmak.nose_temperature = b_params.get('t_nose')

            ttt.data_source = 'calibrated'

            # Invalidate cached curves
            TTTCurve.query.filter_by(ttt_parameters_id=ttt.id).delete()

            db.session.commit()
            flash(f'Calibrated {phase}: n={n_val:.2f}, model={model_type}', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Calibration failed: {e}', 'danger')
            logger.exception("Calibration failed")

        return redirect(url_for('ttt_cct.view', grade_id=grade_id))

    return render_template('ttt_cct/calibration.html',
                           grade=grade, form=form)


# ---- Plot routes (return PNG images) ----

@ttt_cct_bp.route('/grade/<int:grade_id>/ttt-plot')
@login_required
def ttt_plot(grade_id):
    """Generate TTT diagram plot as PNG."""
    grade = SteelGrade.query.get_or_404(grade_id)
    predictor = PhasePredictor(grade)

    curves = predictor.get_ttt_curves()
    if not curves:
        return Response('No TTT data available', status=404)

    trans_temps = predictor.get_transformation_temps()

    from app.services import visualization
    plot_data = visualization.create_ttt_plot(
        curves=curves,
        transformation_temps=trans_temps,
        title=f'TTT Diagram - {grade.designation}'
    )

    response = Response(plot_data, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@ttt_cct_bp.route('/grade/<int:grade_id>/cct-plot')
@login_required
def cct_plot(grade_id):
    """Generate CCT diagram plot as PNG."""
    grade = SteelGrade.query.get_or_404(grade_id)
    predictor = PhasePredictor(grade)

    curves = predictor.get_cct_curves()
    if not curves:
        return Response('No CCT data available', status=404)

    trans_temps = predictor.get_transformation_temps()

    from app.services import visualization
    plot_data = visualization.create_cct_overlay_plot(
        times=None,
        temperatures=None,
        transformation_temps=trans_temps,
        curves=curves,
        title=f'CCT Diagram - {grade.designation}',
        standalone=True
    )

    response = Response(plot_data, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-cache'
    return response


# ---- JSON API routes ----

@ttt_cct_bp.route('/api/grade/<int:grade_id>/ttt-data')
@login_required
def api_ttt_data(grade_id):
    """Return TTT curve data as JSON."""
    grade = SteelGrade.query.get_or_404(grade_id)
    predictor = PhasePredictor(grade)
    curves = predictor.get_ttt_curves()
    temps = predictor.get_transformation_temps()
    return jsonify({
        'curves': curves,
        'transformation_temps': temps,
        'tier': predictor.tier,
    })


@ttt_cct_bp.route('/api/grade/<int:grade_id>/cct-data')
@login_required
def api_cct_data(grade_id):
    """Return CCT curve data as JSON."""
    grade = SteelGrade.query.get_or_404(grade_id)
    predictor = PhasePredictor(grade)
    curves = predictor.get_cct_curves()
    temps = predictor.get_transformation_temps()
    return jsonify({
        'curves': curves,
        'transformation_temps': temps,
        'tier': predictor.tier,
    })
