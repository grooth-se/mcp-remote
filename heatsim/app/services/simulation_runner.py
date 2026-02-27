"""Simulation runner for background job execution.

Extracted from app/simulation/routes.py to run inside the worker thread
without a Flask request context (no flash() calls).
"""
import logging
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import AuditLog, SimulationSnapshot
from app.models.simulation import (
    Simulation, SimulationResult,
    STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
    GEOMETRY_CAD,
)
from app.services import (
    create_geometry, MultiPhaseHeatSolver, SolverConfig,
    PhaseTracker, predict_hardness_profile, visualization,
)
from app.services.hardness_predictor import HardnessPredictor, POSITION_KEYS
from app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)


def run_heat_treatment(simulation_id: int) -> None:
    """Execute a heat treatment simulation.

    This function is called from the worker thread with an app context
    already pushed.  It must NOT use flash() or any request-context helpers.
    """
    sim = db.session.get(Simulation, simulation_id)
    if sim is None:
        logger.error("Simulation %d not found", simulation_id)
        return

    snapshot = None
    try:
        # Create immutable snapshot of all inputs
        snapshot = SnapshotService.create_snapshot(sim)

        sim.status = STATUS_RUNNING
        sim.started_at = datetime.utcnow()
        sim.error_message = None
        db.session.commit()
        AuditLog.log('run_simulation', resource_type='simulation',
                      resource_id=sim.id, resource_name=sim.name)

        # Check solver type: COMSOL or built-in
        solver_type = sim.solver_dict.get('solver_type', 'builtin')

        if solver_type == 'comsol':
            _run_comsol(sim, snapshot)
            return

        # ---------- Built-in 1D FDM path ----------
        _run_builtin(sim, snapshot)

    except Exception as e:
        sim.status = STATUS_FAILED
        sim.error_message = str(e)
        if snapshot:
            SnapshotService.finalize_snapshot(snapshot, 'failed', str(e))
        db.session.commit()
        logger.exception("Simulation %d failed: %s", simulation_id, e)


