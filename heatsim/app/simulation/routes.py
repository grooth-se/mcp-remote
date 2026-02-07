"""Routes for heat treatment simulation."""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user

from app.extensions import db
from app.models import SteelGrade, PhaseDiagram, MeasuredData
from app.models.simulation import (
    Simulation, SimulationResult,
    STATUS_DRAFT, STATUS_READY, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
    GEOMETRY_TYPES, PROCESS_TYPES, DEFAULT_HTC,
    QUENCH_MEDIA, QUENCH_MEDIA_LABELS, AGITATION_LEVELS, AGITATION_LABELS,
    FURNACE_ATMOSPHERES, FURNACE_ATMOSPHERE_LABELS, calculate_quench_htc
)
from app.services import (
    Cylinder, Plate, Ring, create_geometry,
    create_quench_bc, create_heating_bc, create_transfer_bc,
    HeatSolver, MultiPhaseHeatSolver, SolverConfig,
    PhaseTracker,
    visualization
)
from app.services.tc_data_parser import parse_tc_csv, validate_tc_csv

from . import simulation_bp
from .forms import (
    SimulationForm, GeometryForm, SolverForm,
    HeatingPhaseForm, TransferPhaseForm, QuenchingPhaseForm, TemperingPhaseForm
)


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
            status=STATUS_DRAFT
        )

        # Set default geometry based on type
        if form.geometry_type.data == 'cylinder':
            sim.set_geometry({'radius': 0.05, 'length': 0.1})
        elif form.geometry_type.data == 'plate':
            sim.set_geometry({'thickness': 0.02, 'width': 0.1, 'length': 0.1})
        else:
            sim.set_geometry({'inner_radius': 0.02, 'outer_radius': 0.05, 'length': 0.1})

        # Set default solver config
        sim.set_solver_config({'n_nodes': 51, 'dt': 0.1, 'max_time': 1800})

        # Set default heat treatment config
        sim.set_ht_config(sim.create_default_ht_config())

        db.session.add(sim)
        db.session.commit()

        flash(f'Simulation "{sim.name}" created.', 'success')
        return redirect(url_for('simulation.setup', id=sim.id))

    return render_template('simulation/new.html', form=form)


@simulation_bp.route('/<int:id>/setup', methods=['GET', 'POST'])
@login_required
def setup(id):
    """Configure geometry and solver settings."""
    sim = Simulation.query.get_or_404(id)

    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    geometry_form = GeometryForm()
    solver_form = SolverForm()

    if request.method == 'GET':
        # Pre-populate forms
        geom = sim.geometry_dict
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
        solver_form.max_time.data = solver.get('max_time', 1800)
        solver_form.auto_dt.data = solver.get('auto_dt', True)

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

        # Update solver config
        max_time = float(request.form.get('max_time', 1800))
        auto_dt = 'auto_dt' in request.form

        # Calculate dt if auto mode is enabled (limit to ~20,000 time steps)
        if auto_dt:
            dt = max(0.1, max_time / 20000)
        else:
            dt = float(request.form.get('dt', 0.1))

        solver_config = {
            'n_nodes': int(request.form.get('n_nodes', 51)),
            'dt': dt,
            'max_time': max_time,
            'auto_dt': auto_dt
        }
        sim.set_solver_config(solver_config)

        db.session.commit()

        flash('Geometry and solver configured.', 'success')
        return redirect(url_for('simulation.heat_treatment', id=sim.id))

    return render_template(
        'simulation/setup.html',
        sim=sim,
        geometry_form=geometry_form,
        solver_form=solver_form
    )


