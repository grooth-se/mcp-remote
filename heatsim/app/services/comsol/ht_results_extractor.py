"""Results extractor for COMSOL heat treatment simulation.

Maps solver output (thermal cycles, VTK files) to SimulationResult records
stored in the database.
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.models.simulation import Simulation, SimulationResult
    from app.models.snapshot import SimulationSnapshot

logger = logging.getLogger(__name__)


class HeatTreatmentResultsExtractor:
    """Maps COMSOL/mock solver output to SimulationResult records.

    Parameters
    ----------
    simulation : Simulation
        Simulation ORM object
    snapshot : SimulationSnapshot
        Snapshot for this run
    """

    def __init__(self, simulation: 'Simulation', snapshot: 'SimulationSnapshot'):
        self.simulation = simulation
        self.snapshot = snapshot

    def extract_and_store(self, solver_results: dict, db_session=None) -> List['SimulationResult']:
        """Create SimulationResult records from solver output.

        Parameters
        ----------
        solver_results : dict
            Output from HeatTreatmentSolver.solve() or MockHeatTreatmentSolver.solve()
        db_session : Session, optional
            Database session for adding records

        Returns
        -------
        list of SimulationResult
            Created result records
        """
        from app.models.simulation import SimulationResult

        results = []

        # Process each phase
        for phase_name, phase_data in solver_results.get('phases', {}).items():
            # Cooling curves (time vs temperature at different locations)
            results.extend(self._create_cooling_curves(phase_name, phase_data))

            # Temperature distribution (radial profiles)
            results.extend(self._create_temperature_profiles(phase_name, phase_data))

        # Phase fraction results (from quenching summary)
        summary = solver_results.get('summary', {})
        if 'estimated_phases' in summary:
            results.append(self._create_phase_fraction_result(summary))

        # VTK snapshot results
        vtk_files = solver_results.get('vtk_files', [])
        results.extend(self._create_vtk_results(vtk_files))

        # VTK animation result
        animation_result = self._create_animation(solver_results)
        if animation_result:
            results.append(animation_result)

        # Link all results to simulation and snapshot
        for r in results:
            r.simulation_id = self.simulation.id
            r.snapshot_id = self.snapshot.id
            if db_session:
                db_session.add(r)

        if db_session:
            db_session.flush()

        logger.info(f"Created {len(results)} SimulationResult records for COMSOL run")
        return results

    def _create_cooling_curves(self, phase_name: str, phase_data: dict) -> List['SimulationResult']:
        """Create cooling curve results for center, surface, quarter points."""
        from app.models.simulation import SimulationResult

        results = []
        times = phase_data.get('times', [])
        if not times:
            return results

        locations = {
            'center': phase_data.get('center_temps', []),
            'surface': phase_data.get('surface_temps', []),
            'quarter': phase_data.get('quarter_temps', []),
        }

        for location, temps in locations.items():
            if not temps:
                continue

            result = SimulationResult(
                result_type='cooling_curve',
                phase=phase_name,
                location=location,
            )
            result.set_time_data(times)
            result.set_value_data(temps)

            # Calculate cooling rate and t8/5 for quenching phase
            if phase_name == 'quenching' and len(temps) > 1:
                times_arr = np.array(times)
                temps_arr = np.array(temps)
                dt = np.diff(times_arr)
                dT = np.diff(temps_arr)
                cooling_rates = -dT / dt
                result.cooling_rate_max = float(np.max(cooling_rates))

                # t8/5
                t_800_idx = np.argmax(temps_arr < 800) if np.any(temps_arr < 800) else -1
                t_500_idx = np.argmax(temps_arr < 500) if np.any(temps_arr < 500) else -1
                if t_800_idx > 0 and t_500_idx > 0 and t_500_idx > t_800_idx:
                    result.t_800_500 = float(times_arr[t_500_idx] - times_arr[t_800_idx])

                    # Cooling rate in 800-500 range
                    mask = (temps_arr[:-1] > 500) & (temps_arr[:-1] < 800)
                    if np.any(mask):
                        result.cooling_rate_800_500 = float(np.mean(cooling_rates[mask]))

            results.append(result)

        return results

    def _create_temperature_profiles(self, phase_name: str, phase_data: dict) -> List['SimulationResult']:
        """Create temperature distribution results at key timesteps."""
        from app.models.simulation import SimulationResult

        results = []
        temperature_profiles = phase_data.get('temperature_profiles')
        radial_positions = phase_data.get('radial_positions')
        times = phase_data.get('times', [])

        if temperature_profiles is None or len(times) == 0:
            return results

        # Select a few key timesteps for profile data
        n_times = len(times)
        key_indices = [0, n_times // 4, n_times // 2, 3 * n_times // 4, n_times - 1]
        key_indices = sorted(set(min(i, n_times - 1) for i in key_indices))

        for idx in key_indices:
            t = times[idx]
            temps = temperature_profiles[idx]

            result = SimulationResult(
                result_type='temperature_distribution',
                phase=phase_name,
                location='radial',
            )

            if isinstance(radial_positions, np.ndarray):
                r_list = radial_positions.tolist()
            else:
                r_list = list(radial_positions) if radial_positions is not None else []

            if isinstance(temps, np.ndarray):
                t_list = temps.tolist()
            else:
                t_list = list(temps)

            result.set_time_data(r_list)  # Radial positions as "time" axis
            result.set_value_data(t_list)  # Temperature values
            result.set_data({
                'timestep': float(t),
                'phase': phase_name,
                'type': 'radial_profile',
            })

            results.append(result)

        return results

    def _create_phase_fraction_result(self, summary: dict) -> 'SimulationResult':
        """Create phase fraction result from estimated phases."""
        from app.models.simulation import SimulationResult

        phases = summary.get('estimated_phases', {})

        result = SimulationResult(
            result_type='phase_fraction',
            phase='quenching',
            location='center',
        )
        result.set_phase_fractions(phases)

        # Store t8/5 if available
        t85 = summary.get('t_800_500')
        if t85:
            result.t_800_500 = float(t85)

        return result

    def _create_vtk_results(self, vtk_files: List[str]) -> List['SimulationResult']:
        """Create vtk_snapshot results linking to VTK files on disk."""
        from app.models.simulation import SimulationResult

        results = []
        for i, vtk_path in enumerate(vtk_files):
            # Parse phase and timestep from filename
            filename = os.path.basename(vtk_path)
            # Expected: phase_<name>_t<NNN>.vtk
            parts = filename.replace('.vtk', '').split('_')
            phase_name = parts[1] if len(parts) > 1 else 'unknown'
            timestep_idx = int(parts[2].replace('t', '')) if len(parts) > 2 else i

            result = SimulationResult(
                result_type='vtk_snapshot',
                phase=phase_name,
                location='full_3d',
            )
            result.set_data({
                'vtk_path': vtk_path,
                'timestep_index': timestep_idx,
                'filename': filename,
            })

            results.append(result)

        return results

    def _create_animation(self, solver_results: dict) -> Optional['SimulationResult']:
        """Create animated GIF from VTK snapshots or temperature history.

        Tries PyVista 3D animation first, falls back to 2D animation.
        """
        from app.models.simulation import SimulationResult

        sim = self.simulation
        geo_type = sim.geometry_type
        geo_config = sim.geometry_dict

        if geo_type == 'cad':
            geo_type = sim.cad_equivalent_type or 'cylinder'
            geo_config = sim.cad_equivalent_geometry_dict or geo_config

        # Collect all temperature profiles across all phases
        all_times = []
        all_profiles = []
        radial_positions = None
        time_offset = 0.0

        for phase_name, phase_data in solver_results.get('phases', {}).items():
            profiles = phase_data.get('temperature_profiles')
            times = phase_data.get('times', [])
            rp = phase_data.get('radial_positions')

            if profiles is not None and len(times) > 0:
                if isinstance(profiles, np.ndarray):
                    all_profiles.append(profiles)
                else:
                    all_profiles.append(np.array(profiles))

                all_times.extend([t + time_offset for t in times])
                time_offset += times[-1]

                if radial_positions is None and rp is not None:
                    radial_positions = rp if isinstance(rp, np.ndarray) else np.array(rp)

        if not all_profiles or radial_positions is None:
            return None

        # Concatenate all profiles
        combined_profiles = np.vstack(all_profiles)
        combined_times = np.array(all_times)

        # Create animation using visualization_3d
        try:
            from ..visualization_3d import create_temperature_animation

            clim = (float(combined_profiles.min()), float(combined_profiles.max()))

            animation_data = create_temperature_animation(
                geometry_type=geo_type,
                geometry_params=geo_config,
                times=combined_times,
                temperature_history=combined_profiles,
                radial_positions=radial_positions,
                colormap='coolwarm',
                clim=clim,
                fps=8,
                max_frames=60,
                resolution=(600, 450),
            )

            if animation_data:
                # Save animation to disk
                vtk_folder = Path(solver_results.get('vtk_files', [''])[0]).parent \
                    if solver_results.get('vtk_files') else \
                    Path('instance') / 'vtk' / str(sim.id)
                vtk_folder.mkdir(parents=True, exist_ok=True)
                animation_path = vtk_folder / 'ht_animation.gif'
                animation_path.write_bytes(animation_data)

                result = SimulationResult(
                    result_type='vtk_animation',
                    phase='full',
                    location='full_3d',
                )
                result.set_data({
                    'animation_path': str(animation_path),
                    'filename': 'ht_animation.gif',
                    'n_frames': min(60, len(combined_times)),
                    'duration_seconds': float(combined_times[-1]),
                })

                logger.info(f"Created HT animation: {animation_path}")
                return result

        except Exception as e:
            logger.warning(f"Animation creation failed: {e}")

        return None
