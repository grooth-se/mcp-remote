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
        """Generate mock results for a string."""
        from app.models.weld_project import (
            WeldResult, STRING_RUNNING, STRING_COMPLETED,
            RESULT_THERMAL_CYCLE, RESULT_COOLING_RATE
        )
        import numpy as np
        import json
        import time

        logger.info(f"Mock simulating string {string.string_number}")

        string.status = STRING_RUNNING
        string.started_at = datetime.utcnow()
        string.simulation_start_time = global_time
        if db_session:
            db_session.commit()

        # Simulate some processing time
        time.sleep(0.5)

        results = []

        # Generate thermal cycle result
        t_solid = string.effective_solidification_temp
        t_ambient = string.project.preheat_temperature if string.project else 20.0

        # Time array (0 to duration)
        times = np.linspace(0, string.simulation_duration, 100)

        # Temperature: exponential decay from solidification temp
        tau = 30.0  # Time constant
        temps = t_ambient + (t_solid - t_ambient) * np.exp(-times / tau)

        # Find t8/5 (time to cool from 800 to 500 C)
        t_800_idx = np.argmax(temps < 800) if np.any(temps < 800) else -1
        t_500_idx = np.argmax(temps < 500) if np.any(temps < 500) else -1
        t_800_500 = times[t_500_idx] - times[t_800_idx] if t_800_idx >= 0 and t_500_idx >= 0 else None

        # Cooling rate
        cooling_rates = -np.gradient(temps, times)
        max_cooling_rate = np.max(cooling_rates)

        # Create thermal cycle result
        cycle_result = WeldResult(
            project_id=string.project_id,
            string_id=string.id,
            result_type=RESULT_THERMAL_CYCLE,
            location=f'string_{string.string_number}_center',
            peak_temperature=float(t_solid),
            t_800_500=float(t_800_500) if t_800_500 else None,
            cooling_rate_max=float(max_cooling_rate),
        )
        cycle_result.set_time_data(times.tolist())
        cycle_result.set_temperature_data(temps.tolist())

        # Estimate phase fractions based on cooling rate
        phases = self._estimate_phases(t_800_500)
        cycle_result.set_phase_fractions(phases)

        results.append(cycle_result)

        # Create cooling rate result
        rate_result = WeldResult(
            project_id=string.project_id,
            string_id=string.id,
            result_type=RESULT_COOLING_RATE,
            location=f'string_{string.string_number}_center',
            cooling_rate_max=float(max_cooling_rate),
            cooling_rate_800_500=float(np.mean(cooling_rates[(temps > 500) & (temps < 800)]))
            if np.any((temps > 500) & (temps < 800)) else None,
        )
        rate_result.set_time_data(temps.tolist())  # Use temp as x-axis
        rate_result.set_temperature_data(cooling_rates.tolist())  # dT/dt as y

        results.append(rate_result)

        # Mark string complete
        string.status = STRING_COMPLETED
        string.completed_at = datetime.utcnow()
        string.calculated_initial_temp = float(t_solid)

        if db_session:
            for r in results:
                db_session.add(r)
            db_session.commit()

        return results

    def _estimate_phases(self, t_800_500: Optional[float]) -> dict:
        """Estimate phase fractions from t8/5 cooling time.

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

        # Simplified CCT-based estimation
        # Very fast cooling -> martensite
        # Medium cooling -> bainite
        # Slow cooling -> ferrite/pearlite

        if t_800_500 < 5:
            # Very fast - mostly martensite
            return {'martensite': 0.95, 'bainite': 0.05, 'ferrite': 0.0, 'pearlite': 0.0}
        elif t_800_500 < 20:
            # Fast - martensite + bainite
            m_frac = max(0, 0.95 - (t_800_500 - 5) * 0.05)
            return {'martensite': m_frac, 'bainite': 1 - m_frac, 'ferrite': 0.0, 'pearlite': 0.0}
        elif t_800_500 < 60:
            # Medium - bainite dominant
            b_frac = max(0.3, 0.8 - (t_800_500 - 20) * 0.01)
            return {'martensite': 0.1, 'bainite': b_frac, 'ferrite': 0.9 - b_frac, 'pearlite': 0.0}
        else:
            # Slow - ferrite/pearlite
            return {'martensite': 0.0, 'bainite': 0.1, 'ferrite': 0.6, 'pearlite': 0.3}