@simulation_bp.route('/<int:id>/heat-treatment', methods=['GET', 'POST'])
@login_required
def heat_treatment(id):
    """Configure heat treatment phases."""
    sim = Simulation.query.get_or_404(id)

    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    # Initialize forms
    heating_form = HeatingPhaseForm(prefix='heating')
    transfer_form = TransferPhaseForm(prefix='transfer')
    quenching_form = QuenchingPhaseForm(prefix='quenching')
    tempering_form = TemperingPhaseForm(prefix='tempering')

    if request.method == 'GET':
        # Pre-populate from existing config
        ht = sim.ht_config
        if not ht:
            ht = sim.create_default_ht_config()

        # Heating phase
        h = ht.get('heating', {})
        heating_form.enabled.data = h.get('enabled', True)
        heating_form.initial_temperature.data = h.get('initial_temperature', 25.0)
        heating_form.target_temperature.data = h.get('target_temperature', 850.0)
        heating_form.hold_time.data = h.get('hold_time', 60.0)
        heating_form.furnace_atmosphere.data = h.get('furnace_atmosphere', 'air')
        # Furnace ramp settings
        heating_form.cold_furnace.data = h.get('cold_furnace', False)
        heating_form.furnace_start_temperature.data = h.get('furnace_start_temperature', 25.0)
        heating_form.furnace_ramp_rate.data = h.get('furnace_ramp_rate', 5.0)
        # End condition settings
        heating_form.end_condition.data = h.get('end_condition', 'equilibrium')
        heating_form.rate_threshold.data = h.get('rate_threshold', 1.0)
        heating_form.hold_time_after_trigger.data = h.get('hold_time_after_trigger', 30.0)
        heating_form.center_offset.data = h.get('center_offset', 3.0)
        # Heat transfer parameters
        heating_form.furnace_htc.data = h.get('furnace_htc', 25.0)
        heating_form.furnace_emissivity.data = h.get('furnace_emissivity', 0.85)
        heating_form.use_radiation.data = h.get('use_radiation', True)

        # Transfer phase
        t = ht.get('transfer', {})
        transfer_form.enabled.data = t.get('enabled', True)
        transfer_form.duration.data = t.get('duration', 10.0)
        transfer_form.ambient_temperature.data = t.get('ambient_temperature', 25.0)
        transfer_form.htc.data = t.get('htc', 10.0)
        transfer_form.emissivity.data = t.get('emissivity', 0.85)
        transfer_form.use_radiation.data = t.get('use_radiation', True)

        # Quenching phase
        q = ht.get('quenching', {})
        quenching_form.media.data = q.get('media', 'water')
        quenching_form.media_temperature.data = q.get('media_temperature', 25.0)
        quenching_form.agitation.data = q.get('agitation', 'moderate')
        quenching_form.htc_override.data = q.get('htc_override')
        quenching_form.duration.data = q.get('duration', 300.0)
        quenching_form.emissivity.data = q.get('emissivity', 0.3)
        quenching_form.use_radiation.data = q.get('use_radiation', False)

        # Tempering phase
        tp = ht.get('tempering', {})
        tempering_form.enabled.data = tp.get('enabled', False)
        tempering_form.temperature.data = tp.get('temperature', 550.0)
        tempering_form.hold_time.data = tp.get('hold_time', 120.0)
        # End condition settings
        tempering_form.end_condition.data = tp.get('end_condition', 'equilibrium')
        tempering_form.rate_threshold.data = tp.get('rate_threshold', 1.0)
        tempering_form.hold_time_after_trigger.data = tp.get('hold_time_after_trigger', 30.0)
        tempering_form.center_offset.data = tp.get('center_offset', 3.0)
        tempering_form.cooling_method.data = tp.get('cooling_method', 'air')
        tempering_form.htc.data = tp.get('htc', 25.0)
        tempering_form.emissivity.data = tp.get('emissivity', 0.85)

    if request.method == 'POST':
        # Build heat treatment config from form data
        ht_config = {
            'heating': {
                'enabled': 'heating-enabled' in request.form,
                'initial_temperature': float(request.form.get('heating-initial_temperature', 25)),
                'target_temperature': float(request.form.get('heating-target_temperature', 850)),
                'hold_time': float(request.form.get('heating-hold_time', 60)),
                'furnace_atmosphere': request.form.get('heating-furnace_atmosphere', 'air'),
                # Furnace ramp settings
                'cold_furnace': 'heating-cold_furnace' in request.form,
                'furnace_start_temperature': float(request.form.get('heating-furnace_start_temperature', 25)),
                'furnace_ramp_rate': float(request.form.get('heating-furnace_ramp_rate', 5)),
                # End condition settings
                'end_condition': request.form.get('heating-end_condition', 'equilibrium'),
                'rate_threshold': float(request.form.get('heating-rate_threshold', 1.0)),
                'hold_time_after_trigger': float(request.form.get('heating-hold_time_after_trigger', 30)),
                'center_offset': float(request.form.get('heating-center_offset', 3)),
                # Heat transfer parameters
                'furnace_htc': float(request.form.get('heating-furnace_htc', 25)),
                'furnace_emissivity': float(request.form.get('heating-furnace_emissivity', 0.85)),
                'use_radiation': 'heating-use_radiation' in request.form,
            },
            'transfer': {
                'enabled': 'transfer-enabled' in request.form,
                'duration': float(request.form.get('transfer-duration', 10)),
                'ambient_temperature': float(request.form.get('transfer-ambient_temperature', 25)),
                'htc': float(request.form.get('transfer-htc', 10)),
                'emissivity': float(request.form.get('transfer-emissivity', 0.85)),
                'use_radiation': 'transfer-use_radiation' in request.form,
            },
            'quenching': {
                'enabled': True,  # Always enabled
                'media': request.form.get('quenching-media', 'water'),
                'media_temperature': float(request.form.get('quenching-media_temperature', 25)),
                'agitation': request.form.get('quenching-agitation', 'moderate'),
                'htc_override': float(request.form.get('quenching-htc_override')) if request.form.get('quenching-htc_override') else None,
                'duration': float(request.form.get('quenching-duration', 300)),
                'emissivity': float(request.form.get('quenching-emissivity', 0.3)),
                'use_radiation': 'quenching-use_radiation' in request.form,
            },
            'tempering': {
                'enabled': 'tempering-enabled' in request.form,
                'temperature': float(request.form.get('tempering-temperature', 550)),
                'hold_time': float(request.form.get('tempering-hold_time', 120)),
                # End condition settings
                'end_condition': request.form.get('tempering-end_condition', 'equilibrium'),
                'rate_threshold': float(request.form.get('tempering-rate_threshold', 1.0)),
                'hold_time_after_trigger': float(request.form.get('tempering-hold_time_after_trigger', 30)),
                'center_offset': float(request.form.get('tempering-center_offset', 3)),
                'cooling_method': request.form.get('tempering-cooling_method', 'air'),
                'htc': float(request.form.get('tempering-htc', 25)),
                'emissivity': float(request.form.get('tempering-emissivity', 0.85)),
            },
        }

        sim.set_ht_config(ht_config)

        # Update legacy fields for compatibility
        sim.initial_temperature = ht_config['heating']['target_temperature']
        sim.ambient_temperature = ht_config['quenching']['media_temperature']

        sim.status = STATUS_READY
        db.session.commit()

        flash('Heat treatment configured successfully.', 'success')
        return redirect(url_for('simulation.view', id=sim.id))

    # Calculate effective HTC for display
    q_config = sim.ht_config.get('quenching', {}) if sim.ht_config else {}
    effective_htc = calculate_quench_htc(
        q_config.get('media', 'water'),
        q_config.get('agitation', 'moderate'),
        q_config.get('media_temperature', 25)
    )

    return render_template(
        'simulation/heat_treatment.html',
        sim=sim,
        heating_form=heating_form,
        transfer_form=transfer_form,
        quenching_form=quenching_form,
        tempering_form=tempering_form,
        effective_htc=effective_htc,
        quench_media=QUENCH_MEDIA,
        quench_media_labels=QUENCH_MEDIA_LABELS,
        agitation_levels=AGITATION_LEVELS,
        agitation_labels=AGITATION_LABELS,
        furnace_atmospheres=FURNACE_ATMOSPHERES,
        furnace_atmosphere_labels=FURNACE_ATMOSPHERE_LABELS
    )


