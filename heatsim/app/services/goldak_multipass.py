"""Multi-pass welding chain simulation using Goldak solver.

Chains sequential weld passes:
1. Run Goldak solver for pass N with initial temperature field
2. Apply interpass cooling until interpass temperature reached
3. Run Goldak solver for pass N+1 using cooled field as initial condition
4. Track cumulative thermal cycles at probe points
5. Optionally compare with Rosenthal analytical solution

This is the numerical equivalent of the COMSOL SequentialSolver
but uses the 2D Goldak cross-section solver.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List

import numpy as np

from .goldak_solver import (
    GoldakSolver, GoldakParams, GoldakSolverConfig, GoldakResult,
    estimate_pool_params, STEFAN_BOLTZMANN, DEFAULT_EMISSIVITY,
    DEFAULT_CONVECTION_HTC, ARC_EFFICIENCIES,
    DEFAULT_CONDUCTIVITY, DEFAULT_DENSITY, DEFAULT_SPECIFIC_HEAT,
)
from .rosenthal_solver import RosenthalSolver

logger = logging.getLogger(__name__)

# Grid resolution presets
GRID_PRESETS = {
    'coarse': GoldakSolverConfig(ny=21, nz=11, dt=0.1, output_interval=20),
    'medium': GoldakSolverConfig(ny=41, nz=31, dt=0.05, output_interval=20),
    'fine': GoldakSolverConfig(ny=61, nz=41, dt=0.02, output_interval=50),
}


@dataclass
class MultiPassResult:
    """Combined results from multi-pass Goldak simulation.

    Attributes
    ----------
    pass_results : list of GoldakResult
        Individual per-pass results
    cumulative_peak_temp_map : np.ndarray
        Max temperature reached across all passes (nz, ny)
    cumulative_thermal_cycles : dict
        {probe_name: {'times': [...], 'temps': [...]}} across all passes
    final_temperature_field : np.ndarray
        Temperature field after all passes and final cooling (nz, ny)
    pass_summary : list of dict
        Per-pass summary: {pass_number, peak_temp, t8_5, interpass_temp_before,
                           interpass_cooling_time, ...}
    comparison_with_rosenthal : dict or None
        Per-pass comparison data
    y_coords_mm : list
        y coordinates in mm
    z_coords_mm : list
        z coordinates in mm
    """
    pass_results: list
    cumulative_peak_temp_map: np.ndarray
    cumulative_thermal_cycles: dict
    final_temperature_field: np.ndarray
    pass_summary: list
    comparison_with_rosenthal: Optional[dict]
    y_coords_mm: list
    z_coords_mm: list

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            'pass_results': [r.to_dict() for r in self.pass_results],
            'cumulative_peak_temp_map': self.cumulative_peak_temp_map.tolist(),
            'cumulative_thermal_cycles': self.cumulative_thermal_cycles,
            'final_temperature_field': self.final_temperature_field.tolist(),
            'pass_summary': self.pass_summary,
            'comparison_with_rosenthal': self.comparison_with_rosenthal,
            'y_coords_mm': self.y_coords_mm,
            'z_coords_mm': self.z_coords_mm,
            'n_passes': len(self.pass_results),
        }


class GoldakMultiPassSolver:
    """Orchestrates multi-pass welding using Goldak 2D solver."""

    def __init__(self, project, config: Optional[GoldakSolverConfig] = None,
                 compare_with_rosenthal: bool = True):
        """
        Parameters
        ----------
        project : WeldProject
            Weld project with strings configured
        config : GoldakSolverConfig, optional
            Solver config (applied to all passes)
        compare_with_rosenthal : bool
            Generate Rosenthal comparison for each pass
        """
        self.project = project
        self.config = config or GoldakSolverConfig()
        self.compare = compare_with_rosenthal

    @classmethod
    def with_preset(cls, project, preset: str = 'medium',
                    compare: bool = True) -> 'GoldakMultiPassSolver':
        """Create solver with a named resolution preset."""
        config = GRID_PRESETS.get(preset, GRID_PRESETS['medium'])
        return cls(project, config=config, compare_with_rosenthal=compare)

    def run(self, progress_callback=None) -> MultiPassResult:
        """Run complete multi-pass simulation.

        For each string in execution order:
        1. Create GoldakSolver from string parameters
        2. Set initial field (previous cooled field or preheat)
        3. Solve single pass
        4. Apply interpass cooling
        5. Store results
        """
        project = self.project
        strings = project.strings.order_by('string_number').all()

        if not strings:
            raise ValueError("No weld strings configured for project")

        n_passes = len(strings)
        pass_results = []
        pass_summaries = []
        comparison_data = {'passes': []} if self.compare else None

        # Initial temperature field (uniform preheat)
        current_field = None  # Will be created by first solver
        cumulative_peak = None
        cumulative_cycles = {}

        # Track cumulative time across all passes
        cumulative_time = 0.0

        for idx, string in enumerate(strings):
            pass_num = idx + 1
            logger.info(f"Multi-pass: starting pass {pass_num}/{n_passes} "
                        f"(string #{string.string_number})")

            if progress_callback:
                progress_callback(idx / n_passes)

            # Create solver for this pass
            solver = GoldakSolver.from_weld_project(
                project, string=string, config=self._pass_config(string)
            )

            # Get interpass temperature before this pass
            if current_field is not None:
                interpass_temp_before = float(np.max(current_field))
            else:
                interpass_temp_before = project.preheat_temperature or 20.0

            # Run single-pass Goldak
            result = solver.solve(initial_field=current_field)
            pass_results.append(result)

            # Update cumulative peak temperature
            if cumulative_peak is None:
                cumulative_peak = result.peak_temperature_map.copy()
            else:
                cumulative_peak = np.maximum(cumulative_peak, result.peak_temperature_map)

            # Accumulate probe thermal cycles
            for probe_name, cycle in result.probe_thermal_cycles.items():
                if probe_name not in cumulative_cycles:
                    cumulative_cycles[probe_name] = {'times': [], 'temps': []}
                # Offset times by cumulative time
                offset_times = [t + cumulative_time for t in cycle['times']]
                cumulative_cycles[probe_name]['times'].extend(offset_times)
                cumulative_cycles[probe_name]['temps'].extend(cycle['temps'])

            cumulative_time += self.config.total_time

            # Get the final temperature field from this pass
            current_field = result.temperature_field[-1].copy()

            # Apply interpass cooling (except after last pass)
            interpass_cooling_time = 0.0
            if idx < n_passes - 1:
                target_temp = project.interpass_temperature or 250.0
                interpass_time_limit = string.effective_interpass_time or 600.0

                current_field, cooling_time = self._apply_interpass_cooling(
                    current_field, solver.y, solver.z,
                    target_temp=target_temp,
                    max_time=interpass_time_limit,
                )
                interpass_cooling_time = cooling_time
                cumulative_time += cooling_time

                # Record cooling in probe cycles
                for probe_name, (iz, iy) in _get_probe_indices(solver).items():
                    if probe_name in cumulative_cycles:
                        cumulative_cycles[probe_name]['times'].append(cumulative_time)
                        cumulative_cycles[probe_name]['temps'].append(
                            float(current_field[iz, iy]))

            # Pass summary
            ny_mid = len(solver.y) // 2
            center_peak = float(result.peak_temperature_map[0, ny_mid])
            summary = {
                'pass_number': pass_num,
                'string_number': string.string_number,
                'string_name': string.display_name,
                'heat_input_kj_mm': string.effective_heat_input,
                'travel_speed_mm_s': string.effective_travel_speed,
                'peak_temperature': center_peak,
                't8_5': result.center_t8_5,
                'interpass_temp_before': round(interpass_temp_before, 1),
                'interpass_cooling_time': round(interpass_cooling_time, 1),
                'fusion_area_mm2': result.fusion_zone_area_mm2,
                'solver_wall_time': result.solver_info.get('wall_time_s', 0),
            }
            pass_summaries.append(summary)

            # Rosenthal comparison for this pass
            if self.compare:
                comp = self._compare_with_rosenthal(project, string, result, solver)
                comparison_data['passes'].append(comp)

        # Final temperature field
        final_field = current_field if current_field is not None else np.array([])

        y_mm = (solver.y * 1000).tolist()
        z_mm = (solver.z * 1000).tolist()

        if progress_callback:
            progress_callback(1.0)

        return MultiPassResult(
            pass_results=pass_results,
            cumulative_peak_temp_map=cumulative_peak,
            cumulative_thermal_cycles=cumulative_cycles,
            final_temperature_field=final_field,
            pass_summary=pass_summaries,
            comparison_with_rosenthal=comparison_data,
            y_coords_mm=y_mm,
            z_coords_mm=z_mm,
        )

    def _pass_config(self, string) -> GoldakSolverConfig:
        """Create solver config for a specific pass."""
        cfg = GoldakSolverConfig(
            ny=self.config.ny,
            nz=self.config.nz,
            dt=self.config.dt,
            total_time=string.simulation_duration or self.config.total_time,
            theta=self.config.theta,
            convergence_tol=self.config.convergence_tol,
            max_iterations=self.config.max_iterations,
            output_interval=self.config.output_interval,
        )
        return cfg

    def _apply_interpass_cooling(self, field: np.ndarray,
                                  y: np.ndarray, z: np.ndarray,
                                  target_temp: float,
                                  max_time: float = 600.0) -> tuple:
        """Cool field via natural convection + radiation until max temp <= target.

        Uses simple explicit time-stepping with no heat source.

        Parameters
        ----------
        field : np.ndarray (nz, ny)
        y, z : coordinate arrays
        target_temp : float (°C)
        max_time : float (s)

        Returns
        -------
        (cooled_field, cooling_time)
        """
        nz, ny = field.shape
        dy = y[1] - y[0]
        dz = z[1] - z[0]
        T = field.copy()

        # Use larger time step for cooling (no source term, smoother)
        dt_cool = 0.5
        k = DEFAULT_CONDUCTIVITY
        rho = DEFAULT_DENSITY
        Cp = DEFAULT_SPECIFIC_HEAT
        alpha = k / (rho * Cp)

        # Stability limit for explicit scheme
        max_dt = 0.25 / (alpha * (1/dy**2 + 1/dz**2))
        dt_cool = min(dt_cool, max_dt * 0.9)

        t = 0.0
        while t < max_time:
            if np.max(T) <= target_temp:
                break

            # Explicit diffusion step
            T_new = T.copy()

            # Interior points
            for j in range(1, nz - 1):
                for i in range(1, ny - 1):
                    laplacian = (alpha * dt_cool *
                                 ((T[j, i-1] - 2*T[j, i] + T[j, i+1]) / dy**2 +
                                  (T[j-1, i] - 2*T[j, i] + T[j+1, i]) / dz**2))
                    T_new[j, i] = T[j, i] + laplacian

            # BCs: convection + radiation on surfaces
            T_amb = 20.0
            for i in range(ny):
                # Top surface (z=0)
                h = DEFAULT_CONVECTION_HTC + DEFAULT_EMISSIVITY * STEFAN_BOLTZMANN * (
                    (T[0, i] + 273.15)**2 + (T_amb + 273.15)**2) * (
                    (T[0, i] + 273.15) + (T_amb + 273.15))
                q_loss = h * (T[0, i] - T_amb)
                T_new[0, i] = T[0, i] - dt_cool * 2 * q_loss / (rho * Cp * dz)
                # Diffusion from interior
                if nz > 1:
                    T_new[0, i] += alpha * dt_cool * 2 * (T[1, i] - T[0, i]) / dz**2

            # Bottom: adiabatic (already handled by no flux)
            if nz > 1:
                T_new[-1, :] = T[-1, :] + alpha * dt_cool * 2 * (T[-2, :] - T[-1, :]) / dz**2

            # Left/right edges: convection
            for j in range(nz):
                for side_idx in [0, ny - 1]:
                    h = DEFAULT_CONVECTION_HTC
                    q_loss = h * (T[j, side_idx] - T_amb)
                    T_new[j, side_idx] -= dt_cool * 2 * q_loss / (rho * Cp * dy)
                    neighbor = 1 if side_idx == 0 else ny - 2
                    T_new[j, side_idx] += alpha * dt_cool * 2 * (T[j, neighbor] - T[j, side_idx]) / dy**2

            T = np.maximum(T_new, T_amb)  # Don't go below ambient
            t += dt_cool

        return T, t

    def _compare_with_rosenthal(self, project, string, goldak_result, solver) -> dict:
        """Run Rosenthal for same string and compare with Goldak result."""
        try:
            ros = RosenthalSolver.from_weld_project(project, string=string)

            # Get surface distances (positive half only)
            y_coords = solver.y
            ny_mid = len(y_coords) // 2
            distances_m = y_coords[ny_mid:]
            distances_mm = distances_m * 1000

            # Rosenthal peak temperatures
            ros_peak = ros.peak_temperature_at_distance(distances_m, z=0.0)

            # Goldak peak temperatures (surface, positive y)
            goldak_peak = goldak_result.peak_temperature_map[0, ny_mid:]

            # t8/5 comparison at a few key distances
            compare_distances = [0.002, 0.005, 0.010]  # 2, 5, 10 mm
            ros_t85 = []
            goldak_t85 = []
            for d in compare_distances:
                ros_val = ros.t8_5_at_point(d, z=0.0)
                ros_t85.append(ros_val)

                iy = np.argmin(np.abs(y_coords - d))
                gval = goldak_result.t8_5_map[0, iy]
                goldak_t85.append(float(gval) if gval > 0 else None)

            # HAZ width comparison
            ros_haz_widths = {}
            for zone, temp in [('fusion', 1500), ('cghaz', 1100), ('fghaz', 900), ('ichaz', 727)]:
                ros_haz_widths[zone] = ros.haz_boundary_distance(temp, z=0.0) * 1000  # mm

            goldak_haz = {}
            for zone, temp in [('fusion', 1500), ('cghaz', 1100), ('fghaz', 900), ('ichaz', 727)]:
                idx = np.where(goldak_peak < temp)[0]
                if len(idx) > 0 and idx[0] > 0:
                    goldak_haz[zone] = float(distances_mm[idx[0]])
                else:
                    goldak_haz[zone] = 0.0

            return {
                'string_number': string.string_number,
                'distances_mm': distances_mm.tolist(),
                'rosenthal_peak_temps': ros_peak.tolist(),
                'goldak_peak_temps': goldak_peak.tolist(),
                'compare_distances_mm': [d * 1000 for d in compare_distances],
                'rosenthal_t8_5': ros_t85,
                'goldak_t8_5': goldak_t85,
                'rosenthal_haz_widths': ros_haz_widths,
                'goldak_haz_widths': goldak_haz,
            }
        except Exception as e:
            logger.warning(f"Rosenthal comparison failed: {e}")
            return {'error': str(e)}


def _get_probe_indices(solver: GoldakSolver) -> dict:
    """Get probe point grid indices for a solver."""
    from .goldak_solver import PROBE_POINTS
    indices = {}
    ny = len(solver.y)
    nz = len(solver.z)
    for name, (y_abs, z_frac) in PROBE_POINTS.items():
        iy = np.argmin(np.abs(solver.y - y_abs))
        iz = int(z_frac * (nz - 1)) if z_frac < 1.0 else nz - 1
        indices[name] = (iz, iy)
    return indices