def _run_comsol(sim: Simulation, snapshot: SimulationSnapshot) -> None:
    """Run simulation using COMSOL solver path.

    Generates the same rich result set as the builtin path:
    full_cycle plot, per-phase curves, cooling rate, phase prediction,
    hardness prediction, CCT overlay, and VTK snapshots/animation.
    """
    from app.services.comsol import (
        COMSOLClient, MockCOMSOLClient, COMSOLNotAvailableError,
        HeatTreatmentSolver, MockHeatTreatmentSolver,
        HeatTreatmentResultsExtractor
    )
    from app.services.comsol.client import get_shared_client
    import numpy as np

    client = None
    use_real_comsol = False
    try:
        # Try real COMSOL (singleton client), fall back to mock
        try:
            client = get_shared_client()
            if not client.is_available:
                raise COMSOLNotAvailableError("mph not available")
            comsol_solver = HeatTreatmentSolver(client, sim, snapshot)
            use_real_comsol = True
            logger.info("Using real COMSOL solver")
        except (COMSOLNotAvailableError, Exception) as e:
            logger.info("COMSOL not available (%s), using mock solver", e)
            comsol_solver = MockHeatTreatmentSolver(sim, snapshot)

        # Run COMSOL/mock solver
        solver_results = comsol_solver.solve()

        # Extract and store results (cooling curves, VTK, full_cycle plot, etc.)
        extractor = HeatTreatmentResultsExtractor(sim, snapshot)
        extractor.extract_and_store(solver_results, db_session=db.session)

        # --- Phase prediction (same three-tier as builtin) ---
        grade = sim.steel_grade
        diagram = grade.phase_diagrams.first() if grade else None
        trans_temps = diagram.temps_dict if diagram else {}

        # Build combined time/center arrays for prediction
        combined_times, combined_center, combined_surface = extractor._combine_phases(solver_results)

        tracker = None
        phases = None
        t85 = solver_results.get('summary', {}).get('t_800_500')

        if combined_times is not None and combined_center is not None:
            if diagram or (grade and grade.composition):
                from app.services.phase_transformation import PhasePredictor
                predictor = PhasePredictor(grade)
                if predictor.is_available:
                    phases = predictor.predict_phases_scheil(
                        combined_times, combined_center, t85
                    )
                    logger.info("COMSOL: Phase prediction via JMAK/Scheil for %s",
                                grade.designation)
                else:
                    if diagram:
                        tracker = PhaseTracker(diagram)
                        phases = tracker.predict_phases(
                            combined_times, combined_center, t85
                        )

                if phases:
                    phase_result_obj = SimulationResult(
                        simulation_id=sim.id,
                        snapshot_id=snapshot.id,
                        result_type='phase_fraction',
                        phase='full',
                        location='center',
                    )
                    phase_result_obj.set_phase_fractions(phases.to_dict())
                    phase_result_obj.plot_image = visualization.create_phase_fraction_plot(
                        phases.to_dict(),
                        title=f'Predicted Phase Fractions - {sim.name}'
                    )
                    db.session.add(phase_result_obj)

            # --- Hardness prediction ---
            if diagram and grade and grade.composition:
                try:
                    # Build 2D temperature array for hardness predictor
                    if combined_surface is not None:
                        temp_2d = np.column_stack([combined_center, combined_surface])
                    else:
                        temp_2d = combined_center.reshape(-1, 1)

                    hardness_result = predict_hardness_profile(
                        composition=grade.composition,
                        temperatures=temp_2d,
                        times=combined_times,
                        phase_tracker=tracker,
                    )

                    hardness_sim_result = SimulationResult(
                        simulation_id=sim.id,
                        snapshot_id=snapshot.id,
                        result_type='hardness_prediction',
                        phase='full',
                        location='all',
                    )

                    # Tempering hardness
                    ht_config = sim.ht_config or {}
                    tempering_cfg = ht_config.get('tempering', {})
                    if tempering_cfg.get('enabled') and grade.composition:
                        hp_c = grade.composition.hollomon_jaffe_c or 20.0
                        temp_c = tempering_cfg.get('temperature', 550)
                        hold_min = tempering_cfg.get('hold_time', 60)
                        hp = HardnessPredictor(grade.composition)
                        hjp_val = 0.0
                        for pos_key in POSITION_KEYS:
                            hv_q = hardness_result.hardness_hv.get(pos_key, 0)
                            if hv_q > 0:
                                hv_t, hjp_val = hp.tempered_hardness(hv_q, temp_c, hold_min, hp_c)
                                hardness_result.tempered_hardness_hv[pos_key] = round(hv_t, 1)
                                hrc_t = hp.hv_to_hrc(hv_t)
                                hardness_result.tempered_hardness_hrc[pos_key] = round(hrc_t, 1) if hrc_t else None
                        hardness_result.hollomon_jaffe_parameter = round(hjp_val, 0)
                        hardness_result.tempering_temperature = temp_c
                        hardness_result.tempering_time = hold_min

                    hardness_sim_result.set_data(hardness_result.to_dict())
                    hardness_sim_result.plot_image = visualization.create_hardness_profile_plot(
                        hardness_result,
                        title=f'Predicted Hardness - {sim.name}'
                    )
                    db.session.add(hardness_sim_result)
                except Exception as e:
                    logger.warning('COMSOL: Hardness prediction failed: %s', e)

            # --- CCT overlay ---
            try:
                from app.simulation.routes import _get_cct_curves_for_grade
                cct_curves = _get_cct_curves_for_grade(grade, diagram)

                if cct_curves and combined_center is not None:
                    if combined_surface is not None:
                        temp_for_cct = np.column_stack([combined_center, combined_surface])
                    else:
                        temp_for_cct = combined_center

                    cct_result = SimulationResult(
                        simulation_id=sim.id,
                        snapshot_id=snapshot.id,
                        result_type='cct_overlay',
                        phase='full',
                        location='all',
                    )
                    cct_result.plot_image = visualization.create_cct_overlay_plot(
                        combined_times, temp_for_cct, trans_temps,
                        curves=cct_curves,
                        title=f'CCT Overlay - {sim.name}'
                    )
                    db.session.add(cct_result)
            except Exception as e:
                logger.warning('COMSOL: CCT overlay failed: %s', e)

        # Update simulation status
        sim.status = STATUS_COMPLETED
        sim.completed_at = datetime.utcnow()

        # Update snapshot with summary
        summary = solver_results.get('summary', {})
        snapshot.t_800_500 = summary.get('t_800_500')
        SnapshotService.finalize_snapshot(snapshot, 'completed')
        new_results = SimulationResult.query.filter_by(snapshot_id=snapshot.id).all()
        SnapshotService.update_summary(snapshot, new_results)
        db.session.commit()

    finally:
        # Clean up COMSOL model to free server memory (keep server running)
        if use_real_comsol and client is not None:
            try:
                if hasattr(comsol_solver, '_model') and comsol_solver._model is not None:
                    client.remove_model(comsol_solver._model)
            except Exception as e:
                logger.warning("Failed to clean up COMSOL model: %s", e)


