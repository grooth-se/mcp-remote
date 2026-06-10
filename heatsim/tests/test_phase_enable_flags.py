"""Regression tests for MultiPhaseHeatSolver phase-enable handling.

Pins the contract that every phase honors its `enabled` flag, including
quenching. Historically quenching was unconditionally appended (see the
fix that introduced this test); these tests prevent that regression.
"""

from __future__ import annotations

from app.services import MultiPhaseHeatSolver, SolverConfig, create_geometry


def _solver():
    geometry = create_geometry("cylinder", {"radius": 0.025, "length": 0.1})
    config = SolverConfig.from_dict({"n_nodes": 21, "dt": 1.0, "max_time": 7200})
    s = MultiPhaseHeatSolver(geometry, config=config)
    s.set_material(None, None, density=7850.0, emissivity=0.85)
    return s


def _phase_names(solver) -> list[str]:
    return [p.name for p in solver.phases]


def test_heating_only_config_produces_single_phase():
    """heating.enabled=True and everything else disabled → only heating runs."""
    solver = _solver()
    solver.configure_from_ht_config(
        {
            "heating": {"enabled": True, "target_temperature": 850.0, "hold_time": 30.0},
            "transfer": {"enabled": False},
            "quenching": {"enabled": False},
            "tempering": {"enabled": False},
        }
    )
    assert _phase_names(solver) == ["heating"]


def test_disabled_quench_is_skipped():
    """quenching.enabled=False removes the quench phase."""
    solver = _solver()
    solver.configure_from_ht_config(
        {
            "heating": {"enabled": True, "target_temperature": 850.0, "hold_time": 30.0},
            "transfer": {"enabled": True, "duration": 10.0},
            "quenching": {"enabled": False},
            "tempering": {"enabled": False},
        }
    )
    assert "quenching" not in _phase_names(solver)
    assert _phase_names(solver) == ["heating", "transfer"]


def test_missing_quench_enabled_key_defaults_to_on():
    """Backward compat: legacy configs without the `enabled` key still quench."""
    solver = _solver()
    solver.configure_from_ht_config(
        {
            "heating": {"enabled": True, "target_temperature": 850.0, "hold_time": 30.0},
            # No `enabled` key in quenching — should default to True.
            "quenching": {"media": "water", "media_temperature": 25.0, "duration": 300.0},
        }
    )
    assert "quenching" in _phase_names(solver)


def test_full_default_cycle_has_all_phases():
    """Default config (heating+transfer+quenching enabled, tempering off) → 3 phases."""
    solver = _solver()
    solver.configure_from_ht_config(
        {
            "heating": {"enabled": True, "target_temperature": 850.0, "hold_time": 30.0},
            "transfer": {"enabled": True, "duration": 10.0},
            "quenching": {"enabled": True, "media": "water", "duration": 300.0},
            "tempering": {"enabled": False},
        }
    )
    assert _phase_names(solver) == ["heating", "transfer", "quenching"]


def test_tempering_adds_cooling_after():
    """Enabling tempering appends a cooling tail."""
    solver = _solver()
    solver.configure_from_ht_config(
        {
            "heating": {"enabled": True, "target_temperature": 850.0, "hold_time": 30.0},
            "quenching": {"enabled": True, "media": "water", "duration": 300.0},
            "tempering": {"enabled": True, "temperature": 550.0, "hold_time": 60.0},
        }
    )
    names = _phase_names(solver)
    assert names[-1] == "cooling"
    assert "tempering" in names
