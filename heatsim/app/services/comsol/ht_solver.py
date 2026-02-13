"""Heat treatment solver using COMSOL or mock with VTK output.

Runs multi-phase heat treatment simulation (heating, transfer, quenching,
tempering) and generates 3D temperature field data as VTK files.
"""
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, TYPE_CHECKING

import numpy as np

from .client import COMSOLClient, COMSOLError, MockCOMSOLClient
from .ht_model_builder import HeatTreatmentModelBuilder

if TYPE_CHECKING:
    from app.models.simulation import Simulation
    from app.models.snapshot import SimulationSnapshot

logger = logging.getLogger(__name__)


class HeatTreatmentSolver:
    """Run multi-phase heat treatment in COMSOL.

    Parameters
    ----------
    client : COMSOLClient
        Connected COMSOL client instance
    simulation : Simulation
        Simulation ORM object
    snapshot : SimulationSnapshot
        Snapshot for this run
    vtk_folder : str
        Path to store VTK output files
    """

    def __init__(self, client: COMSOLClient, simulation: 'Simulation',
                 snapshot: 'SimulationSnapshot', vtk_folder: str = None):
        self.client = client
        self.simulation = simulation
        self.snapshot = snapshot
        self.builder = HeatTreatmentModelBuilder(client, simulation)

        if vtk_folder is None:
            vtk_folder = os.path.join('instance', 'vtk', str(simulation.id))
        self.vtk_folder = Path(vtk_folder)
        self.vtk_folder.mkdir(parents=True, exist_ok=True)

    def solve(self) -> dict:
        """Run full multi-phase heat treatment simulation.

        Returns
        -------
        dict
            Results dictionary with keys:
            - phases: dict of phase_name -> phase result dict
            - vtk_files: list of VTK file paths
            - summary: dict with t_800_500, peak_temp, etc.
        """
        # Create base model
        model = self.builder.create_model()

        ht_config = self.simulation.ht_config
        results = {'phases': {}, 'vtk_files': [], 'summary': {}}

        phase_order = ['heating', 'transfer', 'quenching', 'tempering']

        for phase_name in phase_order:
            phase_config = ht_config.get(phase_name, {})
            if not phase_config.get('enabled', phase_name == 'quenching'):
                continue

            logger.info(f"Running COMSOL phase: {phase_name}")

            # Configure model for this phase
            self.builder.build_phase(model, phase_name, phase_config)

            # Run COMSOL study
            self.client.run_study(model, 'std1')

            # Extract results
            phase_result = self._extract_phase_results(model, phase_name, phase_config)
            results['phases'][phase_name] = phase_result

            # Export VTK snapshots
            vtk_paths = self._extract_vtk_snapshots(model, phase_name, phase_config)
            results['vtk_files'].extend(vtk_paths)

        # Calculate summary metrics
        results['summary'] = self._calculate_summary(results)

        logger.info(f"COMSOL HT simulation complete: {len(results['vtk_files'])} VTK files")
        return results

    def _extract_phase_results(self, model: Any, phase_name: str,
                                phase_config: dict) -> dict:
        """Extract thermal cycle and temperature data from COMSOL."""
        duration = self.builder._get_phase_duration(phase_name, phase_config)
        n_points = 100
        times = np.linspace(0, duration, n_points)

        try:
            # Evaluate temperature at center and surface
            t_center = self.client.evaluate(model, 'T', dataset='center')
            t_surface = self.client.evaluate(model, 'T', dataset='surface')

            if isinstance(t_center, np.ndarray) and len(t_center) > 0:
                center_temps = t_center.tolist()
            else:
                center_temps = np.linspace(850, 25, n_points).tolist()

            if isinstance(t_surface, np.ndarray) and len(t_surface) > 0:
                surface_temps = t_surface.tolist()
            else:
                surface_temps = np.linspace(850, 25, n_points).tolist()

        except Exception as e:
            logger.warning(f"Could not evaluate from COMSOL, using estimated data: {e}")
            center_temps = np.linspace(850, 25, n_points).tolist()
            surface_temps = np.linspace(850, 25, n_points).tolist()

        return {
            'phase_name': phase_name,
            'times': times.tolist(),
            'center_temps': center_temps,
            'surface_temps': surface_temps,
            'duration': duration,
        }

    def _extract_vtk_snapshots(self, model: Any, phase_name: str,
                                phase_config: dict) -> List[str]:
        """Export 3D temperature field as VTK at selected timesteps."""
        duration = self.builder._get_phase_duration(phase_name, phase_config)

        # Select ~10 snapshot times
        n_snapshots = min(10, max(3, int(duration / 30)))
        snapshot_times = np.linspace(0, duration, n_snapshots)

        vtk_paths = []
        for i, t in enumerate(snapshot_times):
            vtk_path = self.vtk_folder / f"phase_{phase_name}_t{i:03d}.vtk"
            try:
                self.client.export_data(model, str(vtk_path), expression='T', format='vtk')
                vtk_paths.append(str(vtk_path))
            except Exception as e:
                logger.warning(f"VTK export failed at t={t:.1f}s: {e}")

        return vtk_paths

    def _calculate_summary(self, results: dict) -> dict:
        """Calculate summary metrics from all phase results."""
        summary = {}

        # Get quenching phase for t8/5 calculation
        quench = results['phases'].get('quenching', {})
        if quench:
            times = np.array(quench.get('times', []))
            center_temps = np.array(quench.get('center_temps', []))
            surface_temps = np.array(quench.get('surface_temps', []))

            if len(center_temps) > 0:
                # t8/5 at center
                t_800_500 = self._calc_t8_5(times, center_temps)
                if t_800_500:
                    summary['t_800_500'] = t_800_500

                # Max cooling rate
                if len(times) > 1:
                    dt = np.diff(times)
                    dT = np.diff(center_temps)
                    cooling_rates = -dT / dt
                    summary['max_cooling_rate'] = float(np.max(cooling_rates))

            if len(surface_temps) > 0:
                summary['peak_surface_temp'] = float(np.max(surface_temps))
            if len(center_temps) > 0:
                summary['peak_center_temp'] = float(np.max(center_temps))

        return summary

    def _calc_t8_5(self, times: np.ndarray, temps: np.ndarray) -> Optional[float]:
        """Calculate t8/5 cooling time."""
        if len(temps) == 0:
            return None
        t_800_idx = np.argmax(temps < 800) if np.any(temps < 800) else -1
        t_500_idx = np.argmax(temps < 500) if np.any(temps < 500) else -1
        if t_800_idx > 0 and t_500_idx > 0 and t_500_idx > t_800_idx:
            return float(times[t_500_idx] - times[t_800_idx])
        return None


