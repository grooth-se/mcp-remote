"""Results extractor for COMSOL heat treatment simulation.

Maps solver output (thermal cycles, VTK files) to SimulationResult records
stored in the database.  Generates the same rich plot set as the builtin
1-D FDM path so that COMSOL results appear identical in the web UI.
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

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

    def __init__(self, simulation: "Simulation", snapshot: "SimulationSnapshot"):
        self.simulation = simulation
        self.snapshot = snapshot

    def extract_and_store(self, solver_results: dict, db_session=None) -> list["SimulationResult"]:
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

        results = []

        # --- Build combined time/temperature arrays across all phases ---
        combined_times, combined_center, combined_surface = self._combine_phases(solver_results)

        # --- Full cycle result with multi-position data and plot ---
        full_cycle = self._create_full_cycle_result(
            solver_results, combined_times, combined_center, combined_surface
        )
        if full_cycle:
            results.append(full_cycle)

        # --- Per-phase cooling/heating curves ---
        for phase_name, phase_data in solver_results.get("phases", {}).items():
            results.extend(self._create_cooling_curves(phase_name, phase_data))
            results.extend(self._create_temperature_profiles(phase_name, phase_data))
            # dT/dt plots for heating, quenching, tempering phases
            if phase_name in ("heating", "quenching", "tempering"):
                results.extend(self._create_dTdt_results(phase_name, phase_data))

        # --- Phase fraction results ---
        summary = solver_results.get("summary", {})
        if "estimated_phases" in summary:
            results.append(self._create_phase_fraction_result(summary))

        # --- Cooling rate plot ---
        if combined_times is not None and combined_center is not None:
            cr = self._create_cooling_rate_result(combined_times, combined_center, combined_surface)
            if cr:
                results.append(cr)

        # --- VTK snapshots ---
        vtk_files = solver_results.get("vtk_files", [])
        results.extend(self._create_vtk_results(vtk_files))

        # --- VTK animation ---
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _combine_phases(self, solver_results: dict):
        """Combine per-phase time/temperature into continuous arrays."""
        all_times = []
        all_center = []
        all_surface = []
        time_offset = 0.0

        for phase_name, phase_data in solver_results.get("phases", {}).items():
            times = phase_data.get("times", [])
            center = phase_data.get("center_temps", [])
            surface = phase_data.get("surface_temps", [])

            if not times or not center:
                continue

            times_arr = np.array(times)
            # Offset so phases are continuous
            if all_times:
                time_offset = all_times[-1]
                # Skip first point if it overlaps
                if len(times_arr) > 1:
                    times_arr = times_arr[1:]
                    center = center[1:] if len(center) > 1 else center
                    surface = surface[1:] if len(surface) > 1 else surface

            all_times.extend(
                (times_arr + time_offset).tolist() if time_offset else times_arr.tolist()
            )
            all_center.extend(center)
            if surface:
                all_surface.extend(surface)

        if not all_times:
            return None, None, None

        t = np.array(all_times)
        c = np.array(all_center)
        s = np.array(all_surface) if all_surface else None
        return t, c, s

    def _build_furnace_temps(self, solver_results: dict) -> list:
        """Build furnace temperature list for the full_cycle plot overlay."""
        ht_config = self.simulation.ht_config or {}
        furnace_temps = []
        time_offset = 0.0

        for phase_name, phase_data in solver_results.get("phases", {}).items():
            times = phase_data.get("times", [])
            if not times:
                continue

            start_time = time_offset
            duration = times[-1]
            end_time = start_time + duration

            temp = None
            cold_furnace = False
            furnace_start_temp = None
            ramp_rate = 0

            if phase_name == "heating":
                cfg = ht_config.get("heating", {})
                temp = cfg.get("target_temperature")
                cold_furnace = cfg.get("cold_furnace", False)
                furnace_start_temp = cfg.get("furnace_start_temperature", 25.0)
                ramp_rate = cfg.get("furnace_ramp_rate", 0)
            elif phase_name == "transfer":
                temp = ht_config.get("transfer", {}).get("ambient_temperature")
            elif phase_name == "quenching":
                temp = ht_config.get("quenching", {}).get("media_temperature")
            elif phase_name == "tempering":
                cfg = ht_config.get("tempering", {})
                temp = cfg.get("temperature")
                cold_furnace = cfg.get("cold_furnace", False)
                furnace_start_temp = cfg.get("furnace_start_temperature", 25.0)
                ramp_rate = cfg.get("furnace_ramp_rate", 0)
            elif phase_name == "cooling":
                temp = ht_config.get("transfer", {}).get("ambient_temperature", 25.0)

            if temp is not None:
                furnace_temps.append(
                    {
                        "start_time": start_time,
                        "end_time": end_time,
                        "temperature": temp,
                        "phase_name": phase_name,
                        "cold_furnace": cold_furnace,
                        "furnace_start_temperature": furnace_start_temp
                        if furnace_start_temp
                        else temp,
                        "furnace_ramp_rate": ramp_rate,
                    }
                )

            time_offset = end_time

        return furnace_temps

    def _create_full_cycle_result(
        self, solver_results, combined_times, combined_center, combined_surface
    ):
        """Create full_cycle result with plot, matching builtin path output."""
        from app.models.simulation import SimulationResult

        if combined_times is None or combined_center is None:
            return None

        sim = self.simulation
        grade = sim.steel_grade
        diagram = grade.phase_diagrams.first() if grade else None
        trans_temps = diagram.temps_dict if diagram else {}

        result = SimulationResult(
            result_type="full_cycle",
            phase="full",
            location="center",
        )
        result.set_time_data(combined_times.tolist())
        result.set_value_data(combined_center.tolist())

        # Multi-position data
        multi_pos = {"positions": ["center"]}
        multi_pos["center"] = combined_center.tolist()
        if combined_surface is not None:
            multi_pos["positions"].append("surface")
            multi_pos["surface"] = combined_surface.tolist()

        # Add one_third / two_thirds from probe data if available
        for key in ("one_third", "two_thirds"):
            all_vals = []
            for phase_data in solver_results.get("phases", {}).values():
                vals = phase_data.get(f"{key}_temps", [])
                if vals:
                    all_vals.extend(vals)
            if all_vals and len(all_vals) >= len(combined_center):
                # Trim to match combined length
                all_vals = all_vals[: len(combined_center)]
                multi_pos["positions"].append(key)
                multi_pos[key] = all_vals

        result.set_data(multi_pos)

        # Calculate t8/5
        t85 = solver_results.get("summary", {}).get("t_800_500")
        if t85:
            result.t_800_500 = float(t85)
        else:
            # Calculate from combined data
            if np.any(combined_center < 800) and np.any(combined_center < 500):
                idx_800 = np.argmax(combined_center < 800)
                idx_500 = np.argmax(combined_center < 500)
                if idx_500 > idx_800 > 0:
                    result.t_800_500 = float(combined_times[idx_500] - combined_times[idx_800])

        # Generate plot with furnace temperature overlay
        try:
            from app.services import visualization

            # Build temperature array for plot (2D: center + surface if available)
            if combined_surface is not None:
                temp_2d = np.column_stack([combined_center, combined_surface])
            else:
                temp_2d = combined_center

            # Build furnace/ambient temperature list for overlay
            furnace_temps = self._build_furnace_temps(solver_results)

            result.plot_image = visualization.create_heat_treatment_cycle_plot(
                combined_times,
                temp_2d,
                phase_results=None,
                title=f"Heat Treatment Cycle - {sim.name}",
                transformation_temps=trans_temps,
                furnace_temps=furnace_temps,
            )
        except Exception as e:
            logger.warning("Failed to generate full cycle plot: %s", e)

        return result

    def _create_cooling_curves(self, phase_name: str, phase_data: dict) -> list["SimulationResult"]:
        """Create cooling curve results for center, surface, quarter points."""
        from app.models.simulation import SimulationResult

        results = []
        times = phase_data.get("times", [])
        if not times:
            return results

        locations = {
            "center": phase_data.get("center_temps", []),
            "surface": phase_data.get("surface_temps", []),
            "quarter": phase_data.get("quarter_temps", []),
        }

        for location, temps in locations.items():
            if not temps:
                continue

            result = SimulationResult(
                result_type="cooling_curve",
                phase=phase_name,
                location=location,
            )
            result.set_time_data(times)
            result.set_value_data(temps)

            # Calculate cooling rate and t8/5 for quenching phase
            if phase_name == "quenching" and len(temps) > 1:
                times_arr = np.array(times)
                temps_arr = np.array(temps)
                dt = np.diff(times_arr)
                dT = np.diff(temps_arr)
                valid = dt > 0
                cooling_rates = np.zeros_like(dt)
                cooling_rates[valid] = -dT[valid] / dt[valid]
                if np.any(valid):
                    result.cooling_rate_max = float(np.max(cooling_rates[valid]))

                # t8/5
                t_800_idx = np.argmax(temps_arr < 800) if np.any(temps_arr < 800) else -1
                t_500_idx = np.argmax(temps_arr < 500) if np.any(temps_arr < 500) else -1
                if t_800_idx > 0 and t_500_idx > 0 and t_500_idx > t_800_idx:
                    result.t_800_500 = float(times_arr[t_500_idx] - times_arr[t_800_idx])

                    mask = (temps_arr[:-1] > 500) & (temps_arr[:-1] < 800)
                    if np.any(mask):
                        result.cooling_rate_800_500 = float(np.mean(cooling_rates[mask]))

            results.append(result)

        return results

    def _create_temperature_profiles(
        self, phase_name: str, phase_data: dict
    ) -> list["SimulationResult"]:
        """Create temperature distribution results at key timesteps."""
        from app.models.simulation import SimulationResult

        results = []
        temperature_profiles = phase_data.get("temperature_profiles")
        radial_positions = phase_data.get("radial_positions")
        times = phase_data.get("times", [])

        if temperature_profiles is None or len(times) == 0:
            return results

        n_times = len(times)
        key_indices = [0, n_times // 4, n_times // 2, 3 * n_times // 4, n_times - 1]
        key_indices = sorted(set(min(i, n_times - 1) for i in key_indices))

        for idx in key_indices:
            t = times[idx]
            temps = temperature_profiles[idx]

            result = SimulationResult(
                result_type="temperature_distribution",
                phase=phase_name,
                location="radial",
            )

            if isinstance(radial_positions, np.ndarray):
                r_list = radial_positions.tolist()
            else:
                r_list = list(radial_positions) if radial_positions is not None else []

            if isinstance(temps, np.ndarray):
                t_list = temps.tolist()
            else:
                t_list = list(temps)

            result.set_time_data(r_list)
            result.set_value_data(t_list)
            result.set_data(
                {
                    "timestep": float(t),
                    "phase": phase_name,
                    "type": "radial_profile",
                }
            )

            results.append(result)

        return results

    def _create_phase_fraction_result(self, summary: dict) -> "SimulationResult":
        """Create phase fraction result from estimated phases."""
        from app.models.simulation import SimulationResult

        phases = summary.get("estimated_phases", {})

        result = SimulationResult(
            result_type="phase_fraction",
            phase="full",
            location="center",
        )
        result.set_phase_fractions(phases)

        t85 = summary.get("t_800_500")
        if t85:
            result.t_800_500 = float(t85)

        # Generate phase fraction plot
        try:
            from app.services import visualization

            result.plot_image = visualization.create_phase_fraction_plot(
                phases, title=f"Predicted Phase Fractions - {self.simulation.name}"
            )
        except Exception as e:
            logger.warning("Failed to generate phase fraction plot: %s", e)

        return result

    def _create_cooling_rate_result(self, times, center_temps, surface_temps):
        """Create cooling rate plot result."""
        from app.models.simulation import SimulationResult

        try:
            from app.services import visualization

            result = SimulationResult(
                result_type="cooling_rate",
                phase="full",
                location="all",
            )
            result.plot_image = visualization.create_cooling_rate_plot(
                times,
                center_temps,
                surface_temps if surface_temps is not None else center_temps,
                title=f"Cooling Rate - {self.simulation.name}",
            )
            return result
        except Exception as e:
            logger.warning("Failed to generate cooling rate plot: %s", e)
            return None

    def _build_phase_temp_2d(self, phase_data: dict) -> np.ndarray | None:
        """Build 2D temperature array [time, position] from phase probe data.

        Returns array with columns for center, one_third, two_thirds, surface
        (matching the format expected by visualization plot functions).
        """
        center = phase_data.get("center_temps", [])
        surface = phase_data.get("surface_temps", [])
        one_third = phase_data.get("one_third_temps", [])
        two_thirds = phase_data.get("two_thirds_temps", [])

        if not center:
            return None

        n = len(center)
        cols = [np.array(center)]

        if one_third and len(one_third) == n:
            cols.append(np.array(one_third))
        else:
            cols.append(np.array(center))

        if two_thirds and len(two_thirds) == n:
            cols.append(np.array(two_thirds))
        elif surface and len(surface) == n:
            # Interpolate between center and surface
            cols.append(0.5 * (np.array(center) + np.array(surface)))
        else:
            cols.append(np.array(center))

        if surface and len(surface) == n:
            cols.append(np.array(surface))
        else:
            cols.append(np.array(center))

        return np.column_stack(cols)

    def _create_dTdt_results(self, phase_name: str, phase_data: dict) -> list["SimulationResult"]:
        """Create dT/dt vs time and dT/dt vs temperature plots for a phase."""
        from app.models.simulation import SimulationResult

        results = []
        times = phase_data.get("times", [])
        if not times or len(times) < 3:
            return results

        temp_2d = self._build_phase_temp_2d(phase_data)
        if temp_2d is None:
            return results

        times_arr = np.array(times)
        sim = self.simulation
        phase_label = phase_name.title()

        try:
            from app.services import visualization

            # dT/dt vs Time
            dtdt_time = SimulationResult(
                result_type="dTdt_vs_time",
                phase=phase_name,
                location="all",
            )
            dtdt_time.plot_image = visualization.create_dTdt_vs_time_plot(
                times_arr,
                temp_2d,
                title=f"dT/dt vs Time ({phase_label}) - {sim.name}",
                phase_name=phase_name,
            )
            results.append(dtdt_time)

            # dT/dt vs Temperature
            dtdt_temp = SimulationResult(
                result_type="dTdt_vs_temp",
                phase=phase_name,
                location="all",
            )
            dtdt_temp.plot_image = visualization.create_dTdt_vs_temperature_plot(
                times_arr,
                temp_2d,
                title=f"dT/dt vs Temperature ({phase_label}) - {sim.name}",
                phase_name=phase_name,
            )
            results.append(dtdt_temp)

        except Exception as e:
            logger.warning("Failed to generate dT/dt plots for %s: %s", phase_name, e)

        return results

    def _create_vtk_results(self, vtk_files: list[str]) -> list["SimulationResult"]:
        """Create vtk_snapshot results linking to VTK files on disk."""
        from app.models.simulation import SimulationResult

        results = []
        for i, vtk_path in enumerate(vtk_files):
            filename = os.path.basename(vtk_path)
            parts = filename.replace(".vtk", "").split("_")
            phase_name = parts[1] if len(parts) > 1 else "unknown"
            timestep_idx = int(parts[2].replace("t", "")) if len(parts) > 2 else i

            result = SimulationResult(
                result_type="vtk_snapshot",
                phase=phase_name,
                location="full_3d",
            )
            result.set_data(
                {
                    "vtk_path": vtk_path,
                    "timestep_index": timestep_idx,
                    "filename": filename,
                }
            )

            results.append(result)

        return results

    def _create_animation(self, solver_results: dict) -> Optional["SimulationResult"]:
        """Create animated GIF from VTK snapshots or temperature history."""
        from app.models.simulation import SimulationResult

        sim = self.simulation
        geo_type = sim.geometry_type
        geo_config = sim.geometry_dict

        if geo_type == "cad":
            geo_type = sim.cad_equivalent_type or "cylinder"
            geo_config = sim.cad_equivalent_geometry_dict or geo_config

        all_times = []
        all_profiles = []
        radial_positions = None
        time_offset = 0.0

        for phase_name, phase_data in solver_results.get("phases", {}).items():
            profiles = phase_data.get("temperature_profiles")
            times = phase_data.get("times", [])
            rp = phase_data.get("radial_positions")

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

        combined_profiles = np.vstack(all_profiles)
        combined_times = np.array(all_times)

        try:
            import sys
            import threading

            # VTK Cocoa renderer crashes on macOS when called from non-main thread
            if (
                sys.platform == "darwin"
                and threading.current_thread() is not threading.main_thread()
            ):
                logger.info("Skipping animation on macOS worker thread (VTK Cocoa limitation)")
                return None

            from ..visualization_3d import create_temperature_animation

            clim = (float(combined_profiles.min()), float(combined_profiles.max()))

            animation_data = create_temperature_animation(
                geometry_type=geo_type,
                geometry_params=geo_config,
                times=combined_times,
                temperature_history=combined_profiles,
                radial_positions=radial_positions,
                colormap="coolwarm",
                clim=clim,
                fps=8,
                max_frames=60,
                resolution=(600, 450),
            )

            if animation_data:
                vtk_folder = (
                    Path(solver_results.get("vtk_files", [""])[0]).parent
                    if solver_results.get("vtk_files")
                    else Path("instance") / "vtk" / str(sim.id)
                )
                vtk_folder.mkdir(parents=True, exist_ok=True)
                animation_path = vtk_folder / "ht_animation.gif"
                animation_path.write_bytes(animation_data)

                result = SimulationResult(
                    result_type="vtk_animation",
                    phase="full",
                    location="full_3d",
                )
                result.set_data(
                    {
                        "animation_path": str(animation_path),
                        "filename": "ht_animation.gif",
                        "n_frames": min(60, len(combined_times)),
                        "duration_seconds": float(combined_times[-1]),
                    }
                )

                logger.info(f"Created HT animation: {animation_path}")
                return result

        except Exception as e:
            logger.warning(f"Animation creation failed: {e}")

        return None