def _run_builtin(sim: Simulation, snapshot: SimulationSnapshot) -> None:
    """Run simulation using built-in 1D FDM solver."""
    # Build geometry (use equivalent geometry for CAD types)
    if sim.geometry_type == GEOMETRY_CAD:
        equiv_type = sim.cad_equivalent_type or 'cylinder'
        equiv_params = sim.cad_equivalent_geometry_dict
        geometry = create_geometry(equiv_type, equiv_params)
    else:
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
        snapshot_id=snapshot.id,
        result_type='full_cycle',
        phase='full',
        location='center',
        t_800_500=float(result.t8_5) if result.t8_5 is not None else None
    )
    cycle_result.set_time_data(result.time.tolist())
    cycle_result.set_value_data(result.center_temp.tolist())

    # Store multi-position temperature data for CCT overlay
    n_pos = result.temperature.shape[1] if result.temperature.ndim > 1 else 1
    if n_pos > 1:
        idx_center = 0
        idx_one_third = n_pos // 3
        idx_two_thirds = 2 * n_pos // 3
        idx_surface = n_pos - 1
        multi_pos_data = {
            'positions': ['center', 'one_third', 'two_thirds', 'surface'],
            'center': result.temperature[:, idx_center].tolist(),
            'one_third': result.temperature[:, idx_one_third].tolist(),
            'two_thirds': result.temperature[:, idx_two_thirds].tolist(),
            'surface': result.temperature[:, idx_surface].tolist(),
        }
        cycle_result.set_data(multi_pos_data)

    # Build furnace/ambient temperature list for plotting (with ramp info)
    furnace_temps = []
    if result.phase_results:
        for pr in result.phase_results:
            if pr.time.size < 2:
                continue

            temp = None
            phase_name = pr.phase_name
            cold_furnace = False
            furnace_start_temp = None
            ramp_rate = 0

            if phase_name == 'heating':
                heating_cfg = ht_config.get('heating', {})
                temp = heating_cfg.get('target_temperature')
                cold_furnace = heating_cfg.get('cold_furnace', False)
                furnace_start_temp = heating_cfg.get('furnace_start_temperature', 25.0)
                ramp_rate = heating_cfg.get('furnace_ramp_rate', 0)
            elif phase_name == 'transfer':
                temp = ht_config.get('transfer', {}).get('ambient_temperature')
            elif phase_name == 'quenching':
                temp = ht_config.get('quenching', {}).get('media_temperature')
            elif phase_name == 'tempering':
                tempering_cfg = ht_config.get('tempering', {})
                temp = tempering_cfg.get('temperature')
                cold_furnace = tempering_cfg.get('cold_furnace', False)
                furnace_start_temp = tempering_cfg.get('furnace_start_temperature', 25.0)
                ramp_rate = tempering_cfg.get('furnace_ramp_rate', 0)
            elif phase_name == 'cooling':
                temp = ht_config.get('transfer', {}).get('ambient_temperature', 25.0)

            if temp is not None:
                furnace_temps.append({
                    'start_time': pr.start_time,
                    'end_time': pr.end_time,
                    'temperature': temp,
                    'phase_name': phase_name,
                    'cold_furnace': cold_furnace,
                    'furnace_start_temperature': furnace_start_temp if furnace_start_temp else temp,
                    'furnace_ramp_rate': ramp_rate
                })

    # Create comprehensive plot with phase markers (4 radial positions)
    cycle_result.plot_image = visualization.create_heat_treatment_cycle_plot(
        result.time,
        result.temperature,
        phase_results=result.phase_results,
        title=f'Heat Treatment Cycle - {sim.name}',
        transformation_temps=trans_temps,
        furnace_temps=furnace_temps
    )
    db.session.add(cycle_result)

    # Store individual phase results with T vs Time plots
    if result.phase_results:
        for phase_result in result.phase_results:
            if not phase_result.time.size or len(phase_result.time) < 2:
                continue

            pr = SimulationResult(
                simulation_id=sim.id,
                snapshot_id=snapshot.id,
                result_type='cooling_curve' if phase_result.phase_name in ('quenching', 'transfer', 'cooling') else 'heating_curve',
                phase=phase_result.phase_name,
                location='center',
                t_800_500=float(phase_result.t8_5) if phase_result.t8_5 is not None else None
            )
            pr.set_time_data(phase_result.absolute_time.tolist())
            pr.set_value_data(phase_result.center_temp.tolist())

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
        snapshot_id=snapshot.id,
        result_type='temperature_profile',
        phase='full',
        location='all'
    )

    n_times = len(result.time)
    time_indices = [0, n_times//4, n_times//2, 3*n_times//4, n_times-1]
    time_indices = [i for i in time_indices if i < n_times]

    is_cylindrical = sim.geometry_type in ['cylinder', 'ring', 'hollow_cylinder']
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
    # Use PhasePredictor with three-tier fallback: JMAK Scheil > simplified PhaseTracker
    tracker = None
    phases = None
    if diagram or grade.composition:
        from app.services.phase_transformation import PhasePredictor
        predictor = PhasePredictor(grade)
        if predictor.is_available:
            # Tier 2: JMAK/Scheil prediction
            phases = predictor.predict_phases_scheil(result.time, result.center_temp, result.t8_5)
            logger.info("Phase prediction via JMAK/Scheil for %s", grade.designation)
        else:
            # Tier 3: Simplified CCT-based (original PhaseTracker)
            if diagram:
                tracker = PhaseTracker(diagram)
                phases = tracker.predict_phases(result.time, result.center_temp, result.t8_5)

        if phases:
            phase_result_obj = SimulationResult(
                simulation_id=sim.id,
                snapshot_id=snapshot.id,
                result_type='phase_fraction',
                phase='full',
                location='center'
            )
            phase_result_obj.set_phase_fractions(phases.to_dict())
            phase_result_obj.plot_image = visualization.create_phase_fraction_plot(
                phases.to_dict(),
                title=f'Predicted Phase Fractions - {sim.name}'
            )
            db.session.add(phase_result_obj)

    # Hardness prediction (requires composition and phase diagram)
    if diagram and grade.composition:
        try:
            hardness_result = predict_hardness_profile(
                composition=grade.composition,
                temperatures=result.temperature,
                times=result.time,
                phase_tracker=tracker
            )

            hardness_sim_result = SimulationResult(
                simulation_id=sim.id,
                snapshot_id=snapshot.id,
                result_type='hardness_prediction',
                phase='full',
                location='all'
            )
            # Tempering hardness calculation
            tempering_cfg = ht_config.get('tempering', {})
            if tempering_cfg.get('enabled') and grade.composition:
                hp_c = grade.composition.hollomon_jaffe_c or 20.0
                temp_c = tempering_cfg.get('temperature', 550)
                hold_min = tempering_cfg.get('hold_time', 60)
                predictor = HardnessPredictor(grade.composition)
                hjp_val = 0.0
                for pos_key in POSITION_KEYS:
                    hv_q = hardness_result.hardness_hv.get(pos_key, 0)
                    if hv_q > 0:
                        hv_t, hjp_val = predictor.tempered_hardness(hv_q, temp_c, hold_min, hp_c)
                        hardness_result.tempered_hardness_hv[pos_key] = round(hv_t, 1)
                        hrc_t = predictor.hv_to_hrc(hv_t)
                        hardness_result.tempered_hardness_hrc[pos_key] = round(hrc_t, 1) if hrc_t else None
                hardness_result.hollomon_jaffe_parameter = round(hjp_val, 0)
                hardness_result.tempering_temperature = temp_c
                hardness_result.tempering_time = hold_min

            hardness_sim_result.set_data(hardness_result.to_dict())
            hardness_sim_result.plot_image = visualization.create_hardness_profile_plot(
                hardness_result,
                title=f'Predicted Hardness - {sim.name}'
            )
            db.session.add(hardness_sim_result)
        except Exception as e:
            logger.warning('Hardness prediction failed: %s', e)

    # Cooling rate plot
    rate_result = SimulationResult(
        simulation_id=sim.id,
        snapshot_id=snapshot.id,
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
                snapshot_id=snapshot.id,
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
                snapshot_id=snapshot.id,
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

    # Generate absorbed power plots for heating and tempering phases
    if result.phase_results:
        import numpy as np

        # Calculate mass from geometry
        mass = geometry.volume * density  # kg

        # Create Cp interpolation function
        def get_cp_at_temp(temp):
            """Get specific heat at given temperature."""
            if cp_prop:
                if cp_prop.property_type == 'constant':
                    return cp_prop.data_dict.get('value', 500.0)
                elif cp_prop.property_type == 'curve':
                    from app.services.property_evaluator import evaluate_property
                    val = evaluate_property(cp_prop, temperature=temp)
                    return val if val else 500.0
            return 500.0

        for phase_result in result.phase_results:
            if phase_result.phase_name not in ('heating', 'tempering'):
                continue
            if not phase_result.time.size or len(phase_result.time) < 3:
                continue

            phase_label = phase_result.phase_name.title()

            center_temp = phase_result.center_temp
            cp_values = np.array([get_cp_at_temp(t) for t in center_temp])

            power_result = SimulationResult(
                simulation_id=sim.id,
                snapshot_id=snapshot.id,
                result_type='absorbed_power',
                phase=phase_result.phase_name,
                location='all'
            )
            power_result.plot_image = visualization.create_absorbed_power_plot(
                phase_result.time,
                phase_result.temperature,
                mass=mass,
                cp_values=cp_values,
                title=f'Absorbed Power ({phase_label}) - {sim.name}',
                phase_name=phase_result.phase_name
            )
            db.session.add(power_result)

    sim.status = STATUS_COMPLETED
    sim.completed_at = datetime.utcnow()

    # Finalize snapshot with summary metrics
    SnapshotService.finalize_snapshot(snapshot, 'completed')
    new_results = SimulationResult.query.filter_by(snapshot_id=snapshot.id).all()
    SnapshotService.update_summary(snapshot, new_results)
    db.session.commit()