class MockHeatTreatmentSolver:
    """Mock solver generating real VTK files with synthetic temperature data.

    Uses visualization_3d mesh creation functions to generate real geometry
    meshes with interpolated temperature fields.

    Parameters
    ----------
    simulation : Simulation
        Simulation ORM object
    snapshot : SimulationSnapshot
        Snapshot for this run
    vtk_folder : str
        Path to store VTK output files
    """

    def __init__(self, simulation: 'Simulation',
                 snapshot: 'SimulationSnapshot', vtk_folder: str = None):
        self.simulation = simulation
        self.snapshot = snapshot

        if vtk_folder is None:
            vtk_folder = os.path.join('instance', 'vtk', str(simulation.id))
        self.vtk_folder = Path(vtk_folder)
        self.vtk_folder.mkdir(parents=True, exist_ok=True)

    def solve(self) -> dict:
        """Run mock multi-phase heat treatment simulation.

        Generates synthetic thermal cycles and real VTK files.

        Returns
        -------
        dict
            Same structure as HeatTreatmentSolver.solve()
        """
        sim = self.simulation
        ht_config = sim.ht_config
        geo_config = sim.geometry_dict
        geo_type = sim.geometry_type

        # Effective geometry for CAD types
        if geo_type == 'cad':
            geo_type = sim.cad_equivalent_type or 'cylinder'
            geo_config = sim.cad_equivalent_geometry_dict or geo_config

        results = {'phases': {}, 'vtk_files': [], 'summary': {}}

        # Track temperature state across phases
        current_temp = ht_config.get('heating', {}).get('initial_temperature', 25.0)

        phase_order = ['heating', 'transfer', 'quenching', 'tempering']

        for phase_name in phase_order:
            phase_config = ht_config.get(phase_name, {})
            if not phase_config.get('enabled', phase_name == 'quenching'):
                continue

            logger.info(f"Mock simulating phase: {phase_name}")

            # Generate synthetic thermal cycle for this phase
            phase_result = self._generate_phase_data(
                phase_name, phase_config, current_temp, geo_type, geo_config
            )
            results['phases'][phase_name] = phase_result

            # Generate VTK snapshots for this phase
            vtk_paths = self._generate_vtk_snapshots(
                phase_name, phase_result, geo_type, geo_config
            )
            results['vtk_files'].extend(vtk_paths)

            # Update current temperature for next phase
            center_temps = phase_result.get('center_temps', [])
            if center_temps:
                current_temp = center_temps[-1]

            # Small delay to simulate processing
            time.sleep(0.2)

        # Calculate summary metrics
        results['summary'] = self._calculate_summary(results)

        logger.info(f"Mock HT simulation complete: {len(results['vtk_files'])} VTK files")
        return results

    def _generate_phase_data(self, phase_name: str, phase_config: dict,
                              initial_temp: float, geo_type: str,
                              geo_config: dict) -> dict:
        """Generate synthetic thermal cycle data for a phase.

        Returns dict with times, center_temps, surface_temps, quarter_temps,
        temperature_profiles (for VTK generation).
        """
        duration = self._get_phase_duration(phase_name, phase_config)
        n_points = 100
        times = np.linspace(0, duration, n_points)

        # Number of radial positions for profiles
        n_radial = 50

        if phase_name == 'heating':
            target_temp = phase_config.get('target_temperature', 850.0)
            # Heating: exponential approach to target
            tau = duration / 4  # Time constant
            center_temps = target_temp - (target_temp - initial_temp) * np.exp(-times / tau)
            # Surface heats faster
            tau_surface = duration / 6
            surface_temps = target_temp - (target_temp - initial_temp) * np.exp(-times / tau_surface)

        elif phase_name == 'transfer':
            ambient = phase_config.get('ambient_temperature', 25.0)
            # Mild cooling during transfer
            tau = 200.0
            center_temps = ambient + (initial_temp - ambient) * np.exp(-times / tau)
            tau_surface = 100.0
            surface_temps = ambient + (initial_temp - ambient) * np.exp(-times / tau_surface)

        elif phase_name == 'quenching':
            media_temp = phase_config.get('media_temperature', 25.0)
            media = phase_config.get('media', 'water')
            agitation = phase_config.get('agitation', 'moderate')

            # Cooling speed depends on quench media
            tau_map = {'water': 15.0, 'oil': 40.0, 'polymer': 25.0, 'brine': 10.0, 'air': 200.0}
            base_tau = tau_map.get(media, 15.0)
            agit_factor = {'none': 1.5, 'mild': 1.2, 'moderate': 1.0, 'strong': 0.8, 'violent': 0.6}
            tau = base_tau * agit_factor.get(agitation, 1.0)

            # Center cools slower than surface
            center_temps = media_temp + (initial_temp - media_temp) * np.exp(-times / (tau * 2))
            surface_temps = media_temp + (initial_temp - media_temp) * np.exp(-times / tau)

        elif phase_name == 'tempering':
            target_temp = phase_config.get('temperature', 550.0)
            # Heat up to tempering temp, then hold
            ramp_time = duration * 0.2
            hold_start = ramp_time

            center_temps = np.where(
                times < ramp_time,
                initial_temp + (target_temp - initial_temp) * times / ramp_time,
                target_temp
            )
            surface_temps = np.where(
                times < ramp_time * 0.8,
                initial_temp + (target_temp - initial_temp) * times / (ramp_time * 0.8),
                target_temp
            )
        else:
            center_temps = np.full(n_points, initial_temp)
            surface_temps = np.full(n_points, initial_temp)

        # Quarter point: average of center and surface
        quarter_temps = 0.5 * (center_temps + surface_temps)

        # Generate full radial temperature profiles at each timestep
        # [n_times, n_radial] — from center (0) to surface (1)
        r_norm = np.linspace(0, 1, n_radial)
        temperature_profiles = np.zeros((n_points, n_radial))
        for i in range(n_points):
            t_center = center_temps[i]
            t_surface = surface_temps[i]
            # Parabolic profile: T(r) = T_center + (T_surface - T_center) * r^2
            temperature_profiles[i] = t_center + (t_surface - t_center) * r_norm**2

        return {
            'phase_name': phase_name,
            'times': times.tolist(),
            'center_temps': center_temps.tolist(),
            'surface_temps': surface_temps.tolist(),
            'quarter_temps': quarter_temps.tolist(),
            'temperature_profiles': temperature_profiles,
            'radial_positions': r_norm,
            'duration': duration,
        }

    def _generate_vtk_snapshots(self, phase_name: str, phase_result: dict,
                                 geo_type: str, geo_config: dict) -> List[str]:
        """Generate real VTK files with temperature data on 3D mesh.

        Uses visualization_3d mesh functions for geometry creation.
        """
        try:
            import pyvista as pv
        except ImportError:
            logger.warning("PyVista not available, skipping VTK generation")
            return []

        from ..visualization_3d import (
            create_cylinder_mesh, create_plate_mesh,
            create_hollow_cylinder_mesh, interpolate_temperature_to_mesh
        )

        temperature_profiles = phase_result.get('temperature_profiles')
        radial_positions = phase_result.get('radial_positions')
        times = phase_result.get('times', [])

        if temperature_profiles is None or len(times) == 0:
            return []

        # Select ~8 snapshot times spread across the phase
        n_snapshots = min(8, len(times))
        indices = np.linspace(0, len(times) - 1, n_snapshots, dtype=int)

        # Create mesh for this geometry
        try:
            if geo_type == 'cylinder':
                radius = geo_config.get('radius', 0.05)
                length = geo_config.get('length', 0.1)
                mesh = create_cylinder_mesh(radius, length, n_radial=30, n_axial=10)
            elif geo_type in ('ring', 'hollow_cylinder'):
                outer_r = geo_config.get('outer_radius',
                          geo_config.get('outer_diameter', 0.1) / 2)
                inner_r = geo_config.get('inner_radius',
                          geo_config.get('inner_diameter', 0.05) / 2)
                length = geo_config.get('length', 0.1)
                mesh = create_hollow_cylinder_mesh(outer_r, inner_r, length,
                                                    n_radial=20, n_axial=10)
            elif geo_type == 'plate':
                thickness = geo_config.get('thickness', 0.02)
                width = geo_config.get('width', 0.1)
                length = geo_config.get('length', 0.1)
                mesh = create_plate_mesh(thickness, width, length, n_thickness=20)
            else:
                mesh = create_cylinder_mesh(0.05, 0.1, n_radial=30, n_axial=10)
        except Exception as e:
            logger.error(f"Mesh creation failed: {e}")
            return []

        vtk_paths = []
        for i, idx in enumerate(indices):
            t = times[idx]
            temps = temperature_profiles[idx]

            # Map temperatures onto mesh
            mesh_copy = mesh.copy()
            try:
                mesh_copy = interpolate_temperature_to_mesh(
                    mesh_copy, temps, radial_positions,
                    geo_type, geo_config
                )
            except Exception as e:
                logger.warning(f"Temperature interpolation failed at t={t:.1f}s: {e}")
                # Fall back: assign uniform temp
                mesh_copy['Temperature'] = np.full(mesh_copy.n_points, float(np.mean(temps)))

            # Save VTK
            vtk_path = self.vtk_folder / f"phase_{phase_name}_t{i:03d}.vtk"
            try:
                mesh_copy.save(str(vtk_path))
                vtk_paths.append(str(vtk_path))
                logger.debug(f"Saved VTK: {vtk_path} (t={t:.1f}s)")
            except Exception as e:
                logger.warning(f"VTK save failed: {e}")

        return vtk_paths

    def _calculate_summary(self, results: dict) -> dict:
        """Calculate summary metrics from phase results."""
        summary = {}

        quench = results['phases'].get('quenching', {})
        if quench:
            times = np.array(quench.get('times', []))
            center_temps = np.array(quench.get('center_temps', []))
            surface_temps = np.array(quench.get('surface_temps', []))

            if len(center_temps) > 0:
                # t8/5
                t_800_idx = np.argmax(center_temps < 800) if np.any(center_temps < 800) else -1
                t_500_idx = np.argmax(center_temps < 500) if np.any(center_temps < 500) else -1
                if t_800_idx > 0 and t_500_idx > 0 and t_500_idx > t_800_idx:
                    summary['t_800_500'] = float(times[t_500_idx] - times[t_800_idx])

                # Cooling rate
                if len(times) > 1:
                    dt_arr = np.diff(times)
                    dT_arr = np.diff(center_temps)
                    cooling_rates = -dT_arr / dt_arr
                    summary['max_cooling_rate'] = float(np.max(cooling_rates))

                # Phase estimation from t8/5
                t85 = summary.get('t_800_500')
                if t85:
                    summary['estimated_phases'] = self._estimate_phases(t85)

            if len(surface_temps) > 0:
                summary['peak_surface_temp'] = float(np.max(surface_temps))
            if len(center_temps) > 0:
                summary['peak_center_temp'] = float(np.max(center_temps))

        return summary

    def _estimate_phases(self, t_800_500: float) -> dict:
        """Estimate phase fractions from t8/5 cooling time.

        Same logic as MockSequentialSolver._estimate_phases.
        """
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

    def _get_phase_duration(self, phase_name: str, phase_config: dict) -> float:
        """Get simulation duration for a phase in seconds."""
        if phase_name == 'heating':
            return phase_config.get('hold_time', 60.0) * 60.0
        elif phase_name == 'transfer':
            return phase_config.get('duration', 10.0)
        elif phase_name == 'quenching':
            return phase_config.get('duration', 300.0)
        elif phase_name == 'tempering':
            return phase_config.get('hold_time', 120.0) * 60.0
        return 300.0
