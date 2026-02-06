"""Routes for heat treatment simulation."""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user

from app.extensions import db
from app.models import SteelGrade, PhaseDiagram
from app.models.simulation import (
    Simulation, SimulationResult,
    STATUS_DRAFT, STATUS_READY, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
    GEOMETRY_TYPES, PROCESS_TYPES, DEFAULT_HTC
)
from app.services import (
    Cylinder, Plate, Ring, create_geometry,
    create_quench_bc,
    HeatSolver, SolverConfig,
    PhaseTracker,
    visualization
)

from . import simulation_bp
from .forms import SimulationForm, GeometryForm, SolverForm


@simulation_bp.route('/')
@login_required
def index():
    """List all simulations for current user."""
    simulations = Simulation.query.filter_by(user_id=current_user.id)\
        .order_by(Simulation.created_at.desc()).all()
    return render_template('simulation/index.html', simulations=simulations)


@simulation_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new simulation."""
    form = SimulationForm()
    form.steel_grade_id.choices = [
        (g.id, g.display_name) for g in SteelGrade.query.order_by(SteelGrade.designation).all()
    ]

    if form.validate_on_submit():
        sim = Simulation(
            name=form.name.data,
            description=form.description.data,
            steel_grade_id=form.steel_grade_id.data,
            user_id=current_user.id,
            geometry_type=form.geometry_type.data,
            process_type=form.process_type.data,
            initial_temperature=form.initial_temperature.data,
            ambient_temperature=form.ambient_temperature.data,
            status=STATUS_DRAFT
        )

        # Set default geometry based on type
        if form.geometry_type.data == 'cylinder':
            sim.set_geometry({'radius': 0.05, 'length': 0.1})
        elif form.geometry_type.data == 'plate':
            sim.set_geometry({'thickness': 0.02, 'width': 0.1, 'length': 0.1})
        else:
            sim.set_geometry({'inner_radius': 0.02, 'outer_radius': 0.05, 'length': 0.1})

        # Set default boundary conditions
        default_htc = DEFAULT_HTC.get(form.process_type.data, 1000)
        sim.set_boundary_conditions({'htc': default_htc, 'emissivity': 0.85})

        # Set default solver config
        sim.set_solver_config({'n_nodes': 51, 'dt': 0.1, 'max_time': 600})

        db.session.add(sim)
        db.session.commit()

        flash(f'Simulation "{sim.name}" created.', 'success')
        return redirect(url_for('simulation.setup', id=sim.id))

    return render_template('simulation/new.html', form=form)


@simulation_bp.route('/<int:id>/setup', methods=['GET', 'POST'])
@login_required
def setup(id):
    """Configure geometry and boundary conditions."""
    sim = Simulation.query.get_or_404(id)

    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    geometry_form = GeometryForm()
    solver_form = SolverForm()

    if request.method == 'GET':
        # Pre-populate forms
        geom = sim.geometry_dict
        bc = sim.bc_dict
        solver = sim.solver_dict

        if sim.geometry_type == 'cylinder':
            geometry_form.radius.data = geom.get('radius', 0.05) * 1000
            geometry_form.length.data = geom.get('length', 0.1) * 1000
        elif sim.geometry_type == 'plate':
            geometry_form.thickness.data = geom.get('thickness', 0.02) * 1000
            geometry_form.width.data = geom.get('width', 0.1) * 1000
            geometry_form.length.data = geom.get('length', 0.1) * 1000
        else:
            geometry_form.inner_radius.data = geom.get('inner_radius', 0.02) * 1000
            geometry_form.outer_radius.data = geom.get('outer_radius', 0.05) * 1000
            geometry_form.length.data = geom.get('length', 0.1) * 1000

        solver_form.n_nodes.data = solver.get('n_nodes', 51)
        solver_form.dt.data = solver.get('dt', 0.1)
        solver_form.max_time.data = solver.get('max_time', 600)
        solver_form.htc.data = bc.get('htc', DEFAULT_HTC.get(sim.process_type, 1000))
        solver_form.emissivity.data = bc.get('emissivity', 0.85)

    if request.method == 'POST':
        # Update geometry (convert mm to m)
        geom_config = {}
        if sim.geometry_type == 'cylinder':
            geom_config = {
                'radius': float(request.form.get('radius', 50)) / 1000,
                'length': float(request.form.get('length', 100)) / 1000
            }
        elif sim.geometry_type == 'plate':
            geom_config = {
                'thickness': float(request.form.get('thickness', 20)) / 1000,
                'width': float(request.form.get('width', 100)) / 1000,
                'length': float(request.form.get('length', 100)) / 1000
            }
        else:
            geom_config = {
                'inner_radius': float(request.form.get('inner_radius', 20)) / 1000,
                'outer_radius': float(request.form.get('outer_radius', 50)) / 1000,
                'length': float(request.form.get('length', 100)) / 1000
            }

        sim.set_geometry(geom_config)

        # Update boundary conditions
        bc_config = {
            'htc': float(request.form.get('htc') or DEFAULT_HTC.get(sim.process_type, 1000)),
            'emissivity': float(request.form.get('emissivity', 0.85))
        }
        sim.set_boundary_conditions(bc_config)

        # Update solver config
        solver_config = {
            'n_nodes': int(request.form.get('n_nodes', 51)),
            'dt': float(request.form.get('dt', 0.1)),
            'max_time': float(request.form.get('max_time', 600))
        }
        sim.set_solver_config(solver_config)

        sim.status = STATUS_READY
        db.session.commit()

        flash('Simulation configured successfully.', 'success')
        return redirect(url_for('simulation.view', id=sim.id))

    return render_template(
        'simulation/setup.html',
        sim=sim,
        geometry_form=geometry_form,
        solver_form=solver_form,
        default_htc=DEFAULT_HTC
    )


@simulation_bp.route('/<int:id>')
@login_required
def view(id):
    """View simulation details and results."""
    sim = Simulation.query.get_or_404(id)
    results = sim.results.all()

    return render_template('simulation/results.html', sim=sim, results=results)


@simulation_bp.route('/<int:id>/run', methods=['POST'])
@login_required
def run(id):
    """Execute the simulation."""
    sim = Simulation.query.get_or_404(id)

    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    if sim.status not in [STATUS_READY, STATUS_COMPLETED, STATUS_FAILED]:
        flash('Simulation is not ready to run.', 'warning')
        return redirect(url_for('simulation.view', id=id))

    try:
        # Clear previous results
        SimulationResult.query.filter_by(simulation_id=sim.id).delete()

        sim.status = STATUS_RUNNING
        sim.started_at = datetime.utcnow()
        sim.error_message = None
        db.session.commit()

        # Build geometry
        geometry = create_geometry(sim.geometry_type, sim.geometry_dict)

        # Build boundary condition
        bc_config = sim.bc_dict
        bc = create_quench_bc(
            sim.process_type,
            ambient_temp=sim.ambient_temperature,
            emissivity=bc_config.get('emissivity', 0.85),
            custom_htc=bc_config.get('htc')
        )

        # Build solver config
        solver_config = SolverConfig.from_dict(sim.solver_dict)

        # Create solver
        solver = HeatSolver(geometry, bc, config=solver_config)

        # Set material properties
        grade = sim.steel_grade
        k_prop = grade.get_property('thermal_conductivity')
        cp_prop = grade.get_property('specific_heat')
        rho_prop = grade.get_property('density')
        emiss_prop = grade.get_property('emissivity')

        density = 7850
        if rho_prop:
            density = rho_prop.data_dict.get('value', 7850)

        emissivity = 0.85
        if emiss_prop:
            emissivity = emiss_prop.data_dict.get('value', 0.85)

        solver.set_material(k_prop, cp_prop, density, emissivity)

        # Run simulation
        result = solver.solve(sim.initial_temperature)

        # Get phase diagram for transformation temps
        diagram = grade.phase_diagrams.first()
        trans_temps = diagram.temps_dict if diagram else {}

        # Store cooling curve result
        cooling_result = SimulationResult(
            simulation_id=sim.id,
            result_type='cooling_curve',
            location='center',
            t_800_500=result.t8_5
        )
        cooling_result.set_time_data(result.time.tolist())
        cooling_result.set_value_data(result.center_temp.tolist())

        cooling_result.plot_image = visualization.create_cooling_curve_plot(
            result.time,
            result.center_temp,
            result.surface_temp,
            result.quarter_temp,
            title=f'Cooling Curves - {sim.name}',
            transformation_temps=trans_temps
        )
        db.session.add(cooling_result)

        # Store temperature profile result
        profile_result = SimulationResult(
            simulation_id=sim.id,
            result_type='temperature_profile',
            location='all'
        )

        # Generate profile plot at selected times
        n_times = len(result.time)
        time_indices = [0, n_times//4, n_times//2, 3*n_times//4, n_times-1]
        time_indices = [i for i in time_indices if i < n_times]

        is_cylindrical = sim.geometry_type in ['cylinder', 'ring']
        profile_result.plot_image = visualization.create_temperature_profile_plot(
            result.positions,
            result.temperature,
            result.time,
            time_indices,
            title=f'Temperature Profile - {sim.name}',
            is_cylindrical=is_cylindrical
        )
        db.session.add(profile_result)

        # Phase transformation prediction
        if diagram:
            tracker = PhaseTracker(diagram)
            phases = tracker.predict_phases(result.time, result.center_temp, result.t8_5)

            phase_result = SimulationResult(
                simulation_id=sim.id,
                result_type='phase_fraction',
                location='center'
            )
            phase_result.set_phase_fractions(phases.to_dict())
            phase_result.plot_image = visualization.create_phase_fraction_plot(
                phases.to_dict(),
                title=f'Predicted Phase Fractions - {sim.name}'
            )
            db.session.add(phase_result)

        # Cooling rate plot
        rate_result = SimulationResult(
            simulation_id=sim.id,
            result_type='cooling_rate',
            location='all'
        )
        rate_result.plot_image = visualization.create_cooling_rate_plot(
            result.time,
            result.center_temp,
            result.surface_temp,
            title=f'Cooling Rate - {sim.name}'
        )
        db.session.add(rate_result)

        sim.status = STATUS_COMPLETED
        sim.completed_at = datetime.utcnow()
        db.session.commit()

        flash('Simulation completed successfully!', 'success')

    except Exception as e:
        sim.status = STATUS_FAILED
        sim.error_message = str(e)
        db.session.commit()
        flash(f'Simulation failed: {str(e)}', 'danger')

    return redirect(url_for('simulation.view', id=id))


@simulation_bp.route('/<int:id>/result/<int:result_id>/image')
@login_required
def result_image(id, result_id):
    """Serve result plot image."""
    result = SimulationResult.query.get_or_404(result_id)

    if result.simulation_id != id or not result.plot_image:
        return '', 404

    return Response(result.plot_image, mimetype='image/png')


@simulation_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete simulation."""
    sim = Simulation.query.get_or_404(id)

    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    name = sim.name
    db.session.delete(sim)
    db.session.commit()

    flash(f'Simulation "{name}" deleted.', 'success')
    return redirect(url_for('simulation.index'))


@simulation_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit simulation basic info."""
    sim = Simulation.query.get_or_404(id)

    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    form = SimulationForm(obj=sim)
    form.steel_grade_id.choices = [
        (g.id, g.display_name) for g in SteelGrade.query.order_by(SteelGrade.designation).all()
    ]

    if form.validate_on_submit():
        sim.name = form.name.data
        sim.description = form.description.data
        sim.steel_grade_id = form.steel_grade_id.data
        sim.process_type = form.process_type.data
        sim.initial_temperature = form.initial_temperature.data
        sim.ambient_temperature = form.ambient_temperature.data

        # Update default HTC if process changed
        bc = sim.bc_dict
        bc['htc'] = DEFAULT_HTC.get(form.process_type.data, bc.get('htc', 1000))
        sim.set_boundary_conditions(bc)

        db.session.commit()
        flash('Simulation updated.', 'success')
        return redirect(url_for('simulation.view', id=sim.id))

    return render_template('simulation/new.html', form=form, edit_mode=True, sim=sim)
