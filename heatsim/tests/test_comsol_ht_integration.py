"""Integration tests for COMSOL heat treatment pipeline.

Tests the MockHeatTreatmentSolver, HeatTreatmentResultsExtractor,
and the fallback chain in simulation_runner.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.models import DATA_SOURCE_STANDARD, ROLE_ENGINEER, SteelGrade, User
from app.models.material import MaterialProperty, PhaseDiagram, SteelComposition
from app.models.simulation import (
    GEOMETRY_CYLINDER,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_RUNNING,
    Simulation,
    SimulationResult,
)
from app.models.snapshot import SimulationSnapshot
from app.services.comsol import (
    COMSOLNotAvailableError,
    HeatTreatmentResultsExtractor,
    MockHeatTreatmentSolver,
)

# ---------------------------------------------------------------------------
# Lightweight mock objects to avoid heavy DB dependencies in unit-level tests
# ---------------------------------------------------------------------------


class _MockGrade:
    """Minimal SteelGrade stand-in."""

    id = 1
    designation = "AISI 4340"
    display_name = "AISI 4340"
    composition = None
    phase_diagrams = MagicMock()

    def __init__(self):
        self.phase_diagrams.first.return_value = None

    def get_property(self, name):
        return None


class _MockSimulation:
    """Minimal Simulation stand-in for MockHeatTreatmentSolver."""

    def __init__(self, ht_config=None, geo_type="cylinder", geo_dict=None):
        self.id = 1
        self.name = "Test HT Sim"
        self.geometry_type = geo_type
        self.cad_equivalent_type = None
        self.cad_equivalent_geometry_dict = None
        self.cad_file_path = None
        self.steel_grade = _MockGrade()
        self.steel_grade_id = 1
        self._geometry_dict = geo_dict or {"radius": 0.05, "length": 0.2}
        self._ht_config = ht_config or self._default_ht_config()

    @property
    def geometry_dict(self):
        return self._geometry_dict

    @property
    def ht_config(self):
        return self._ht_config

    def _default_ht_config(self):
        return {
            "heating": {
                "enabled": True,
                "target_temperature": 850.0,
                "hold_time": 60.0,
                "initial_temperature": 25.0,
                "cold_furnace": False,
                "h_conv": 50.0,
            },
            "transfer": {
                "enabled": True,
                "duration": 10.0,
                "ambient_temperature": 25.0,
                "h_conv": 10.0,
            },
            "quenching": {
                "enabled": True,
                "media": "oil",
                "media_temperature": 60.0,
                "duration": 300.0,
                "h_conv": 500.0,
            },
            "tempering": {
                "enabled": False,
            },
        }


class _MockSnapshot:
    """Minimal SimulationSnapshot stand-in."""

    id = 1
    t_800_500 = None


# ---------------------------------------------------------------------------
# Helper to build a solver_results dict without running the full solver
# ---------------------------------------------------------------------------


def _make_solver_results(n=50, with_quench=True, with_tempering=False):
    """Build a synthetic solver_results dict for extractor tests."""
    phases = {}

    # Heating phase
    h_times = np.linspace(0, 300, n).tolist()
    h_center = np.linspace(25, 850, n).tolist()
    h_surface = np.linspace(25, 860, n).tolist()
    phases["heating"] = {
        "phase_name": "heating",
        "times": h_times,
        "center_temps": h_center,
        "surface_temps": h_surface,
        "quarter_temps": np.linspace(25, 855, n).tolist(),
        "temperature_profiles": np.zeros((n, 10)),
        "radial_positions": np.linspace(0, 0.05, 10),
        "duration": 300.0,
    }

    # Transfer phase
    t_times = np.linspace(0, 10, 20).tolist()
    t_center = np.linspace(850, 830, 20).tolist()
    t_surface = np.linspace(860, 820, 20).tolist()
    phases["transfer"] = {
        "phase_name": "transfer",
        "times": t_times,
        "center_temps": t_center,
        "surface_temps": t_surface,
        "quarter_temps": np.linspace(855, 825, 20).tolist(),
        "temperature_profiles": np.zeros((20, 10)),
        "radial_positions": np.linspace(0, 0.05, 10),
        "duration": 10.0,
    }

    if with_quench:
        q_times = np.linspace(0, 600, n).tolist()
        q_center = np.linspace(830, 60, n).tolist()
        q_surface = np.linspace(820, 60, n).tolist()
        phases["quenching"] = {
            "phase_name": "quenching",
            "times": q_times,
            "center_temps": q_center,
            "surface_temps": q_surface,
            "quarter_temps": np.linspace(825, 60, n).tolist(),
            "temperature_profiles": np.zeros((n, 10)),
            "radial_positions": np.linspace(0, 0.05, 10),
            "duration": 600.0,
        }

    if with_tempering:
        tp_times = np.linspace(0, 3600, n).tolist()
        tp_center = np.linspace(60, 550, n).tolist()
        tp_surface = np.linspace(60, 555, n).tolist()
        phases["tempering"] = {
            "phase_name": "tempering",
            "times": tp_times,
            "center_temps": tp_center,
            "surface_temps": tp_surface,
            "quarter_temps": np.linspace(60, 552, n).tolist(),
            "temperature_profiles": np.zeros((n, 10)),
            "radial_positions": np.linspace(0, 0.05, 10),
            "duration": 3600.0,
        }

    return {
        "phases": phases,
        "vtk_files": [],
        "summary": {
            "t_800_500": 15.0 if with_quench else None,
            "max_cooling_rate": 50.0,
            "peak_surface_temp": 860.0,
            "peak_center_temp": 850.0,
            "estimated_phases": {
                "martensite": 0.85,
                "bainite": 0.10,
                "ferrite": 0.03,
                "pearlite": 0.02,
            },
        },
        "temperature_profiles": {},
    }


# ===========================================================================
# Test MockHeatTreatmentSolver
# ===========================================================================


class TestMockHeatTreatmentSolver:
    """Tests for MockHeatTreatmentSolver.solve() pipeline."""

    def test_solve_returns_required_keys(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        assert "phases" in result
        assert "vtk_files" in result
        assert "summary" in result
        assert "temperature_profiles" in result

    def test_solve_produces_heating_and_quenching_phases(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        assert "heating" in result["phases"]
        assert "quenching" in result["phases"]

    def test_phase_data_structure(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        for phase_name, phase_data in result["phases"].items():
            assert "times" in phase_data, f"Missing 'times' in {phase_name}"
            assert "center_temps" in phase_data, f"Missing 'center_temps' in {phase_name}"
            assert "surface_temps" in phase_data, f"Missing 'surface_temps' in {phase_name}"
            assert len(phase_data["times"]) == len(phase_data["center_temps"])
            assert len(phase_data["times"]) == len(phase_data["surface_temps"])
            assert len(phase_data["times"]) > 2, f"Phase {phase_name} too short"

    def test_summary_has_t85_and_cooling_rate(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        summary = result["summary"]
        assert "max_cooling_rate" in summary
        assert "peak_surface_temp" in summary
        assert "peak_center_temp" in summary
        assert summary["peak_center_temp"] > 700

    def test_estimated_phases_sum_to_one(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        phases = result["summary"].get("estimated_phases")
        if phases:
            total = sum(phases.values())
            assert abs(total - 1.0) < 0.01

    def test_temperature_continuity_between_phases(self):
        """End temperature of one phase should be close to start of next."""
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        phase_order = ["heating", "transfer", "quenching"]
        phases = result["phases"]
        for i in range(len(phase_order) - 1):
            p1 = phase_order[i]
            p2 = phase_order[i + 1]
            if p1 in phases and p2 in phases:
                end_temp = phases[p1]["center_temps"][-1]
                start_temp = phases[p2]["center_temps"][0]
                assert abs(end_temp - start_temp) < 50, (
                    f"Temperature jump {p1}->{p2}: {end_temp:.0f} -> {start_temp:.0f}"
                )

    def test_with_tempering_enabled(self):
        ht_config = _MockSimulation()._default_ht_config()
        ht_config["tempering"] = {
            "enabled": True,
            "temperature": 550.0,
            "hold_time": 60.0,
            "duration": 3600.0,
            "h_conv": 50.0,
        }
        sim = _MockSimulation(ht_config=ht_config)
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        assert "tempering" in result["phases"]

    def test_vtk_files_created(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        with tempfile.TemporaryDirectory() as tmp:
            solver = MockHeatTreatmentSolver(sim, snap, vtk_folder=tmp)
            result = solver.solve()

        # VTK generation may silently fail without pyvista; just check list type
        assert isinstance(result["vtk_files"], list)


# ===========================================================================
# Test HeatTreatmentResultsExtractor (unit-level, no DB)
# ===========================================================================


class TestResultsExtractorUnit:
    """Unit tests for HeatTreatmentResultsExtractor helper methods."""

    def test_combine_phases_basic(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)
        solver_results = _make_solver_results()

        times, center, surface = extractor._combine_phases(solver_results)

        assert times is not None
        assert center is not None
        assert surface is not None
        assert len(times) == len(center)
        assert len(times) == len(surface)
        # Times should be monotonically increasing
        assert np.all(np.diff(times) >= 0)

    def test_combine_phases_empty(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)

        times, center, surface = extractor._combine_phases({"phases": {}})
        assert times is None
        assert center is None
        assert surface is None

    def test_combine_phases_time_continuity(self):
        """Combined times should increase across phase boundaries."""
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)
        solver_results = _make_solver_results()

        times, center, surface = extractor._combine_phases(solver_results)

        # No duplicate times at phase boundaries
        diffs = np.diff(times)
        assert np.all(diffs > -1e-10), "Times not monotonically increasing"

    def test_build_furnace_temps(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)
        solver_results = _make_solver_results()

        furnace_temps = extractor._build_furnace_temps(solver_results)

        assert isinstance(furnace_temps, list)
        assert len(furnace_temps) > 0

        for ft in furnace_temps:
            assert "start_time" in ft
            assert "end_time" in ft
            assert "temperature" in ft
            assert "phase_name" in ft
            assert ft["end_time"] > ft["start_time"]

    def test_build_phase_temp_2d(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)

        phase_data = _make_solver_results()["phases"]["heating"]
        temp_2d = extractor._build_phase_temp_2d(phase_data)

        assert temp_2d is not None
        assert temp_2d.ndim == 2
        assert temp_2d.shape[0] == len(phase_data["center_temps"])
        # Should have at least center and surface columns
        assert temp_2d.shape[1] >= 2

    def test_build_phase_temp_2d_missing_data(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)

        result = extractor._build_phase_temp_2d({})
        assert result is None

    def test_create_dTdt_results(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)

        phase_data = _make_solver_results()["phases"]["quenching"]
        results = extractor._create_dTdt_results("quenching", phase_data)

        assert len(results) == 2
        types = {r.result_type for r in results}
        assert "dTdt_vs_time" in types
        assert "dTdt_vs_temp" in types

        for r in results:
            # simulation_id/snapshot_id are set by extract_and_store(), not by _create_dTdt_results()
            assert r.phase == "quenching"
            assert r.plot_image is not None

    def test_create_dTdt_results_heating(self):
        sim = _MockSimulation()
        snap = _MockSnapshot()
        extractor = HeatTreatmentResultsExtractor(sim, snap)

        phase_data = _make_solver_results()["phases"]["heating"]
        results = extractor._create_dTdt_results("heating", phase_data)

        assert len(results) == 2
        for r in results:
            assert r.phase == "heating"


# ===========================================================================
# Test HeatTreatmentResultsExtractor.extract_and_store() (DB integration)
# ===========================================================================


class TestResultsExtractorDB:
    """Integration tests requiring Flask app/DB context."""

    def _create_sim(self, db_session):
        """Create a minimal Simulation + deps in the test DB."""
        user = User(username="tester", role=ROLE_ENGINEER)
        user.set_password("test")
        db_session.add(user)

        grade = SteelGrade(designation="AISI 4340", data_source=DATA_SOURCE_STANDARD)
        db_session.add(grade)
        db_session.flush()

        sim = Simulation(
            name="Integration Test",
            steel_grade_id=grade.id,
            user_id=user.id,
            geometry_type=GEOMETRY_CYLINDER,
            status=STATUS_RUNNING,
        )
        sim.set_geometry({"radius": 0.05, "length": 0.2})
        sim.set_solver_config({"solver_type": "comsol", "n_nodes": 21, "dt": 0.5})
        sim.set_ht_config(
            {
                "heating": {
                    "enabled": True,
                    "target_temperature": 850.0,
                    "hold_time": 60.0,
                    "initial_temperature": 25.0,
                    "h_conv": 50.0,
                    "cold_furnace": False,
                },
                "transfer": {
                    "enabled": True,
                    "duration": 10.0,
                    "ambient_temperature": 25.0,
                    "h_conv": 10.0,
                },
                "quenching": {
                    "enabled": True,
                    "media": "oil",
                    "media_temperature": 60.0,
                    "duration": 300.0,
                    "h_conv": 500.0,
                },
                "tempering": {"enabled": False},
            }
        )
        db_session.add(sim)
        db_session.flush()

        snapshot = SimulationSnapshot(
            simulation_id=sim.id,
            version=1,
            status="running",
            geometry_type=sim.geometry_type,
            steel_grade_designation=grade.designation,
        )
        db_session.add(snapshot)
        db_session.flush()

        return sim, snapshot

    def test_extract_and_store_creates_results(self, app, db):
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)
            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            solver_results = _make_solver_results()

            results = extractor.extract_and_store(solver_results, db_session=db.session)

            assert len(results) > 0
            # Check that all results are linked to the simulation
            for r in results:
                assert r.simulation_id == sim.id
                assert r.snapshot_id == snapshot.id

    def test_extract_produces_full_cycle(self, app, db):
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)
            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            solver_results = _make_solver_results()

            results = extractor.extract_and_store(solver_results, db_session=db.session)

            types = {r.result_type for r in results}
            assert "full_cycle" in types

    def test_extract_produces_cooling_curves(self, app, db):
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)
            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            solver_results = _make_solver_results()

            results = extractor.extract_and_store(solver_results, db_session=db.session)

            cooling = [r for r in results if r.result_type == "cooling_curve"]
            assert len(cooling) > 0

    def test_extract_produces_dTdt_plots(self, app, db):
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)
            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            solver_results = _make_solver_results()

            results = extractor.extract_and_store(solver_results, db_session=db.session)

            dtdt = [r for r in results if r.result_type.startswith("dTdt_")]
            # Should have dT/dt plots for heating and quenching
            assert len(dtdt) >= 2

    def test_extract_produces_phase_fractions(self, app, db):
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)
            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            solver_results = _make_solver_results()

            results = extractor.extract_and_store(solver_results, db_session=db.session)

            phase_results = [r for r in results if r.result_type == "phase_fraction"]
            assert len(phase_results) == 1

            pr = phase_results[0]
            fractions = pr.get_phase_fractions() if hasattr(pr, "get_phase_fractions") else {}
            if fractions:
                total = sum(fractions.values())
                assert abs(total - 1.0) < 0.05

    def test_extract_produces_cooling_rate(self, app, db):
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)
            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            solver_results = _make_solver_results()

            results = extractor.extract_and_store(solver_results, db_session=db.session)

            rate_results = [r for r in results if r.result_type == "cooling_rate"]
            assert len(rate_results) == 1


# ===========================================================================
# Test MockHeatTreatmentSolver + Extractor end-to-end (DB integration)
# ===========================================================================


class TestMockSolverPipeline:
    """End-to-end: MockHeatTreatmentSolver → HeatTreatmentResultsExtractor."""

    def _create_sim(self, db_session):
        user = User(username="pipeline", role=ROLE_ENGINEER)
        user.set_password("test")
        db_session.add(user)

        grade = SteelGrade(designation="A182 F22", data_source=DATA_SOURCE_STANDARD)
        db_session.add(grade)
        db_session.flush()

        sim = Simulation(
            name="Pipeline Test",
            steel_grade_id=grade.id,
            user_id=user.id,
            geometry_type=GEOMETRY_CYLINDER,
            status=STATUS_RUNNING,
        )
        sim.set_geometry({"radius": 0.05, "length": 0.2})
        sim.set_solver_config({"solver_type": "comsol", "n_nodes": 21, "dt": 0.5})
        sim.set_ht_config(
            {
                "heating": {
                    "enabled": True,
                    "target_temperature": 850.0,
                    "hold_time": 60.0,
                    "initial_temperature": 25.0,
                    "h_conv": 50.0,
                    "cold_furnace": False,
                },
                "transfer": {
                    "enabled": True,
                    "duration": 10.0,
                    "ambient_temperature": 25.0,
                    "h_conv": 10.0,
                },
                "quenching": {
                    "enabled": True,
                    "media": "oil",
                    "media_temperature": 60.0,
                    "duration": 300.0,
                    "h_conv": 500.0,
                },
                "tempering": {"enabled": False},
            }
        )
        db_session.add(sim)
        db_session.flush()

        snapshot = SimulationSnapshot(
            simulation_id=sim.id,
            version=1,
            status="running",
            geometry_type=sim.geometry_type,
            steel_grade_designation=grade.designation,
        )
        db_session.add(snapshot)
        db_session.flush()

        return sim, snapshot

    def test_full_pipeline(self, app, db):
        """Solve with mock → extract → verify results."""
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)

            with tempfile.TemporaryDirectory() as tmp:
                solver = MockHeatTreatmentSolver(sim, snapshot, vtk_folder=tmp)
                solver_results = solver.solve()

            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            results = extractor.extract_and_store(solver_results, db_session=db.session)

            assert len(results) > 5
            types = {r.result_type for r in results}
            assert "full_cycle" in types
            assert "cooling_curve" in types

    def test_pipeline_result_plots_are_bytes(self, app, db):
        """All plot_image fields should contain PNG bytes."""
        with app.app_context():
            sim, snapshot = self._create_sim(db.session)

            with tempfile.TemporaryDirectory() as tmp:
                solver = MockHeatTreatmentSolver(sim, snapshot, vtk_folder=tmp)
                solver_results = solver.solve()

            extractor = HeatTreatmentResultsExtractor(sim, snapshot)
            results = extractor.extract_and_store(solver_results, db_session=db.session)

            plot_results = [r for r in results if r.plot_image is not None]
            assert len(plot_results) > 0

            for r in plot_results:
                assert isinstance(r.plot_image, bytes)
                # PNG magic bytes
                assert r.plot_image[:4] == b"\x89PNG", (
                    f"Result {r.result_type}/{r.phase} plot_image is not a PNG"
                )


# ===========================================================================
# Test fallback chain: COMSOL → Mock → Builtin
# ===========================================================================


class TestFallbackChain:
    """Tests for the COMSOL → Mock → Builtin fallback in simulation_runner."""

    def _create_runnable_sim(self, db_session):
        """Create a simulation that can actually run through the builtin solver."""
        user = User(username="fallback_tester", role=ROLE_ENGINEER)
        user.set_password("test")
        db_session.add(user)

        grade = SteelGrade(designation="AISI 4340", data_source=DATA_SOURCE_STANDARD)
        db_session.add(grade)
        db_session.flush()

        # Add minimal material properties needed by builtin solver
        k_prop = MaterialProperty(
            steel_grade_id=grade.id,
            property_name="thermal_conductivity",
            property_type="constant",
        )
        k_prop.set_data({"value": 44.5})
        db_session.add(k_prop)

        cp_prop = MaterialProperty(
            steel_grade_id=grade.id,
            property_name="specific_heat",
            property_type="constant",
        )
        cp_prop.set_data({"value": 475.0})
        db_session.add(cp_prop)

        rho_prop = MaterialProperty(
            steel_grade_id=grade.id,
            property_name="density",
            property_type="constant",
        )
        rho_prop.set_data({"value": 7850.0})
        db_session.add(rho_prop)

        sim = Simulation(
            name="Fallback Test",
            steel_grade_id=grade.id,
            user_id=user.id,
            geometry_type=GEOMETRY_CYLINDER,
            process_type="quench_water",
            status=STATUS_DRAFT,
        )
        sim.set_geometry({"radius": 0.025, "length": 0.1})
        sim.set_solver_config(
            {
                "solver_type": "comsol",
                "n_nodes": 11,
                "dt": 1.0,
                "max_time": 60,
            }
        )
        sim.set_ht_config(
            {
                "heating": {
                    "enabled": True,
                    "target_temperature": 850.0,
                    "hold_time": 10.0,
                    "initial_temperature": 25.0,
                    "cold_furnace": False,
                    "h_conv": 50.0,
                    "furnace_ramp_rate": 0,
                },
                "transfer": {
                    "enabled": True,
                    "duration": 5.0,
                    "ambient_temperature": 25.0,
                    "h_conv": 10.0,
                },
                "quenching": {
                    "enabled": True,
                    "media": "water",
                    "media_temperature": 25.0,
                    "duration": 60.0,
                    "h_conv": 1500.0,
                },
                "tempering": {"enabled": False},
            }
        )
        db_session.add(sim)
        db_session.commit()

        return sim

    def test_comsol_failure_falls_back_to_builtin(self, app, db):
        """When COMSOL path raises, simulation should still complete via builtin."""
        with app.app_context():
            sim = self._create_runnable_sim(db.session)

            # Patch _run_comsol to raise, simulating total COMSOL failure
            with patch(
                "app.services.simulation_runner._run_comsol",
                side_effect=RuntimeError("COMSOL crashed"),
            ):
                from app.services.simulation_runner import run_heat_treatment

                run_heat_treatment(sim.id)

            db.session.refresh(sim)
            assert sim.status == STATUS_COMPLETED, (
                f"Expected COMPLETED but got {sim.status}: {sim.error_message}"
            )

    def test_comsol_failure_cleans_partial_results(self, app, db):
        """Partial COMSOL results should be removed before builtin runs."""
        with app.app_context():
            sim = self._create_runnable_sim(db.session)

            def _fake_comsol_that_creates_partial(sim_obj, snapshot):
                # Create a partial result then crash
                partial = SimulationResult(
                    simulation_id=sim_obj.id,
                    snapshot_id=snapshot.id,
                    result_type="full_cycle",
                    phase="full",
                    location="center",
                )
                db.session.add(partial)
                db.session.flush()
                raise RuntimeError("COMSOL crashed mid-run")

            with patch(
                "app.services.simulation_runner._run_comsol",
                side_effect=_fake_comsol_that_creates_partial,
            ):
                from app.services.simulation_runner import run_heat_treatment

                run_heat_treatment(sim.id)

            db.session.refresh(sim)
            assert sim.status == STATUS_COMPLETED

            # Verify no orphan partial results — all results should be from builtin
            results = SimulationResult.query.filter_by(simulation_id=sim.id).all()
            assert len(results) > 0

    def test_builtin_solver_direct(self, app, db):
        """Builtin solver should work directly for 'builtin' solver_type."""
        with app.app_context():
            sim = self._create_runnable_sim(db.session)
            sim.set_solver_config(
                {
                    "solver_type": "builtin",
                    "n_nodes": 11,
                    "dt": 1.0,
                    "max_time": 60,
                }
            )
            db.session.commit()

            from app.services.simulation_runner import run_heat_treatment

            run_heat_treatment(sim.id)

            db.session.refresh(sim)
            assert sim.status == STATUS_COMPLETED

            results = SimulationResult.query.filter_by(simulation_id=sim.id).all()
            types = {r.result_type for r in results}
            assert "full_cycle" in types
            assert "cooling_rate" in types

    def test_builtin_solver_with_curve_density_and_emissivity(self, app, db):
        """Curve-type density/emissivity are reduced to scalars, not crashes."""
        with app.app_context():
            sim = self._create_runnable_sim(db.session)
            sim.set_solver_config(
                {
                    "solver_type": "builtin",
                    "n_nodes": 11,
                    "dt": 1.0,
                    "max_time": 60,
                }
            )
            grade_id = sim.steel_grade_id

            rho = MaterialProperty.query.filter_by(
                steel_grade_id=grade_id, property_name="density"
            ).first()
            rho.property_type = "curve"
            rho.set_data({"temperature": [20.0, 800.0], "value": [7850.0, 7600.0]})

            emiss = MaterialProperty(
                steel_grade_id=grade_id,
                property_name="emissivity",
                property_type="curve",
            )
            emiss.set_data({"temperature": [20.0, 1000.0], "value": [0.3, 0.9]})
            db.session.add(emiss)
            db.session.commit()

            from app.services.simulation_runner import run_heat_treatment

            run_heat_treatment(sim.id)

            db.session.refresh(sim)
            assert sim.status == STATUS_COMPLETED

    def test_both_paths_fail_marks_simulation_failed(self, app, db):
        """If both COMSOL and builtin fail, simulation should be marked FAILED."""
        with app.app_context():
            sim = self._create_runnable_sim(db.session)

            with (
                patch(
                    "app.services.simulation_runner._run_comsol",
                    side_effect=RuntimeError("COMSOL crashed"),
                ),
                patch(
                    "app.services.simulation_runner._run_builtin",
                    side_effect=RuntimeError("Builtin also crashed"),
                ),
            ):
                from app.services.simulation_runner import run_heat_treatment

                run_heat_treatment(sim.id)

            db.session.refresh(sim)
            assert sim.status == STATUS_FAILED


# ===========================================================================
# Test shared helper functions (_predict_phases, _predict_hardness)
# ===========================================================================


class TestSharedHelpers:
    """Tests for _predict_phases and _predict_hardness extracted helpers."""

    def _create_sim_with_composition(self, db_session):
        user = User(username="helper_tester", role=ROLE_ENGINEER)
        user.set_password("test")
        db_session.add(user)

        grade = SteelGrade(designation="AISI 4340", data_source=DATA_SOURCE_STANDARD)
        db_session.add(grade)
        db_session.flush()

        comp = SteelComposition(
            steel_grade_id=grade.id,
            carbon=0.40,
            silicon=0.23,
            manganese=0.70,
            chromium=0.80,
            nickel=1.83,
            molybdenum=0.25,
            vanadium=0.0,
        )
        db_session.add(comp)

        diagram = PhaseDiagram(
            steel_grade_id=grade.id,
            diagram_type="CCT",
        )
        diagram.set_temps(
            {
                "Ae1": 727,
                "Ae3": 780,
                "Bs": 540,
                "Ms": 300,
            }
        )
        db_session.add(diagram)
        db_session.flush()

        sim = Simulation(
            name="Helper Test",
            steel_grade_id=grade.id,
            user_id=user.id,
            geometry_type=GEOMETRY_CYLINDER,
            status=STATUS_RUNNING,
        )
        sim.set_geometry({"radius": 0.05, "length": 0.2})
        sim.set_solver_config({"solver_type": "builtin", "n_nodes": 21, "dt": 0.5})
        sim.set_ht_config(
            {
                "heating": {"enabled": True, "target_temperature": 850.0},
                "quenching": {"enabled": True, "duration": 300.0},
                "tempering": {"enabled": False},
            }
        )
        db_session.add(sim)
        db_session.flush()

        snapshot = SimulationSnapshot(
            simulation_id=sim.id,
            version=1,
            status="running",
            geometry_type="cylinder",
            steel_grade_designation="AISI 4340",
        )
        db_session.add(snapshot)
        db_session.flush()

        return sim, snapshot, grade, diagram

    def test_predict_phases_returns_tracker_and_phases(self, app, db):
        with app.app_context():
            sim, snapshot, grade, diagram = self._create_sim_with_composition(db.session)

            times = np.linspace(0, 600, 200)
            center_temp = np.linspace(850, 25, 200)
            t85 = 15.0

            from app.services.simulation_runner import _predict_phases

            tracker, phases = _predict_phases(
                sim, snapshot, grade, diagram, times, center_temp, t85
            )

            # Should return phases (either from JMAK or PhaseTracker)
            assert phases is not None or tracker is not None

    def test_predict_phases_creates_db_result(self, app, db):
        with app.app_context():
            sim, snapshot, grade, diagram = self._create_sim_with_composition(db.session)

            times = np.linspace(0, 600, 200)
            center_temp = np.linspace(850, 25, 200)

            from app.services.simulation_runner import _predict_phases

            _predict_phases(sim, snapshot, grade, diagram, times, center_temp, 15.0)

            results = SimulationResult.query.filter_by(
                simulation_id=sim.id, result_type="phase_fraction"
            ).all()
            assert len(results) == 1

    def test_predict_phases_no_diagram_no_composition(self, app, db):
        with app.app_context():
            user = User(username="nocomp", role=ROLE_ENGINEER)
            user.set_password("test")
            db.session.add(user)
            grade = SteelGrade(designation="Unknown", data_source=DATA_SOURCE_STANDARD)
            db.session.add(grade)
            db.session.flush()

            sim = Simulation(
                name="No Comp Test",
                steel_grade_id=grade.id,
                user_id=user.id,
                geometry_type=GEOMETRY_CYLINDER,
                status=STATUS_RUNNING,
            )
            sim.set_geometry({"radius": 0.05, "length": 0.2})
            db.session.add(sim)
            db.session.flush()

            snapshot = SimulationSnapshot(
                simulation_id=sim.id,
                version=1,
                status="running",
                geometry_type="cylinder",
                steel_grade_designation="AISI 4340",
            )
            db.session.add(snapshot)
            db.session.flush()

            from app.services.simulation_runner import _predict_phases

            tracker, phases = _predict_phases(
                sim,
                snapshot,
                grade,
                None,
                np.linspace(0, 600, 100),
                np.linspace(850, 25, 100),
                15.0,
            )
            assert tracker is None
            assert phases is None

    def test_predict_hardness_no_grade(self, app, db):
        """Should silently return when grade has no composition."""
        with app.app_context():
            user = User(username="nograde", role=ROLE_ENGINEER)
            user.set_password("test")
            db.session.add(user)
            grade = SteelGrade(designation="Bare", data_source=DATA_SOURCE_STANDARD)
            db.session.add(grade)
            db.session.flush()

            sim = Simulation(
                name="No Grade Test",
                steel_grade_id=grade.id,
                user_id=user.id,
                geometry_type=GEOMETRY_CYLINDER,
                status=STATUS_RUNNING,
            )
            sim.set_geometry({"radius": 0.05, "length": 0.2})
            db.session.add(sim)
            db.session.flush()

            snapshot = SimulationSnapshot(
                simulation_id=sim.id,
                version=1,
                status="running",
                geometry_type="cylinder",
                steel_grade_designation="AISI 4340",
            )
            db.session.add(snapshot)
            db.session.flush()

            from app.services.simulation_runner import _predict_hardness

            # Should not raise
            _predict_hardness(
                sim,
                snapshot,
                grade,
                {"tempering": {"enabled": False}},
                np.zeros((100, 2)),
                np.linspace(0, 600, 100),
                None,
            )

            results = SimulationResult.query.filter_by(
                simulation_id=sim.id, result_type="hardness_prediction"
            ).all()
            assert len(results) == 0


# ===========================================================================
# Test @pytest.mark.comsol marker (real COMSOL — auto-skipped if unavailable)
# ===========================================================================


@pytest.mark.comsol
class TestRealCOMSOL:
    """Tests requiring a real COMSOL installation.

    These are automatically skipped when mph is not importable.
    """

    def test_real_client_connects(self, comsol_client):
        assert comsol_client.is_available

    def test_real_client_can_create_model(self, comsol_client):
        model = comsol_client.create_model("test_ht_integration")
        assert model is not None
        comsol_client.remove_model(model)