@simulation_bp.route('/<int:id>')
@login_required
def view(id):
    """View simulation details and results."""
    sim = Simulation.query.get_or_404(id)
    results = sim.results.all()

    # Group results by type
    cooling_curves = [r for r in results if r.result_type in ('cooling_curve', 'full_cycle', 'heating_curve')]
    profiles = [r for r in results if r.result_type == 'temperature_profile']
    phases = [r for r in results if r.result_type == 'phase_fraction']
    rates = [r for r in results if r.result_type == 'cooling_rate']

    # Phase-specific T vs Time results
    heating_curves = [r for r in results if r.result_type == 'heating_curve' and r.phase == 'heating']
    quenching_curves = [r for r in results if r.result_type == 'cooling_curve' and r.phase == 'quenching']
    tempering_curves = [r for r in results if r.result_type in ('cooling_curve', 'heating_curve') and r.phase == 'tempering']

    # dT/dt plots grouped by phase
    dtdt_time_heating = [r for r in results if r.result_type == 'dTdt_vs_time' and r.phase == 'heating']
    dtdt_time_quenching = [r for r in results if r.result_type == 'dTdt_vs_time' and r.phase == 'quenching']
    dtdt_time_tempering = [r for r in results if r.result_type == 'dTdt_vs_time' and r.phase == 'tempering']
    dtdt_temp_heating = [r for r in results if r.result_type == 'dTdt_vs_temp' and r.phase == 'heating']
    dtdt_temp_quenching = [r for r in results if r.result_type == 'dTdt_vs_temp' and r.phase == 'quenching']
    dtdt_temp_tempering = [r for r in results if r.result_type == 'dTdt_vs_temp' and r.phase == 'tempering']

    # Get measured TC data for comparison, grouped by process step
    measured_data = sim.measured_data.all()
    measured_heating = [m for m in measured_data if m.process_step == 'heating']
    measured_quenching = [m for m in measured_data if m.process_step == 'quenching']
    measured_tempering = [m for m in measured_data if m.process_step == 'tempering']

    return render_template(
        'simulation/results.html',
        sim=sim,
        results=results,
        cooling_curves=cooling_curves,
        profiles=profiles,
        phases=phases,
        rates=rates,
        heating_curves=heating_curves,
        quenching_curves=quenching_curves,
        tempering_curves=tempering_curves,
        dtdt_time_heating=dtdt_time_heating,
        dtdt_time_quenching=dtdt_time_quenching,
        dtdt_time_tempering=dtdt_time_tempering,
        dtdt_temp_heating=dtdt_temp_heating,
        dtdt_temp_quenching=dtdt_temp_quenching,
        dtdt_temp_tempering=dtdt_temp_tempering,
        measured_data=measured_data,
        measured_heating=measured_heating,
        measured_quenching=measured_quenching,
        measured_tempering=measured_tempering
    )


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

        # Build solver config
        solver_config = SolverConfig.from_dict(sim.solver_dict)

        # Get material properties
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

        # Get heat treatment config
        ht_config = sim.ht_config
        if not ht_config:
            ht_config = sim.create_default_ht_config()

        # Create multi-phase solver
        solver = MultiPhaseHeatSolver(geometry, config=solver_config)
        solver.set_material(k_prop, cp_prop, density, emissivity)
        solver.configure_from_ht_config(ht_config)

        # Determine initial temperature
        heating_config = ht_config.get('heating', {})
        if heating_config.get('enabled', False):
            initial_temp = heating_config.get('initial_temperature', 25.0)
        else:
            initial_temp = heating_config.get('target_temperature', sim.initial_temperature or 850.0)

        # Run simulation
        result = solver.solve(initial_temperature=initial_temp)

        # Get phase diagram for transformation temps
        diagram = grade.phase_diagrams.first()
        trans_temps = diagram.temps_dict if diagram else {}

        # Store full heat treatment cycle result
        cycle_result = SimulationResult(
            simulation_id=sim.id,
            result_type='full_cycle',
            phase='full',
            location='center',
            t_800_500=result.t8_5
        )
        cycle_result.set_time_data(result.time.tolist())
        cycle_result.set_value_data(result.center_temp.tolist())

        # Create comprehensive plot with phase markers (4 radial positions)
        cycle_result.plot_image = visualization.create_heat_treatment_cycle_plot(
            result.time,
            result.temperature,
            phase_results=result.phase_results,
            title=f'Heat Treatment Cycle - {sim.name}',
            transformation_temps=trans_temps
        )
        db.session.add(cycle_result)

        # Store individual phase results with T vs Time plots
        if result.phase_results:
            for phase_result in result.phase_results:
                if not phase_result.time.size or len(phase_result.time) < 2:
                    continue

                pr = SimulationResult(
                    simulation_id=sim.id,
                    result_type='cooling_curve' if phase_result.phase_name in ('quenching', 'transfer', 'cooling') else 'heating_curve',
                    phase=phase_result.phase_name,
                    location='center',
                    t_800_500=phase_result.t8_5
                )
                pr.set_time_data(phase_result.absolute_time.tolist())
                pr.set_value_data(phase_result.center_temp.tolist())

                # Generate T vs Time plot for this phase
                if phase_result.temperature.size > 0:
                    pr.plot_image = visualization.create_heat_treatment_cycle_plot(
                        phase_result.time,
                        phase_result.temperature,
                        phase_results=None,
                        title=f'{phase_result.phase_name.title()} - {sim.name}',
                        transformation_temps=trans_temps
                    )
                db.session.add(pr)

        # Store temperature profile result
        profile_result = SimulationResult(
            simulation_id=sim.id,
            result_type='temperature_profile',
            phase='full',
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

        # Phase transformation prediction (based on quenching cooling)
        if diagram:
            tracker = PhaseTracker(diagram)
            phases = tracker.predict_phases(result.time, result.center_temp, result.t8_5)

            phase_result = SimulationResult(
                simulation_id=sim.id,
                result_type='phase_fraction',
                phase='full',
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
            phase='full',
            location='all'
        )
        rate_result.plot_image = visualization.create_cooling_rate_plot(
            result.time,
            result.center_temp,
            result.surface_temp,
            title=f'Cooling Rate - {sim.name}'
        )
        db.session.add(rate_result)

        # Generate dT/dt plots for heating and quenching phases
        if result.phase_results:
            for phase_result in result.phase_results:
                if phase_result.phase_name not in ('heating', 'quenching', 'tempering'):
                    continue
                if not phase_result.time.size or len(phase_result.time) < 3:
                    continue

                phase_label = phase_result.phase_name.title()

                # dT/dt vs Time plot
                dtdt_time_result = SimulationResult(
                    simulation_id=sim.id,
                    result_type='dTdt_vs_time',
                    phase=phase_result.phase_name,
                    location='all'
                )
                dtdt_time_result.plot_image = visualization.create_dTdt_vs_time_plot(
                    phase_result.time,
                    phase_result.temperature,
                    title=f'dT/dt vs Time ({phase_label}) - {sim.name}',
                    phase_name=phase_result.phase_name
                )
                db.session.add(dtdt_time_result)

                # dT/dt vs Temperature plot
                dtdt_temp_result = SimulationResult(
                    simulation_id=sim.id,
                    result_type='dTdt_vs_temp',
                    phase=phase_result.phase_name,
                    location='all'
                )
                dtdt_temp_result.plot_image = visualization.create_dTdt_vs_temperature_plot(
                    phase_result.time,
                    phase_result.temperature,
                    title=f'dT/dt vs Temperature ({phase_label}) - {sim.name}',
                    phase_name=phase_result.phase_name
                )
                db.session.add(dtdt_temp_result)

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
        sim.geometry_type = form.geometry_type.data

        db.session.commit()
        flash('Simulation updated.', 'success')
        return redirect(url_for('simulation.view', id=sim.id))

    return render_template('simulation/new.html', form=form, edit_mode=True, sim=sim)


@simulation_bp.route('/api/htc/<media>/<agitation>')
@login_required
def api_htc(media, agitation):
    """API endpoint to calculate effective HTC."""
    temp = request.args.get('temp', 25, type=float)
    htc = calculate_quench_htc(media, agitation, temp)
    return {'htc': htc}


# ============================================================================
# Measured TC Data Routes
# ============================================================================

@simulation_bp.route('/<int:id>/upload-tc', methods=['GET', 'POST'])
@login_required
def upload_tc_data(id):
    """Upload measured thermocouple data for comparison."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    if request.method == 'POST':
        if 'tc_file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(request.url)

        file = request.files['tc_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'danger')
            return redirect(request.url)

        try:
            # Read and parse file
            content = file.read().decode('utf-8')
            is_valid, msg = validate_tc_csv(content)
            if not is_valid:
                flash(f'Invalid file format: {msg}', 'danger')
                return redirect(request.url)

            data = parse_tc_csv(content)

            # Create MeasuredData record
            name = request.form.get('name', file.filename)
            description = request.form.get('description', '')
            process_step = request.form.get('process_step', 'full')

            measured = MeasuredData(
                simulation_id=sim.id,
                name=name,
                description=description,
                filename=file.filename,
                process_step=process_step,
                start_time=data['start_time'],
                end_time=data['end_time'],
                duration_seconds=data['duration_seconds'],
            )
            measured.times = data['times']
            measured.channels = data['channels']
            measured.channel_times = data.get('channel_times', {})
            measured.statistics = data['statistics']

            # Initialize channel labels
            labels = {ch: ch for ch in data['channels'].keys()}
            measured.channel_labels_dict = labels

            db.session.add(measured)
            db.session.commit()

            flash(f'Uploaded {measured.num_channels} channels with {measured.num_points} data points.', 'success')
            return redirect(url_for('simulation.configure_tc_data', id=sim.id, data_id=measured.id))

        except Exception as e:
            flash(f'Error parsing file: {str(e)}', 'danger')
            return redirect(request.url)

    # GET - show upload form
    existing_data = sim.measured_data.all()
    return render_template('simulation/upload_tc.html', sim=sim, existing_data=existing_data)


@simulation_bp.route('/<int:id>/tc-data/<int:data_id>/configure', methods=['GET', 'POST'])
@login_required
def configure_tc_data(id, data_id):
    """Configure channel labels for uploaded TC data."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    measured = MeasuredData.query.get_or_404(data_id)
    if measured.simulation_id != sim.id:
        flash('Data not found.', 'danger')
        return redirect(url_for('simulation.view', id=id))

    if request.method == 'POST':
        # Update channel labels
        labels = {}
        for channel in measured.available_channels:
            label = request.form.get(f'label_{channel}', channel)
            labels[channel] = label
        measured.channel_labels_dict = labels
        db.session.commit()

        flash('Channel labels updated.', 'success')
        return redirect(url_for('simulation.view', id=sim.id))

    return render_template('simulation/configure_tc.html', sim=sim, measured=measured)


@simulation_bp.route('/<int:id>/tc-data/<int:data_id>/delete', methods=['POST'])
@login_required
def delete_tc_data(id, data_id):
    """Delete uploaded TC data."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('simulation.index'))

    measured = MeasuredData.query.get_or_404(data_id)
    if measured.simulation_id != sim.id:
        flash('Data not found.', 'danger')
        return redirect(url_for('simulation.view', id=id))

    db.session.delete(measured)
    db.session.commit()
    flash('TC data deleted.', 'success')
    return redirect(url_for('simulation.view', id=sim.id))


@simulation_bp.route('/<int:id>/comparison-plot')
@login_required
def comparison_plot(id):
    """Generate comparison plot of simulation vs measured data."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    # Get measured data
    measured_list = sim.measured_data.all()
    if not measured_list:
        return Response('No measured data', status=404)

    # Get simulation results (main cycle plot)
    cycle_result = SimulationResult.query.filter_by(
        simulation_id=sim.id,
        result_type='full_cycle'
    ).first()

    if not cycle_result:
        # Fallback to cooling_curve
        cycle_result = SimulationResult.query.filter_by(
            simulation_id=sim.id,
            result_type='cooling_curve'
        ).first()

    if not cycle_result:
        return Response('No simulation results', status=404)

    # Generate comparison plot
    import numpy as np

    sim_times = np.array(cycle_result.time_array)
    sim_temps = np.array(cycle_result.value_array)

    # Prepare measured data
    measured_data = []
    for m in measured_list:
        for channel in m.available_channels:
            measured_data.append({
                'name': m.get_channel_label(channel),
                'times': m.times,
                'temps': m.channels[channel]
            })

    # Create comparison plot
    plot_data = visualization.create_comparison_plot(
        sim_times, sim_temps,
        measured_data,
        title=f'Simulation vs Measured - {sim.name}'
    )

    return Response(plot_data, mimetype='image/png')


@simulation_bp.route('/<int:id>/cycle-plot-with-tc')
@login_required
def cycle_plot_with_tc(id):
    """Generate main cycle plot with measured TC data overlaid."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    # Get simulation temperature data
    cycle_result = SimulationResult.query.filter_by(
        simulation_id=sim.id,
        result_type='full_cycle'
    ).first()

    if not cycle_result or not cycle_result.plot_image:
        return Response('No simulation results', status=404)

    # Check if there's measured data
    measured_list = sim.measured_data.all()
    if not measured_list:
        # Return original plot if no measured data
        return Response(cycle_result.plot_image, mimetype='image/png')

    # Need to regenerate plot with measured data
    # Get the temperature field from stored result
    import numpy as np
    import json

    # Get time and temperature data
    times = np.array(cycle_result.time_array)

    # We need the full temperature field - check if it's stored
    # For now, use stored plot data to extract or regenerate
    # Since we don't have full temp field stored, create comparison plot instead

    sim_temps = np.array(cycle_result.value_array)

    # Prepare measured data
    measured_data = []
    for m in measured_list:
        for channel in m.available_channels:
            measured_data.append({
                'name': m.get_channel_label(channel),
                'times': m.times,
                'temps': m.channels[channel]
            })

    # Create comparison plot
    plot_data = visualization.create_comparison_plot(
        times, sim_temps,
        measured_data,
        title=f'Temperature vs Time - {sim.name}'
    )

    return Response(plot_data, mimetype='image/png')


@simulation_bp.route('/<int:id>/measured-tc-plot')
@login_required
def measured_tc_plot(id):
    """Generate Temperature vs Time plot for measured TC data only."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    measured_list = sim.measured_data.all()
    if not measured_list:
        return Response('No measured data', status=404)

    # Prepare measured data with per-channel times
    measured_data = []
    for m in measured_list:
        for channel in m.available_channels:
            measured_data.append({
                'name': m.get_channel_label(channel),
                'times': m.get_channel_times(channel),
                'temps': m.channels[channel]
            })

    # Create plot for measured data only
    plot_data = visualization.create_measured_tc_plot(
        measured_data,
        title=f'Measured Temperature vs Time - {sim.name}'
    )

    return Response(plot_data, mimetype='image/png')


@simulation_bp.route('/<int:id>/measured-dtdt-plot')
@login_required
def measured_dtdt_plot(id):
    """Generate dT/dt vs Time plot for measured TC data."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    measured_list = sim.measured_data.all()
    if not measured_list:
        return Response('No measured data', status=404)

    # Prepare measured data with per-channel times
    measured_data = []
    for m in measured_list:
        for channel in m.available_channels:
            measured_data.append({
                'name': m.get_channel_label(channel),
                'times': m.get_channel_times(channel),
                'temps': m.channels[channel]
            })

    # Create dT/dt plot for measured data
    plot_data = visualization.create_measured_dtdt_plot(
        measured_data,
        title=f'Measured dT/dt vs Time - {sim.name}'
    )

    return Response(plot_data, mimetype='image/png')


@simulation_bp.route('/<int:id>/measured-dtdt-temp-plot')
@login_required
def measured_dtdt_temp_plot(id):
    """Generate dT/dt vs Temperature plot for measured TC data."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    measured_list = sim.measured_data.all()
    if not measured_list:
        return Response('No measured data', status=404)

    # Prepare measured data with per-channel times
    measured_data = []
    for m in measured_list:
        for channel in m.available_channels:
            measured_data.append({
                'name': m.get_channel_label(channel),
                'times': m.get_channel_times(channel),
                'temps': m.channels[channel]
            })

    # Create dT/dt vs Temperature plot for measured data
    plot_data = visualization.create_measured_dtdt_vs_temp_plot(
        measured_data,
        title=f'Measured dT/dt vs Temperature - {sim.name}'
    )

    return Response(plot_data, mimetype='image/png')


# ============================================================================
# Process Step Specific Measured Data Plots
# ============================================================================

def _get_measured_data_for_step(sim, process_step):
    """Helper to get measured data for a specific process step."""
    measured_list = [m for m in sim.measured_data.all() if m.process_step == process_step]
    if not measured_list:
        return None

    measured_data = []
    for m in measured_list:
        for channel in m.available_channels:
            measured_data.append({
                'name': m.get_channel_label(channel),
                'times': m.get_channel_times(channel),
                'temps': m.channels[channel]
            })
    return measured_data


@simulation_bp.route('/<int:id>/measured-tc-plot/<step>')
@login_required
def measured_tc_plot_step(id, step):
    """Generate Temperature vs Time plot for measured TC data for a specific process step."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    measured_data = _get_measured_data_for_step(sim, step)
    if not measured_data:
        return Response('No measured data', status=404)

    plot_data = visualization.create_measured_tc_plot(
        measured_data,
        title=f'Measured T vs Time ({step.title()})'
    )
    return Response(plot_data, mimetype='image/png')


@simulation_bp.route('/<int:id>/measured-dtdt-plot/<step>')
@login_required
def measured_dtdt_plot_step(id, step):
    """Generate dT/dt vs Time plot for measured TC data for a specific process step."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    measured_data = _get_measured_data_for_step(sim, step)
    if not measured_data:
        return Response('No measured data', status=404)

    plot_data = visualization.create_measured_dtdt_plot(
        measured_data,
        title=f'Measured dT/dt vs Time ({step.title()})'
    )
    return Response(plot_data, mimetype='image/png')


@simulation_bp.route('/<int:id>/measured-dtdt-temp-plot/<step>')
@login_required
def measured_dtdt_temp_plot_step(id, step):
    """Generate dT/dt vs Temperature plot for measured TC data for a specific process step."""
    sim = Simulation.query.get_or_404(id)
    if sim.user_id != current_user.id:
        return Response('Access denied', status=403)

    measured_data = _get_measured_data_for_step(sim, step)
    if not measured_data:
        return Response('No measured data', status=404)

    plot_data = visualization.create_measured_dtdt_vs_temp_plot(
        measured_data,
        title=f'Measured dT/dt vs Temperature ({step.title()})'
    )
    return Response(plot_data, mimetype='image/png')
