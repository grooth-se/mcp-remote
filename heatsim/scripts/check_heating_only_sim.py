"""Simulation check: only the first heating step selected.

Builds a minimal HT config with `heating.enabled=True` and every other
phase disabled, runs `MultiPhaseHeatSolver` directly, and reports which
phases actually ran plus the center-temperature evolution.

Run from project root:
    MPLBACKEND=Agg PYVISTA_OFF_SCREEN=true python scripts/check_heating_only_sim.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import MultiPhaseHeatSolver, SolverConfig, create_geometry


def build_heating_only_config() -> dict:
    """HT config with ONLY the heating step enabled."""
    return {
        "heating": {
            "enabled": True,
            "initial_temperature": 25.0,
            "target_temperature": 850.0,
            "hold_time": 30.0,  # minutes at target
            "furnace_htc": 25.0,
            "furnace_emissivity": 0.85,
            "use_radiation": True,
            "end_condition": "equilibrium",
        },
        "transfer": {"enabled": False},
        "quenching": {"enabled": False, "media": "water", "media_temperature": 25.0},
        "tempering": {"enabled": False},
    }


def main() -> int:
    # 50 mm diameter, 100 mm long cylinder — modest size so the run is short.
    geometry = create_geometry("cylinder", {"radius": 0.025, "length": 0.1})
    solver_config = SolverConfig.from_dict({"n_nodes": 21, "dt": 1.0, "max_time": 7200})

    solver = MultiPhaseHeatSolver(geometry, config=solver_config)
    # k=None, cp=None → defaults (k=40 W/mK, cp=500 J/kgK); density=7850, ε=0.85
    solver.set_material(None, None, density=7850.0, emissivity=0.85)

    ht = build_heating_only_config()
    solver.configure_from_ht_config(ht)

    print("--- Configured phases ---")
    for i, phase in enumerate(solver.phases):
        print(
            f"  [{i}] name={phase.name:<10} enabled={phase.enabled}  "
            f"target={getattr(phase, 'target_temperature', '?')}  "
            f"end_condition={getattr(phase, 'end_condition', '?')}"
        )

    print("\n--- Running solve ---")
    result = solver.solve(initial_temperature=25.0)

    print(f"  total simulated time : {result.time[-1]:>10.1f} s ({result.time[-1] / 60:.1f} min)")
    print(f"  time samples         : {len(result.time)}")
    print(f"  positions            : {result.temperature.shape[1]}")
    print(f"  initial center T     : {result.center_temp[0]:>10.2f} °C")
    print(f"  final center T       : {result.center_temp[-1]:>10.2f} °C")
    print(f"  peak surface T       : {result.temperature[:, -1].max():>10.2f} °C")
    print(f"  t_8/5 (s)            : {result.t8_5!r}")

    print("\n--- Phase-by-phase summary ---")
    if not result.phase_results:
        print("  (no phase results recorded)")
    else:
        for pr in result.phase_results:
            t0 = pr.absolute_time[0] if pr.absolute_time.size else 0.0
            t1 = pr.absolute_time[-1] if pr.absolute_time.size else 0.0
            T0 = pr.center_temp[0] if pr.center_temp.size else float("nan")
            T1 = pr.center_temp[-1] if pr.center_temp.size else float("nan")
            print(
                f"  {pr.phase_name:<10}  "
                f"t = {t0:>8.1f} → {t1:>8.1f} s  "
                f"({(t1 - t0) / 60:>6.1f} min)  "
                f"T_center = {T0:>7.2f} → {T1:>7.2f} °C"
            )

    print("\n--- Verdict ---")
    phase_names = [pr.phase_name for pr in (result.phase_results or [])]
    if phase_names == ["heating"]:
        print("  OK: only the heating phase ran.")
        return 0
    if "quenching" in phase_names:
        print(
            "  NOTE: quenching ran despite quenching.enabled=False.\n"
            "        See app/services/heat_solver.py:973 — configure_from_ht_config\n"
            "        unconditionally appends from_quenching_config(), and the factory\n"
            "        ignores the 'enabled' flag. If you want a pure heating-only run,\n"
            "        either patch the solver or skip configure_from_ht_config and append\n"
            "        only PhaseConfig.from_heating_config(...) manually."
        )
    else:
        print(f"  UNEXPECTED: phases run = {phase_names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
