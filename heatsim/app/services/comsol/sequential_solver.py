"""Sequential solver for multi-pass welding simulation.

Executes weld string simulations in sequence, managing temperature transfer
between passes and tracking progress.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, TYPE_CHECKING

from .client import COMSOLClient, COMSOLError
from .model_builder import WeldModelBuilder
from .results_extractor import ResultsExtractor

if TYPE_CHECKING:
    from app.models.weld_project import WeldProject, WeldString, WeldResult

logger = logging.getLogger(__name__)


class SequentialSolver:
    """Runs sequential string-by-string weld simulation.

    Manages the complete simulation workflow:
    1. Create base model from project configuration
    2. For each string in sequence:
       - Calculate initial temperature from previous results
       - Activate string domain in model
       - Run transient simulation
       - Extract and store results
    3. Generate project-level results and animations

    Parameters
    ----------
    client : COMSOLClient
        Connected COMSOL client instance
    builder : WeldModelBuilder
        Model builder for COMSOL operations
    results_folder : str
        Path to store result files
    """

    def __init__(self, client: COMSOLClient, builder: WeldModelBuilder = None,
                 results_folder: str = 'data/results'):
        """Initialize sequential solver.

        Parameters
        ----------
        client : COMSOLClient
            Connected COMSOL client instance
        builder : WeldModelBuilder, optional
            Model builder (created if not provided)
        results_folder : str
            Path to store result files
        """
        self.client = client
        self.builder = builder or WeldModelBuilder(client)
        self.extractor = ResultsExtractor(results_folder)
        self.results_folder = Path(results_folder)
        self.results_folder.mkdir(parents=True, exist_ok=True)

        self._model = None
        self._cancelled = False
        self._all_results: List['WeldResult'] = []

    def run_project(self, project: 'WeldProject',
                    progress_callback: Optional[Callable[[int, int, str], None]] = None,
                    db_session=None) -> List['WeldResult']:
        """Run full simulation sequence for a weld project.

        Parameters
        ----------
        project : WeldProject
            Weld project to simulate
        progress_callback : callable, optional
            Callback function(current_string, total_strings, message)
            Called after each string completion
        db_session : Session, optional
            Database session for committing updates

        Returns
        -------
        list of WeldResult
            All generated results from the simulation

        Raises
        ------
        COMSOLError
            If simulation fails
        """
        from app.models.weld_project import (
            STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
            STRING_PENDING, STRING_RUNNING, STRING_COMPLETED, STRING_FAILED
        )

        self._cancelled = False
        self._all_results = []

        # Update project status
        project.status = STATUS_RUNNING
        project.started_at = datetime.utcnow()
        project.current_string = 0
        project.progress_percent = 0.0
        project.progress_message = "Initializing COMSOL model..."
        if db_session:
            db_session.commit()

        try:
            # Create base model
            logger.info(f"Creating base model for project: {project.name}")
            self._model = self.builder.create_base_model(project)

            # Save initial model
            model_path = self.results_folder / f"project_{project.id}" / "model.mph"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            self.client.save_model(self._model, str(model_path))
            project.comsol_model_path = str(model_path)

            # Get all strings in order
            strings = list(project.strings.order_by('string_number').all())
            total = len(strings)
            project.total_strings = total

            if total == 0:
                raise COMSOLError("No weld strings defined in project")

            logger.info(f"Starting simulation of {total} strings")

            # Track previous results for temperature calculation
            prev_temps: Dict[str, float] = {}
            global_time = 0.0

            # Simulate each string in sequence
            for idx, string in enumerate(strings):
                if self._cancelled:
                    project.status = STATUS_FAILED
                    project.error_message = "Simulation cancelled by user"
                    break

                # Update progress
                project.current_string = idx + 1
                project.progress_percent = (idx / total) * 100
                project.progress_message = f"Simulating string {idx + 1} of {total}..."
                if db_session:
                    db_session.commit()

                if progress_callback:
                    progress_callback(idx + 1, total, f"String {idx + 1}/{total}")

                # Run single string simulation
                try:
                    string_results = self._simulate_string(
                        string, prev_temps, global_time, db_session
                    )
                    self._all_results.extend(string_results)

                    # Update global time for next string
                    global_time += string.simulation_duration + string.effective_interpass_time

                    # Update prev_temps from results
                    for result in string_results:
                        if result.result_type == 'temperature_field':
                            prev_temps[string.body_name] = result.peak_temperature or 1500.0

                except Exception as e:
                    logger.error(f"String {string.string_number} failed: {e}")
                    string.status = STRING_FAILED
                    string.error_message = str(e)
                    if db_session:
                        db_session.commit()
                    raise

            # Simulation completed successfully
            if not self._cancelled:
                project.status = STATUS_COMPLETED
                project.progress_percent = 100.0
                project.progress_message = "Simulation completed"
                project.completed_at = datetime.utcnow()

                # Generate project-level results (animations, combined plots)
                self._generate_project_results(project, db_session)

            if db_session:
                db_session.commit()

            logger.info(f"Project {project.name} completed with {len(self._all_results)} results")
            return self._all_results

        except Exception as e:
            logger.error(f"Project simulation failed: {e}")
            project.status = STATUS_FAILED
            project.error_message = str(e)
            if db_session:
                db_session.commit()
            raise COMSOLError(f"Project simulation failed: {e}")

    def _simulate_string(self, string: 'WeldString',
                         prev_temps: Dict[str, float],
                         global_time: float,
                         db_session=None) -> List['WeldResult']:
        """Simulate a single weld string.

        Parameters
        ----------
        string : WeldString
            Weld string to simulate
        prev_temps : dict
            Temperature field from previous strings
        global_time : float
            Global simulation time at start of this string
        db_session : Session, optional
            Database session

        Returns
        -------
        list of WeldResult
            Results from this string simulation
        """
        from app.models.weld_project import (
            STRING_RUNNING, STRING_COMPLETED, STRING_FAILED
        )

        logger.info(f"Simulating string {string.string_number}: {string.display_name}")

        string.status = STRING_RUNNING
        string.started_at = datetime.utcnow()
        string.simulation_start_time = global_time
        if db_session:
            db_session.commit()

        try:
            # Activate string in model
            self.builder.activate_string(self._model, string, prev_temps)

            # Update study time range for this string
            start_time = global_time
            end_time = global_time + string.simulation_duration
            self.builder.update_study_time(self._model, start_time, end_time)

            # Run COMSOL study
            self.client.run_study(self._model, 'std1')

            # Extract results
            results = self.extractor.extract_string_results(
                self._model, string, self.results_folder / f"project_{string.project_id}"
            )

            # Mark string complete
            string.status = STRING_COMPLETED
            string.completed_at = datetime.utcnow()
            if db_session:
                db_session.commit()

            logger.info(f"String {string.string_number} completed with {len(results)} results")
            return results

        except Exception as e:
            string.status = STRING_FAILED
            string.error_message = str(e)
            string.completed_at = datetime.utcnow()
            if db_session:
                db_session.commit()
            raise

    def _generate_project_results(self, project: 'WeldProject', db_session=None) -> None:
        """Generate project-level combined results.

        Creates:
        - Combined thermal cycle plots
        - Temperature field animation
        - Summary statistics

        Parameters
        ----------
        project : WeldProject
            Completed project
        db_session : Session, optional
            Database session
        """
        from app.models.weld_project import WeldResult, RESULT_THERMAL_CYCLE

        logger.info("Generating project-level results")

        project_folder = self.results_folder / f"project_{project.id}"
        project_folder.mkdir(parents=True, exist_ok=True)

        # Generate animation from VTK files
        vtk_files = list(project_folder.glob("*.vtk"))
        if vtk_files:
            try:
                from .visualization import WeldVisualization
                viz = WeldVisualization()
                animation_path = project_folder / "animation.mp4"

                # Sort VTK files by timestamp
                vtk_files_sorted = sorted(vtk_files, key=lambda p: p.stem)
                animation_bytes = viz.create_timelapse_animation(
                    [f.read_bytes() for f in vtk_files_sorted],
                    list(range(len(vtk_files_sorted)))
                )

                if animation_bytes:
                    animation_path.write_bytes(animation_bytes)

                    # Create animation result record
                    anim_result = WeldResult(
                        project_id=project.id,
                        result_type='animation',
                        location='full_model',
                        animation_filename=str(animation_path)
                    )
                    if db_session:
                        db_session.add(anim_result)

                logger.info(f"Generated animation at {animation_path}")

            except Exception as e:
                logger.warning(f"Could not generate animation: {e}")

        # Save final model state
        if self._model:
            final_model_path = project_folder / "model_final.mph"
            self.client.save_model(self._model, str(final_model_path))

    def cancel(self) -> None:
        """Cancel the current simulation."""
        self._cancelled = True
        logger.info("Simulation cancellation requested")

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancelled


class MockSequentialSolver(SequentialSolver):
    """Mock solver for testing without COMSOL.

    Generates synthetic results for development and testing.
    """

    def _simulate_string(self, string: 'WeldString',
                         prev_temps: Dict[str, float],
                         global_time: float,
                         db_session=None) -> List['WeldResult']:
        """Generate Rosenthal-based results for a string.

        Uses the analytical Rosenthal solution for physically correct
        thermal cycles instead of simple exponential decay.
        """
        from app.models.weld_project import (
            WeldResult, STRING_RUNNING, STRING_COMPLETED,
            RESULT_THERMAL_CYCLE, RESULT_COOLING_RATE
        )
        import numpy as np
        import time

        logger.info(f"Mock simulating string {string.string_number} (Rosenthal)")

        string.status = STRING_RUNNING
        string.started_at = datetime.utcnow()
        string.simulation_start_time = global_time
        if db_session:
            db_session.commit()

        # Brief processing delay
        time.sleep(0.3)

        results = []

        # Build Rosenthal solver from project/string parameters
        try:
            from app.services.rosenthal_solver import RosenthalSolver
            solver = RosenthalSolver.from_weld_project(string.project, string)
        except Exception as e:
            logger.warning(f"Rosenthal solver init failed, using fallback: {e}")
            return self._simulate_string_fallback(string, db_session)

        # Generate thermal cycles at multiple positions
        positions = {
            'centerline': 0.001,  # 1mm from weld center
            'cghaz': 0.003,       # 3mm — typically CGHAZ
            'fghaz': 0.006,       # 6mm — FGHAZ region
            'ichaz': 0.010,       # 10mm — ICHAZ region
        }

        duration = string.simulation_duration

        for loc_name, y_m in positions.items():
            times, temps = solver.thermal_cycle_at_point(
                y=y_m, z=0.0, duration=duration, n_points=200
            )

            peak_temp = float(np.max(temps))
            t_800_500 = solver.t8_5_at_point(y_m, z=0.0)

            # Cooling rate
            dt = np.diff(times)
            dt[dt == 0] = 1e-6
            cooling_rates = -np.diff(temps) / dt
            max_cooling_rate = float(np.max(cooling_rates)) if len(cooling_rates) > 0 else 0.0

            # Cooling rate in 800-500 range
            temp_mid = 0.5 * (temps[:-1] + temps[1:])
            mask_800_500 = (temp_mid > 500) & (temp_mid < 800)
            cr_800_500 = float(np.mean(cooling_rates[mask_800_500])) if np.any(mask_800_500) else None

            # Phase prediction
            phases = self._estimate_phases_from_rosenthal(t_800_500, string.project)

            # Hardness prediction
            hardness = self._predict_hardness(t_800_500, phases, string.project)

            # Create thermal cycle result
            cycle_result = WeldResult(
                project_id=string.project_id,
                string_id=string.id,
                result_type=RESULT_THERMAL_CYCLE,
                location=f'string_{string.string_number}_{loc_name}',
                peak_temperature=peak_temp,
                t_800_500=float(t_800_500) if t_800_500 else None,
                cooling_rate_max=max_cooling_rate,
                cooling_rate_800_500=cr_800_500,
                hardness_hv=hardness,
            )
            cycle_result.set_time_data(times.tolist())
            cycle_result.set_temperature_data(temps.tolist())
            cycle_result.set_phase_fractions(phases)

            results.append(cycle_result)

        # Create a single cooling rate result (from centerline)
        times_cl, temps_cl = solver.thermal_cycle_at_point(
            y=0.001, z=0.0, duration=duration, n_points=200
        )
        dt_cl = np.diff(times_cl)
        dt_cl[dt_cl == 0] = 1e-6
        cr_cl = -np.diff(temps_cl) / dt_cl
        temp_mid_cl = 0.5 * (temps_cl[:-1] + temps_cl[1:])

        rate_result = WeldResult(
            project_id=string.project_id,
            string_id=string.id,
            result_type=RESULT_COOLING_RATE,
            location=f'string_{string.string_number}_center',
            cooling_rate_max=float(np.max(cr_cl)) if len(cr_cl) > 0 else 0.0,
        )
        rate_result.set_time_data(temp_mid_cl.tolist())
        rate_result.set_temperature_data(cr_cl.tolist())
        results.append(rate_result)

        # Mark string complete
        string.status = STRING_COMPLETED
        string.completed_at = datetime.utcnow()
        string.calculated_initial_temp = float(np.max(temps_cl))

        if db_session:
            for r in results:
                db_session.add(r)
            db_session.commit()

        return results

    def _simulate_string_fallback(self, string: 'WeldString', db_session=None) -> list:
        """Fallback exponential-decay simulation when Rosenthal fails."""
        from app.models.weld_project import (
            WeldResult, STRING_COMPLETED,
            RESULT_THERMAL_CYCLE
        )
        import numpy as np

        t_solid = string.effective_solidification_temp
        t_ambient = string.project.preheat_temperature if string.project else 20.0

        times = np.linspace(0, string.simulation_duration, 100)
        tau = 30.0
        temps = t_ambient + (t_solid - t_ambient) * np.exp(-times / tau)

        t_800_idx = np.argmax(temps < 800) if np.any(temps < 800) else -1
        t_500_idx = np.argmax(temps < 500) if np.any(temps < 500) else -1
        t_800_500 = times[t_500_idx] - times[t_800_idx] if t_800_idx >= 0 and t_500_idx >= 0 else None

        cycle_result = WeldResult(
            project_id=string.project_id,
            string_id=string.id,
            result_type=RESULT_THERMAL_CYCLE,
            location=f'string_{string.string_number}_center',
            peak_temperature=float(t_solid),
            t_800_500=float(t_800_500) if t_800_500 else None,
        )
        cycle_result.set_time_data(times.tolist())
        cycle_result.set_temperature_data(temps.tolist())
        phases = self._estimate_phases_from_rosenthal(t_800_500, string.project)
        cycle_result.set_phase_fractions(phases)

        string.status = STRING_COMPLETED
        string.completed_at = datetime.utcnow()

        if db_session:
            db_session.add(cycle_result)
            db_session.commit()

        return [cycle_result]

    def _estimate_phases_from_rosenthal(self, t_800_500: Optional[float], project) -> dict:
        """Estimate phase fractions using PhaseTracker if available."""
        try:
            from app.services.phase_tracker import PhaseTracker
            import numpy as np

            phase_diagram = None
            if project and project.steel_grade:
                phase_diagram = getattr(project.steel_grade, 'phase_diagram', None)

            tracker = PhaseTracker(phase_diagram)

            if t_800_500 and t_800_500 > 0:
                result = tracker.predict_phases(
                    np.array([0, t_800_500]),
                    np.array([800, 500]),
                    t8_5=t_800_500,
                )
                return result.to_dict()
        except Exception:
            pass

        # Fallback simple estimation
        return self._estimate_phases_simple(t_800_500)

    def _predict_hardness(self, t_800_500: Optional[float], phases: dict, project) -> Optional[float]:
        """Predict hardness using HardnessPredictor if composition available."""
        try:
            if project and project.steel_grade:
                composition = getattr(project.steel_grade, 'composition', None)
                if composition:
                    from app.services.hardness_predictor import HardnessPredictor
                    predictor = HardnessPredictor(composition)
                    t85 = t_800_500 if t_800_500 and t_800_500 > 0 else 5.0
                    return predictor.predict_hardness(phases, t85)
        except Exception:
            pass
        return None

    def _estimate_phases_simple(self, t_800_500: Optional[float]) -> dict:
        """Simple phase estimation fallback.

        Parameters
        ----------
        t_800_500 : float, optional
            Cooling time from 800 to 500 C in seconds

        Returns
        -------
        dict
            Phase fractions (martensite, bainite, ferrite, pearlite)
        """
        if t_800_500 is None:
            return {'martensite': 1.0, 'bainite': 0.0, 'ferrite': 0.0, 'pearlite': 0.0}

        if t_800_500 < 5:
            return {'martensite': 0.95, 'bainite': 0.05, 'ferrite': 0.0, 'pearlite': 0.0}
        elif t_800_500 < 20:
            m_frac = max(0, 0.95 - (t_800_500 - 5) * 0.05)
            return {'martensite': m_frac, 'bainite': 1 - m_frac, 'ferrite': 0.0, 'pearlite': 0.0}
        elif t_800_500 < 60:
            b_frac = max(0.3, 0.8 - (t_800_500 - 20) * 0.01)
            return {'martensite': 0.1, 'bainite': b_frac, 'ferrite': 0.9 - b_frac, 'pearlite': 0.0}
        else:
            return {'martensite': 0.0, 'bainite': 0.1, 'ferrite': 0.6, 'pearlite': 0.3}
