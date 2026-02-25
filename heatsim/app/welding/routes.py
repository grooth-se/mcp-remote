"""Routes for welding simulation."""
import json
import logging
from datetime import datetime
from pathlib import Path

from flask import (
    render_template, redirect, url_for, flash, request, jsonify,
    current_app, send_file
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.weld_project import (
    WeldProject, WeldString, WeldResult,
    STATUS_DRAFT, STATUS_CONFIGURED, STATUS_QUEUED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
    STRING_PENDING, STRING_COMPLETED,
    RESULT_THERMAL_CYCLE, RESULT_COOLING_RATE,
)
from app.models.material import SteelGrade

from .forms import (
    WeldProjectForm, WeldStringForm, QuickAddStringsForm, RunSimulationForm,
    HAZAnalysisForm, PreheatForm, GoldakAnalysisForm, GoldakMultiPassForm,
)
from . import welding_bp

logger = logging.getLogger(__name__)


@welding_bp.route('/')
@login_required
def index():
    """List all weld projects."""
    projects = WeldProject.query.filter_by(user_id=current_user.id)\
        .order_by(WeldProject.created_at.desc()).all()
    return render_template('welding/index.html', projects=projects)


@welding_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create a new weld project."""
    form = WeldProjectForm()

    if form.validate_on_submit():
        project = WeldProject(
            name=form.name.data,
            description=form.description.data,
            user_id=current_user.id,
            steel_grade_id=form.steel_grade_id.data if form.steel_grade_id.data != 0 else None,
            process_type=form.process_type.data,
            preheat_temperature=form.preheat_temperature.data,
            interpass_temperature=form.interpass_temperature.data,
            interpass_time_default=form.interpass_time_default.data,
            default_heat_input=form.default_heat_input.data,
            default_travel_speed=form.default_travel_speed.data,
            default_solidification_temp=form.default_solidification_temp.data,
            status=STATUS_DRAFT,
        )

        # Handle CAD file upload
        if form.cad_file.data:
            cad_file = form.cad_file.data
            project.cad_filename = cad_file.filename
            project.cad_file = cad_file.read()

            # Determine format from extension
            ext = Path(cad_file.filename).suffix.lower()
            if ext in ['.stp', '.step']:
                project.cad_format = 'step'
            elif ext in ['.igs', '.iges']:
                project.cad_format = 'iges'
            elif ext == '.stl':
                project.cad_format = 'stl'

        db.session.add(project)
        db.session.commit()

        flash(f'Project "{project.name}" created successfully.', 'success')
        return redirect(url_for('welding.configure', id=project.id))

    return render_template('welding/new.html', form=form)


@welding_bp.route('/<int:id>')
@login_required
def view(id):
    """View weld project details and results."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    # Get all results
    results = project.results.order_by(WeldResult.created_at.desc()).all()

    # Separate by type
    thermal_cycles = [r for r in results if r.result_type == RESULT_THERMAL_CYCLE]
    cooling_rates = [r for r in results if r.result_type == RESULT_COOLING_RATE]

    return render_template(
        'welding/view.html',
        project=project,
        results=results,
        thermal_cycles=thermal_cycles,
        cooling_rates=cooling_rates,
    )


@welding_bp.route('/<int:id>/configure', methods=['GET', 'POST'])
@login_required
def configure(id):
    """Configure weld string sequence."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    if project.status == STATUS_RUNNING:
        flash('Cannot configure while simulation is running.', 'warning')
        return redirect(url_for('welding.view', id=id))

    quick_form = QuickAddStringsForm()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'quick_add' and quick_form.validate():
            # Add multiple strings quickly
            num_layers = quick_form.num_layers.data
            strings_per_layer = quick_form.strings_per_layer.data

            string_number = project.strings.count() + 1
            for layer in range(1, num_layers + 1):
                for pos in range(1, strings_per_layer + 1):
                    string = WeldString(
                        project_id=project.id,
                        string_number=string_number,
                        layer=layer,
                        position_in_layer=pos,
                        name=f'Layer {layer} - String {pos}',
                        status=STRING_PENDING,
                    )
                    db.session.add(string)
                    string_number += 1

            project.total_strings = project.strings.count()
            db.session.commit()
            flash(f'Added {num_layers * strings_per_layer} strings.', 'success')

        elif action == 'reorder':
            # Handle reordering from JSON data
            order_data = request.form.get('order_data')
            if order_data:
                try:
                    new_order = json.loads(order_data)
                    for item in new_order:
                        string = WeldString.query.get(item['id'])
                        if string and string.project_id == project.id:
                            string.string_number = item['order']
                    db.session.commit()
                    flash('String order updated.', 'success')
                except (json.JSONDecodeError, KeyError) as e:
                    flash(f'Invalid order data: {e}', 'danger')

        elif action == 'mark_configured':
            if project.strings.count() > 0:
                project.status = STATUS_CONFIGURED
                project.total_strings = project.strings.count()
                db.session.commit()
                flash('Project configured and ready to run.', 'success')
                return redirect(url_for('welding.view', id=id))
            else:
                flash('Add at least one string before marking as configured.', 'warning')

    strings = project.strings.order_by(WeldString.string_number).all()
    return render_template(
        'welding/configure.html',
        project=project,
        strings=strings,
        quick_form=quick_form,
    )


@welding_bp.route('/<int:id>/string/new', methods=['GET', 'POST'])
@login_required
def string_new(id):
    """Add a new string to the project."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    form = WeldStringForm()

    # Set default string number
    if request.method == 'GET':
        form.string_number.data = project.strings.count() + 1

    if form.validate_on_submit():
        string = WeldString(
            project_id=project.id,
            string_number=form.string_number.data,
            name=form.name.data,
            body_name=form.body_name.data,
            layer=form.layer.data,
            position_in_layer=form.position_in_layer.data,
            heat_input=form.heat_input.data,
            travel_speed=form.travel_speed.data,
            interpass_time=form.interpass_time.data,
            initial_temp_mode=form.initial_temp_mode.data,
            initial_temperature=form.initial_temperature.data,
            solidification_temp=form.solidification_temp.data,
            simulation_duration=form.simulation_duration.data,
            status=STRING_PENDING,
        )
        db.session.add(string)
        project.total_strings = project.strings.count() + 1
        db.session.commit()

        flash(f'String "{string.display_name}" added.', 'success')
        return redirect(url_for('welding.configure', id=id))

    return render_template('welding/string_edit.html', form=form, project=project, string=None)


@welding_bp.route('/<int:id>/string/<int:sid>', methods=['GET', 'POST'])
@login_required
def string_edit(id, sid):
    """Edit a weld string."""
    project = WeldProject.query.get_or_404(id)
    string = WeldString.query.get_or_404(sid)

    if project.user_id != current_user.id or string.project_id != id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    form = WeldStringForm(obj=string)

    if form.validate_on_submit():
        form.populate_obj(string)
        db.session.commit()
        flash(f'String "{string.display_name}" updated.', 'success')
        return redirect(url_for('welding.configure', id=id))

    return render_template('welding/string_edit.html', form=form, project=project, string=string)


@welding_bp.route('/<int:id>/string/<int:sid>/delete', methods=['POST'])
@login_required
def string_delete(id, sid):
    """Delete a weld string."""
    project = WeldProject.query.get_or_404(id)
    string = WeldString.query.get_or_404(sid)

    if project.user_id != current_user.id or string.project_id != id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    if project.status == STATUS_RUNNING:
        flash('Cannot delete strings while simulation is running.', 'warning')
        return redirect(url_for('welding.configure', id=id))

    db.session.delete(string)

    # Renumber remaining strings
    remaining = project.strings.order_by(WeldString.string_number).all()
    for i, s in enumerate(remaining, 1):
        s.string_number = i

    project.total_strings = len(remaining)
    db.session.commit()

    flash('String deleted.', 'success')
    return redirect(url_for('welding.configure', id=id))


@welding_bp.route('/<int:id>/run', methods=['GET', 'POST'])
@login_required
def run(id):
    """Start or view simulation run."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    form = RunSimulationForm()

    if request.method == 'POST' and form.validate():
        if not project.can_run:
            flash('Project is not ready to run. Please configure strings first.', 'warning')
            return redirect(url_for('welding.configure', id=id))

        # Reset any previous run state
        for string in project.strings.all():
            string.status = STRING_PENDING
            string.started_at = None
            string.completed_at = None
            string.error_message = None

        # Delete previous results
        for result in project.results.all():
            db.session.delete(result)

        # Enqueue for background execution
        use_mock = form.use_mock_solver.data
        project.status = STATUS_QUEUED
        project.progress_percent = 0.0
        project.current_string = 0
        project.error_message = None
        # Store mock preference as a flag in progress_message (worker reads + clears it)
        project.progress_message = 'mock:' if use_mock else 'Queued...'
        db.session.commit()

        flash('Simulation queued.', 'info')
        return redirect(url_for('welding.progress', id=id))

    return render_template('welding/run.html', form=form, project=project)


@welding_bp.route('/<int:id>/progress')
@login_required
def progress(id):
    """View simulation progress."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    strings = project.strings.order_by(WeldString.string_number).all()
    return render_template('welding/progress.html', project=project, strings=strings)


@welding_bp.route('/<int:id>/progress/status')
@login_required
def progress_status(id):
    """Get current progress status (JSON for AJAX polling)."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    strings_data = []
    for string in project.strings.order_by(WeldString.string_number).all():
        strings_data.append({
            'id': string.id,
            'number': string.string_number,
            'name': string.display_name,
            'status': string.status,
            'duration': string.duration_seconds,
        })

    from app.services.job_queue import get_queue_position
    queue_position = get_queue_position('weld', project.id)

    return jsonify({
        'status': project.status,
        'current_string': project.current_string,
        'total_strings': project.total_strings,
        'progress_percent': project.progress_percent,
        'progress_message': project.progress_message,
        'queue_position': queue_position,
        'strings': strings_data,
    })


@welding_bp.route('/<int:id>/results')
@login_required
def results(id):
    """View all simulation results."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    all_results = project.results.order_by(WeldResult.string_id, WeldResult.result_type).all()

    # Group by result type
    thermal_cycles = [r for r in all_results if r.result_type == RESULT_THERMAL_CYCLE]
    cooling_rates = [r for r in all_results if r.result_type == RESULT_COOLING_RATE]

    return render_template(
        'welding/results.html',
        project=project,
        results=all_results,
        thermal_cycles=thermal_cycles,
        cooling_rates=cooling_rates,
    )


@welding_bp.route('/<int:id>/plot/<plot_type>')
@login_required
def plot(id, plot_type):
    """Generate and return a plot image."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    from app.services.comsol.visualization import WeldVisualization
    viz = WeldVisualization()

    results = project.results.all()
    img_data = None

    if plot_type == 'thermal_cycles':
        thermal_results = [r for r in results if r.result_type == RESULT_THERMAL_CYCLE]
        img_data = viz.create_thermal_cycle_plot(thermal_results, title=f'{project.name} - Thermal Cycles')

    elif plot_type == 'cooling_rates':
        cooling_results = [r for r in results if r.result_type == RESULT_COOLING_RATE]
        img_data = viz.create_cct_overlay_plot(cooling_results, title=f'{project.name} - Cooling Rates')

    elif plot_type == 'phases':
        thermal_results = [r for r in results if r.result_type == RESULT_THERMAL_CYCLE]
        img_data = viz.create_phase_fraction_plot(thermal_results, title=f'{project.name} - Phase Fractions')

    elif plot_type == 'summary':
        img_data = viz.create_summary_table_image(project, results)

    # HAZ and Preheat plots (Phase 14)
    if plot_type == 'haz_cross_section':
        haz_data = _get_haz_data(project)
        if haz_data:
            from app.services.visualization import create_haz_cross_section_plot
            img_data = create_haz_cross_section_plot(haz_data)

    elif plot_type == 'peak_temp_profile':
        haz_data = _get_haz_data(project)
        if haz_data:
            from app.services.visualization import create_peak_temperature_profile_plot
            img_data = create_peak_temperature_profile_plot(
                haz_data['distances_mm'],
                haz_data['peak_temperatures'],
                haz_data.get('zone_boundaries'),
            )

    elif plot_type == 'hardness_traverse':
        haz_data = _get_haz_data(project)
        if haz_data:
            from app.services.visualization import create_hardness_traverse_plot
            img_data = create_hardness_traverse_plot(
                haz_data['distances_mm'],
                haz_data['hardness_profile'],
                haz_data.get('zone_boundaries'),
            )

    elif plot_type == 'haz_thermal_cycles':
        haz_data = _get_haz_data(project)
        if haz_data and haz_data.get('thermal_cycles'):
            from app.services.visualization import create_haz_thermal_cycle_comparison_plot
            img_data = create_haz_thermal_cycle_comparison_plot(
                haz_data['thermal_cycles'],
                title=f'{project.name} - HAZ Thermal Cycles',
            )

    elif plot_type == 'preheat_summary':
        preheat_data = _get_preheat_data(project)
        if preheat_data:
            from app.services.visualization import create_preheat_summary_plot
            img_data = create_preheat_summary_plot(preheat_data)

    # Goldak plots (Phase 15)
    elif plot_type == 'goldak_temperature_field':
        goldak_data = _get_goldak_data(project)
        if goldak_data:
            from app.services.visualization import create_goldak_temperature_heatmap
            img_data = create_goldak_temperature_heatmap(goldak_data)

    elif plot_type == 'goldak_weld_pool':
        goldak_data = _get_goldak_data(project)
        if goldak_data:
            from app.services.visualization import create_goldak_weld_pool_plot
            img_data = create_goldak_weld_pool_plot(goldak_data)

    elif plot_type == 'goldak_thermal_cycles':
        goldak_data = _get_goldak_data(project)
        if goldak_data and goldak_data.get('probe_thermal_cycles'):
            from app.services.visualization import create_goldak_thermal_cycle_plot
            img_data = create_goldak_thermal_cycle_plot(
                goldak_data['probe_thermal_cycles'],
                title=f'{project.name} — Goldak Thermal Cycles',
            )

    elif plot_type == 'goldak_vs_rosenthal':
        comparison_data = _get_goldak_rosenthal_comparison(project)
        if comparison_data:
            from app.services.visualization import create_goldak_rosenthal_comparison_plot
            img_data = create_goldak_rosenthal_comparison_plot(comparison_data)

    if img_data:
        from io import BytesIO
        return send_file(BytesIO(img_data), mimetype='image/png')

    return jsonify({'error': 'Plot generation failed'}), 500


def _get_haz_data(project: WeldProject) -> dict:
    """Compute HAZ analysis data for a project (cached in session-like manner)."""
    try:
        from app.services.rosenthal_solver import RosenthalSolver
        from app.services.haz_predictor import HAZPredictor

        solver = RosenthalSolver.from_weld_project(project)

        composition = None
        phase_diagram = None
        if project.steel_grade:
            composition = getattr(project.steel_grade, 'composition', None)
            phase_diagram = getattr(project.steel_grade, 'phase_diagram', None)

        predictor = HAZPredictor(solver, composition, phase_diagram)
        result = predictor.predict()
        return result.to_dict()
    except Exception as e:
        logger.warning(f"HAZ analysis failed: {e}")
        return {}


def _get_preheat_data(project: WeldProject) -> dict:
    """Compute preheat data for a project."""
    try:
        if not project.steel_grade or not getattr(project.steel_grade, 'composition', None):
            return {}

        from app.services.preheat_calculator import PreheatCalculator
        calc = PreheatCalculator(project.steel_grade.composition)
        result = calc.calculate(
            heat_input=project.default_heat_input,
            thickness=20.0,
            hydrogen='B',
            restraint='medium',
        )
        return result.to_dict()
    except Exception as e:
        logger.warning(f"Preheat calculation failed: {e}")
        return {}


@welding_bp.route('/<int:id>/haz', methods=['GET', 'POST'])
@login_required
def haz_analysis(id):
    """HAZ analysis page."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    form = HAZAnalysisForm()
    haz_data = None
    passes_limit = None

    if form.validate_on_submit() or request.method == 'GET':
        try:
            from app.services.rosenthal_solver import RosenthalSolver
            from app.services.haz_predictor import HAZPredictor

            solver = RosenthalSolver.from_weld_project(project)

            composition = None
            phase_diagram = None
            if project.steel_grade:
                composition = getattr(project.steel_grade, 'composition', None)
                phase_diagram = getattr(project.steel_grade, 'phase_diagram', None)

            predictor = HAZPredictor(solver, composition, phase_diagram)

            max_dist = form.max_distance_mm.data or 20.0
            n_pts = form.n_points.data or 50
            z_m = (form.depth_z_mm.data or 0.0) / 1000.0
            hardness_limit = form.hardness_limit.data or 350.0

            result = predictor.predict(
                n_points=n_pts,
                max_distance_mm=max_dist,
                z=z_m,
                hardness_limit=hardness_limit,
            )
            haz_data = result.to_dict()
            passes_limit = result.passes_hardness_limit(hardness_limit)

        except Exception as e:
            flash(f'HAZ analysis error: {e}', 'danger')
            logger.exception("HAZ analysis failed")

    return render_template(
        'welding/haz.html',
        project=project,
        form=form,
        haz_data=haz_data,
        passes_limit=passes_limit,
    )


@welding_bp.route('/<int:id>/preheat', methods=['GET', 'POST'])
@login_required
def preheat(id):
    """Preheat calculator page."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    form = PreheatForm()
    preheat_data = None

    if not project.steel_grade or not getattr(project.steel_grade, 'composition', None):
        flash('Steel grade with composition data is required for preheat calculation.', 'warning')
        return redirect(url_for('welding.view', id=id))

    if form.validate_on_submit() or request.method == 'GET':
        try:
            from app.services.preheat_calculator import PreheatCalculator

            calc = PreheatCalculator(project.steel_grade.composition)

            thickness = form.plate_thickness_mm.data or 20.0
            hydrogen = form.hydrogen_level.data or 'B'
            restraint = form.restraint.data or 'medium'

            result = calc.calculate(
                heat_input=project.default_heat_input,
                thickness=thickness,
                hydrogen=hydrogen,
                restraint=restraint,
                applied_preheat=project.preheat_temperature,
            )
            preheat_data = result.to_dict()

        except Exception as e:
            flash(f'Preheat calculation error: {e}', 'danger')
            logger.exception("Preheat calculation failed")

    return render_template(
        'welding/preheat.html',
        project=project,
        form=form,
        preheat_data=preheat_data,
    )


@welding_bp.route('/<int:id>/animation')
@login_required
def animation(id):
    """Serve the time-lapse animation video."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    # Find animation result
    anim_result = project.results.filter_by(result_type='animation').first()

    if anim_result and anim_result.animation_filename:
        anim_path = Path(anim_result.animation_filename)
        if anim_path.exists():
            return send_file(str(anim_path), mimetype='video/mp4')

    return jsonify({'error': 'Animation not available'}), 404


@welding_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete a weld project."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    if project.status == STATUS_RUNNING:
        flash('Cannot delete project while simulation is running.', 'warning')
        return redirect(url_for('welding.view', id=id))

    name = project.name
    db.session.delete(project)
    db.session.commit()

    flash(f'Project "{name}" deleted.', 'success')
    return redirect(url_for('welding.index'))


@welding_bp.route('/<int:id>/duplicate', methods=['POST'])
@login_required
def duplicate(id):
    """Duplicate a weld project."""
    original = WeldProject.query.get_or_404(id)

    if original.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    # Create copy
    new_project = WeldProject(
        name=f"{original.name} (Copy)",
        description=original.description,
        user_id=current_user.id,
        steel_grade_id=original.steel_grade_id,
        process_type=original.process_type,
        preheat_temperature=original.preheat_temperature,
        interpass_temperature=original.interpass_temperature,
        interpass_time_default=original.interpass_time_default,
        default_heat_input=original.default_heat_input,
        default_travel_speed=original.default_travel_speed,
        default_solidification_temp=original.default_solidification_temp,
        cad_filename=original.cad_filename,
        cad_file=original.cad_file,
        cad_format=original.cad_format,
        status=STATUS_DRAFT,
    )
    db.session.add(new_project)
    db.session.flush()

    # Copy strings
    for string in original.strings.all():
        new_string = WeldString(
            project_id=new_project.id,
            string_number=string.string_number,
            name=string.name,
            body_name=string.body_name,
            layer=string.layer,
            position_in_layer=string.position_in_layer,
            heat_input=string.heat_input,
            travel_speed=string.travel_speed,
            interpass_time=string.interpass_time,
            initial_temp_mode=string.initial_temp_mode,
            initial_temperature=string.initial_temperature,
            solidification_temp=string.solidification_temp,
            simulation_duration=string.simulation_duration,
            status=STRING_PENDING,
        )
        db.session.add(new_string)

    new_project.total_strings = original.total_strings
    db.session.commit()

    flash(f'Project duplicated as "{new_project.name}".', 'success')
    return redirect(url_for('welding.configure', id=new_project.id))


# ---- Phase 15: Goldak Analysis Routes ----

def _get_goldak_data(project: WeldProject, form_data=None) -> dict:
    """Run Goldak analysis with default or form parameters."""
    try:
        from app.services.goldak_solver import GoldakSolver, GoldakSolverConfig

        config = GoldakSolverConfig(ny=41, nz=31, dt=0.05, total_time=120.0)

        b_override = None
        c_override = None
        a_f_override = None
        a_r_override = None

        if form_data:
            if form_data.get('grid_ny'):
                config.ny = form_data['grid_ny']
            if form_data.get('grid_nz'):
                config.nz = form_data['grid_nz']
            if form_data.get('simulation_duration'):
                config.total_time = form_data['simulation_duration']
            b_override = form_data.get('pool_half_width_mm')
            if b_override:
                b_override /= 1000.0
            c_override = form_data.get('penetration_depth_mm')
            if c_override:
                c_override /= 1000.0
            a_f_override = form_data.get('front_length_mm')
            if a_f_override:
                a_f_override /= 1000.0
            a_r_override = form_data.get('rear_length_mm')
            if a_r_override:
                a_r_override /= 1000.0

        solver = GoldakSolver.from_weld_project(
            project, config=config,
            b_override=b_override, c_override=c_override,
            a_f_override=a_f_override, a_r_override=a_r_override,
        )
        result = solver.solve()
        return result.to_dict()
    except Exception as e:
        logger.warning(f"Goldak analysis failed: {e}")
        return {}


def _get_goldak_rosenthal_comparison(project: WeldProject) -> dict:
    """Run both Goldak and Rosenthal and build comparison."""
    try:
        from app.services.goldak_solver import GoldakSolver, GoldakSolverConfig
        from app.services.rosenthal_solver import RosenthalSolver
        import numpy as np

        config = GoldakSolverConfig(ny=41, nz=31, dt=0.05, total_time=120.0)
        solver = GoldakSolver.from_weld_project(project, config=config)
        result = solver.solve()

        ros = RosenthalSolver.from_weld_project(project)

        # Surface distances (positive half)
        ny_mid = len(solver.y) // 2
        distances_m = solver.y[ny_mid:]
        distances_mm = distances_m * 1000

        ros_peak = ros.peak_temperature_at_distance(distances_m, z=0.0)
        goldak_peak = result.peak_temperature_map[0, ny_mid:]

        # HAZ widths
        ros_haz = {}
        goldak_haz = {}
        for zone, temp in [('fusion', 1500), ('cghaz', 1100), ('fghaz', 900), ('ichaz', 727)]:
            ros_haz[zone] = ros.haz_boundary_distance(temp, z=0.0) * 1000
            idx = np.where(goldak_peak < temp)[0]
            if len(idx) > 0 and idx[0] > 0:
                goldak_haz[zone] = float(distances_mm[idx[0]])
            else:
                goldak_haz[zone] = 0.0

        return {
            'distances_mm': distances_mm.tolist(),
            'goldak_peak_temps': goldak_peak.tolist(),
            'rosenthal_peak_temps': ros_peak.tolist(),
            'goldak_haz_widths': goldak_haz,
            'rosenthal_haz_widths': ros_haz,
        }
    except Exception as e:
        logger.warning(f"Goldak/Rosenthal comparison failed: {e}")
        return {}


@welding_bp.route('/<int:id>/goldak', methods=['GET', 'POST'])
@login_required
def goldak_analysis(id):
    """Goldak heat source analysis page."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    form = GoldakAnalysisForm()
    goldak_data = None
    comparison_data = None
    pool_estimate = None

    # Show estimated pool params
    from app.services.goldak_solver import estimate_pool_params
    pool_estimate = estimate_pool_params(
        project.default_heat_input or 1.5,
        project.process_type or 'mig_mag'
    )

    if form.validate_on_submit():
        form_data = {
            'pool_half_width_mm': form.pool_half_width_mm.data,
            'penetration_depth_mm': form.penetration_depth_mm.data,
            'front_length_mm': form.front_length_mm.data,
            'rear_length_mm': form.rear_length_mm.data,
            'grid_ny': form.grid_ny.data,
            'grid_nz': form.grid_nz.data,
            'simulation_duration': form.simulation_duration.data,
        }
        goldak_data = _get_goldak_data(project, form_data)

        if form.compare_with_rosenthal.data:
            comparison_data = _get_goldak_rosenthal_comparison(project)

        if not goldak_data:
            flash('Goldak analysis failed. Check parameters.', 'danger')

    return render_template(
        'welding/goldak.html',
        project=project, form=form,
        goldak_data=goldak_data,
        comparison_data=comparison_data,
        pool_estimate=pool_estimate,
    )


@welding_bp.route('/<int:id>/goldak/multipass', methods=['GET', 'POST'])
@login_required
def goldak_multipass(id):
    """Goldak multi-pass simulation page."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('welding.index'))

    if not project.total_strings or project.total_strings == 0:
        flash('Configure weld strings before running multi-pass simulation.', 'warning')
        return redirect(url_for('welding.configure', id=id))

    form = GoldakMultiPassForm()

    if form.validate_on_submit():
        # Enqueue for background execution
        project.status = STATUS_QUEUED
        project.progress_percent = 0.0
        project.error_message = None
        project.started_at = None
        project.completed_at = None
        project.progress_message = (
            f'goldak:{form.grid_resolution.data}'
            f':{str(form.compare_methods.data).lower()}'
        )
        db.session.commit()
        flash('Goldak multi-pass simulation queued.', 'info')
        return redirect(url_for('welding.goldak_multipass', id=id))

    # Check if goldak multipass is running/queued
    is_goldak_running = (
        project.status in (STATUS_QUEUED, STATUS_RUNNING)
        and (project.progress_message or '').startswith(('goldak', 'Pass ', 'Initializing Goldak'))
    )

    # Load stored result if available
    stored_result = project.results.filter_by(result_type='goldak_multipass').first()
    multipass_data = json.loads(stored_result.time_data) if stored_result else None

    return render_template(
        'welding/goldak_multipass.html',
        project=project, form=form,
        multipass_data=multipass_data,
        is_goldak_running=is_goldak_running,
    )


@welding_bp.route('/<int:id>/goldak/multipass/status')
@login_required
def goldak_multipass_status(id):
    """Get goldak multipass progress status (JSON for AJAX polling)."""
    project = WeldProject.query.get_or_404(id)

    if project.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    from app.services.job_queue import get_queue_position
    queue_position = get_queue_position('weld', project.id) if project.status == STATUS_QUEUED else None

    return jsonify({
        'status': project.status,
        'progress_percent': project.progress_percent,
        'progress_message': project.progress_message,
        'queue_position': queue_position,
        'error_message': project.error_message,
    })
