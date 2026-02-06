"""Results extraction from COMSOL models.

Extracts thermal cycles, temperature fields, cooling rates, and other
data from completed COMSOL simulations.
"""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any, TYPE_CHECKING

import numpy as np

from .client import COMSOLError

if TYPE_CHECKING:
    from app.models.weld_project import WeldString, WeldResult

logger = logging.getLogger(__name__)


class ResultsExtractor:
    """Extracts and processes results from COMSOL models.

    Provides methods for extracting:
    - Point/probe data (temperature vs time)
    - Line data (temperature vs position)
    - Field data (3D temperature field as VTK)
    - Derived quantities (cooling rates, t8/5)

    Parameters
    ----------
    results_folder : str
        Base folder for storing extracted results
    """

    def __init__(self, results_folder: str = 'data/results'):
        """Initialize results extractor.

        Parameters
        ----------
        results_folder : str
            Base folder for storing extracted results
        """
        self.results_folder = Path(results_folder)
        self.results_folder.mkdir(parents=True, exist_ok=True)

    def extract_string_results(self, model: Any, string: 'WeldString',
                               output_folder: Path) -> List['WeldResult']:
        """Extract all results for a completed weld string simulation.

        Parameters
        ----------
        model : Model
            COMSOL model with completed study
        string : WeldString
            Weld string that was simulated
        output_folder : Path
            Folder to store result files

        Returns
        -------
        list of WeldResult
            Extracted result records
        """
        from app.models.weld_project import (
            WeldResult, RESULT_THERMAL_CYCLE, RESULT_TEMPERATURE_FIELD, RESULT_COOLING_RATE
        )

        output_folder.mkdir(parents=True, exist_ok=True)
        results = []

        # Extract probe/center point thermal cycle
        try:
            thermal_result = self._extract_thermal_cycle(model, string, output_folder)
            if thermal_result:
                results.append(thermal_result)
        except Exception as e:
            logger.warning(f"Could not extract thermal cycle: {e}")

        # Extract temperature field snapshot
        try:
            field_result = self._extract_temperature_field(model, string, output_folder)
            if field_result:
                results.append(field_result)
        except Exception as e:
            logger.warning(f"Could not extract temperature field: {e}")

        # Extract cooling rate data
        try:
            cooling_result = self._extract_cooling_rate(model, string, output_folder)
            if cooling_result:
                results.append(cooling_result)
        except Exception as e:
            logger.warning(f"Could not extract cooling rate: {e}")

        logger.info(f"Extracted {len(results)} results for string {string.string_number}")
        return results

    def _extract_thermal_cycle(self, model: Any, string: 'WeldString',
                               output_folder: Path) -> Optional['WeldResult']:
        """Extract temperature vs time at string center point.

        Parameters
        ----------
        model : Model
            COMSOL model
        string : WeldString
            Weld string
        output_folder : Path
            Output folder

        Returns
        -------
        WeldResult or None
            Thermal cycle result
        """
        from app.models.weld_project import WeldResult, RESULT_THERMAL_CYCLE

        try:
            # Get time steps from model
            # Note: This is simplified - actual implementation would query the solver
            times = self._get_time_steps(model)
            if times is None or len(times) == 0:
                return None

            # Get temperature at center point
            # In real implementation, would evaluate 'T' at a specific coordinate
            temps = self._evaluate_at_point(model, (0, 0, 0), times)
            if temps is None:
                return None

            # Calculate statistics
            peak_temp = float(np.max(temps))
            t_800_500 = self._calculate_t8_5(times, temps)
            cooling_rate = self._calculate_max_cooling_rate(times, temps)

            result = WeldResult(
                project_id=string.project_id,
                string_id=string.id,
                result_type=RESULT_THERMAL_CYCLE,
                location=f'string_{string.string_number}_center',
                peak_temperature=peak_temp,
                t_800_500=t_800_500,
                cooling_rate_max=cooling_rate,
            )
            result.set_time_data(times.tolist())
            result.set_temperature_data(temps.tolist())

            # Estimate phases from cooling rate
            phases = self._estimate_phases(t_800_500)
            result.set_phase_fractions(phases)

            return result

        except Exception as e:
            logger.error(f"Failed to extract thermal cycle: {e}")
            return None

    def _extract_temperature_field(self, model: Any, string: 'WeldString',
                                   output_folder: Path) -> Optional['WeldResult']:
        """Extract 3D temperature field as VTK file.

        Parameters
        ----------
        model : Model
            COMSOL model
        string : WeldString
            Weld string
        output_folder : Path
            Output folder

        Returns
        -------
        WeldResult or None
            Temperature field result
        """
        from app.models.weld_project import WeldResult, RESULT_TEMPERATURE_FIELD

        try:
            # Export VTK at end of simulation
            vtk_filename = output_folder / f"string_{string.string_number}_field.vtk"

            # In real implementation, would call model.export() or similar
            # For now, create placeholder
            self._export_vtk(model, str(vtk_filename), string.simulation_start_time + string.simulation_duration)

            result = WeldResult(
                project_id=string.project_id,
                string_id=string.id,
                result_type=RESULT_TEMPERATURE_FIELD,
                location='full_field',
                vtk_filename=str(vtk_filename),
                timestamp=string.simulation_start_time + string.simulation_duration,
            )

            return result

        except Exception as e:
            logger.error(f"Failed to extract temperature field: {e}")
            return None

    def _extract_cooling_rate(self, model: Any, string: 'WeldString',
                             output_folder: Path) -> Optional['WeldResult']:
        """Extract cooling rate data (dT/dt vs T).

        Parameters
        ----------
        model : Model
            COMSOL model
        string : WeldString
            Weld string
        output_folder : Path
            Output folder

        Returns
        -------
        WeldResult or None
            Cooling rate result
        """
        from app.models.weld_project import WeldResult, RESULT_COOLING_RATE

        try:
            times = self._get_time_steps(model)
            temps = self._evaluate_at_point(model, (0, 0, 0), times)

            if times is None or temps is None:
                return None

            # Calculate cooling rates
            cooling_rates = -np.gradient(temps, times)

            # Filter to cooling portion only (where dT/dt < 0)
            cooling_mask = cooling_rates > 0
            temps_cooling = temps[cooling_mask]
            rates_cooling = cooling_rates[cooling_mask]

            # Calculate average rate in 800-500 range
            range_mask = (temps_cooling > 500) & (temps_cooling < 800)
            avg_rate_800_500 = float(np.mean(rates_cooling[range_mask])) if np.any(range_mask) else None

            result = WeldResult(
                project_id=string.project_id,
                string_id=string.id,
                result_type=RESULT_COOLING_RATE,
                location=f'string_{string.string_number}_center',
                cooling_rate_max=float(np.max(cooling_rates)),
                cooling_rate_800_500=avg_rate_800_500,
            )

            # Store dT/dt vs T (for CCT overlay plot)
            result.set_time_data(temps_cooling.tolist())  # T as x-axis
            result.set_temperature_data(rates_cooling.tolist())  # dT/dt as y-axis

            return result

        except Exception as e:
            logger.error(f"Failed to extract cooling rate: {e}")
            return None

    def _get_time_steps(self, model: Any) -> Optional[np.ndarray]:
        """Get time steps from COMSOL model solution.

        Parameters
        ----------
        model : Model
            COMSOL model

        Returns
        -------
        ndarray or None
            Array of time values
        """
        try:
            # In real implementation, would query model for solution times
            # For now, return default range
            return np.linspace(0, 120, 121)
        except Exception:
            return None

    def _evaluate_at_point(self, model: Any, point: Tuple[float, float, float],
                          times: np.ndarray) -> Optional[np.ndarray]:
        """Evaluate temperature at a point over time.

        Parameters
        ----------
        model : Model
            COMSOL model
        point : tuple
            (x, y, z) coordinates
        times : ndarray
            Time values

        Returns
        -------
        ndarray or None
            Temperature values at each time
        """
        try:
            # In real implementation, would use model.evaluate()
            # For now, generate synthetic data
            t_initial = 1500  # Solidification temperature
            t_ambient = 25
            tau = 30  # Time constant

            temps = t_ambient + (t_initial - t_ambient) * np.exp(-times / tau)
            return temps
        except Exception:
            return None

    def _export_vtk(self, model: Any, filename: str, time: float) -> None:
        """Export temperature field to VTK file.

        Parameters
        ----------
        model : Model
            COMSOL model
        filename : str
            Output filename
        time : float
            Time at which to export
        """
        try:
            # In real implementation, would use COMSOL export
            # For now, create placeholder file
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            logger.debug(f"Exported VTK to {filename}")
        except Exception as e:
            logger.warning(f"VTK export failed: {e}")

    def _calculate_t8_5(self, times: np.ndarray, temps: np.ndarray) -> Optional[float]:
        """Calculate cooling time from 800 to 500 C.

        Parameters
        ----------
        times : ndarray
            Time values
        temps : ndarray
            Temperature values

        Returns
        -------
        float or None
            t8/5 cooling time in seconds
        """
        try:
            # Find time when temperature crosses 800 and 500 C
            t_800_idx = np.argmax(temps < 800)
            t_500_idx = np.argmax(temps < 500)

            if t_800_idx > 0 and t_500_idx > t_800_idx:
                return float(times[t_500_idx] - times[t_800_idx])
            return None
        except Exception:
            return None

    def _calculate_max_cooling_rate(self, times: np.ndarray, temps: np.ndarray) -> Optional[float]:
        """Calculate maximum cooling rate.

        Parameters
        ----------
        times : ndarray
            Time values
        temps : ndarray
            Temperature values

        Returns
        -------
        float or None
            Maximum cooling rate in C/s
        """
        try:
            cooling_rates = -np.gradient(temps, times)
            return float(np.max(cooling_rates))
        except Exception:
            return None

    def _estimate_phases(self, t_800_500: Optional[float]) -> dict:
        """Estimate phase fractions from t8/5 cooling time.

        Uses simplified CCT-based estimation.

        Parameters
        ----------
        t_800_500 : float, optional
            Cooling time from 800 to 500 C

        Returns
        -------
        dict
            Phase fractions
        """
        if t_800_500 is None:
            return {'martensite': 1.0, 'bainite': 0.0, 'ferrite': 0.0, 'pearlite': 0.0}

        # Simplified estimation based on typical low-alloy steel behavior
        if t_800_500 < 5:
            return {'martensite': 0.95, 'bainite': 0.05, 'ferrite': 0.0, 'pearlite': 0.0}
        elif t_800_500 < 20:
            m = max(0, 0.95 - (t_800_500 - 5) * 0.05)
            return {'martensite': m, 'bainite': 1 - m, 'ferrite': 0.0, 'pearlite': 0.0}
        elif t_800_500 < 60:
            b = max(0.3, 0.8 - (t_800_500 - 20) * 0.01)
            return {'martensite': 0.1, 'bainite': b, 'ferrite': 0.9 - b, 'pearlite': 0.0}
        else:
            return {'martensite': 0.0, 'bainite': 0.1, 'ferrite': 0.6, 'pearlite': 0.3}

    def extract_probe_data(self, model: Any, probe_points: List[Tuple[float, float, float]],
                          names: List[str] = None) -> Dict[str, Dict[str, np.ndarray]]:
        """Extract T vs t at multiple specified points.

        Parameters
        ----------
        model : Model
            COMSOL model with completed solution
        probe_points : list of tuple
            List of (x, y, z) coordinates
        names : list of str, optional
            Names for each probe point

        Returns
        -------
        dict
            Dictionary mapping probe names to {'time': array, 'temperature': array}
        """
        times = self._get_time_steps(model)
        if times is None:
            return {}

        if names is None:
            names = [f'probe_{i}' for i in range(len(probe_points))]

        results = {}
        for name, point in zip(names, probe_points):
            temps = self._evaluate_at_point(model, point, times)
            if temps is not None:
                results[name] = {
                    'time': times,
                    'temperature': temps,
                }

        return results

    def extract_line_data(self, model: Any, start: Tuple[float, float, float],
                         end: Tuple[float, float, float], n_points: int = 50,
                         times: List[float] = None) -> Dict[float, Dict[str, np.ndarray]]:
        """Extract T vs position along a line at multiple times.

        Parameters
        ----------
        model : Model
            COMSOL model
        start : tuple
            (x, y, z) start of line
        end : tuple
            (x, y, z) end of line
        n_points : int
            Number of points along line
        times : list of float, optional
            Times at which to extract (defaults to model solution times)

        Returns
        -------
        dict
            Dictionary mapping time to {'position': array, 'temperature': array}
        """
        if times is None:
            all_times = self._get_time_steps(model)
            if all_times is None:
                return {}
            # Select a few representative times
            indices = np.linspace(0, len(all_times) - 1, 5, dtype=int)
            times = all_times[indices]

        # Calculate positions along line
        start = np.array(start)
        end = np.array(end)
        positions = np.linspace(0, 1, n_points)
        arc_length = np.linalg.norm(end - start)

        results = {}
        for t in times:
            # In real implementation, would evaluate at each point
            # For now, generate synthetic gradient
            temps = np.linspace(500, 100, n_points)  # Mock gradient
            results[float(t)] = {
                'position': positions * arc_length,
                'temperature': temps,
            }

        return results

    def extract_field_sequence(self, model: Any, times: List[float],
                              output_folder: Path) -> List[Path]:
        """Extract VTK files at multiple time points for animation.

        Parameters
        ----------
        model : Model
            COMSOL model
        times : list of float
            Times at which to export
        output_folder : Path
            Output folder for VTK files

        Returns
        -------
        list of Path
            Paths to generated VTK files
        """
        output_folder.mkdir(parents=True, exist_ok=True)
        vtk_files = []

        for i, t in enumerate(times):
            filename = output_folder / f"field_{i:04d}.vtk"
            self._export_vtk(model, str(filename), t)
            vtk_files.append(filename)

        return vtk_files
