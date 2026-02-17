"""Tests for COMSOL mock integration.

Tests the MockCOMSOLClient, WeldModelBuilder with mock client,
ResultsExtractor, and MockSequentialSolver phase estimation.
"""
import pytest
import numpy as np
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.comsol.client import (
    MockCOMSOLClient, COMSOLClient, COMSOLError, COMSOLNotAvailableError,
)
from app.services.comsol.model_builder import WeldModelBuilder
from app.services.comsol.results_extractor import ResultsExtractor
from app.services.comsol.sequential_solver import MockSequentialSolver


# ---------------------------------------------------------------------------
# Helpers — lightweight mock objects that mirror WeldProject / WeldString
# attributes used by WeldModelBuilder and MockSequentialSolver without
# requiring a database or Flask app context.
# ---------------------------------------------------------------------------

class _MockSteelGrade:
    """Minimal steel grade stand-in."""
    designation = 'S355J2'
    display_name = 'S355J2'
    phase_diagram = None
    composition = None

    def get_property(self, name):
        return None


class _MockWeldProject:
    """Minimal WeldProject stand-in."""
    id = 1
    name = 'Test Project'
    cad_file = b'STEP file bytes'
    cad_format = 'step'
    cad_filename = 'geometry.stp'
    steel_grade = _MockSteelGrade()
    steel_grade_id = 1
    process_type = 'mig_mag'
    preheat_temperature = 100.0
    interpass_temperature = 200.0
    interpass_time_default = 60.0
    default_heat_input = 1.5
    default_travel_speed = 5.0
    default_solidification_temp = 1500.0
    status = 'configured'
    current_string = 0
    total_strings = 2
    progress_percent = 0.0
    progress_message = ''
    comsol_model_path = None
    started_at = None
    completed_at = None
    error_message = None

    @property
    def process_label(self):
        return 'MIG/MAG'


class _MockWeldString:
    """Minimal WeldString stand-in."""
    id = 10
    project_id = 1
    project = None  # set after init
    string_number = 1
    body_name = 'string_1'
    layer = 1
    position_in_layer = 1
    name = 'Root Pass'
    heat_input = None
    travel_speed = None
    interpass_time = 60.0
    initial_temp_mode = 'solidification'
    initial_temperature = None
    solidification_temp = None
    calculated_initial_temp = None
    simulation_start_time = 0.0
    simulation_duration = 120.0
    status = 'pending'
    started_at = None
    completed_at = None
    error_message = None

    @property
    def effective_heat_input(self):
        if self.heat_input is not None:
            return self.heat_input
        return self.project.default_heat_input if self.project else 1.5

    @property
    def effective_travel_speed(self):
        if self.travel_speed is not None:
            return self.travel_speed
        return self.project.default_travel_speed if self.project else 5.0

    @property
    def effective_solidification_temp(self):
        if self.solidification_temp is not None:
            return self.solidification_temp
        return self.project.default_solidification_temp if self.project else 1500.0

    @property
    def effective_interpass_time(self):
        if self.interpass_time is not None:
            return self.interpass_time
        return self.project.interpass_time_default if self.project else 60.0

    @property
    def display_name(self):
        if self.name:
            return self.name
        return f"String {self.string_number}"


def _make_mock_project_and_string():
    """Create a connected project + string pair."""
    proj = _MockWeldProject()
    s = _MockWeldString()
    s.project = proj
    s.project_id = proj.id
    return proj, s


# ======================================================================
# MockCOMSOLClient tests
# ======================================================================

class TestMockCOMSOLClient:
    """Test MockCOMSOLClient operations."""

    def test_auto_connected(self):
        client = MockCOMSOLClient()
        assert client._connected is True

    def test_is_available(self):
        client = MockCOMSOLClient()
        assert client.is_available is True

    def test_connect_disconnect(self):
        client = MockCOMSOLClient()
        client.disconnect()
        assert client._connected is False
        client.connect()
        assert client._connected is True

    def test_create_model(self):
        client = MockCOMSOLClient()
        model = client.create_model('TestWeld')
        assert isinstance(model, dict)
        assert model['name'] == 'TestWeld'
        assert 'parameters' in model
        assert 'geometries' in model
        assert 'physics' in model
        assert 'studies' in model
        assert 'results' in model

    def test_create_model_stored_internally(self):
        client = MockCOMSOLClient()
        model = client.create_model('MyModel')
        assert 'MyModel' in client._models
        assert client._models['MyModel'] is model

    def test_import_cad_returns_bodies(self):
        client = MockCOMSOLClient()
        model = client.create_model('CADTest')
        bodies = client.import_cad(model, b'cad-data', 'part.stp', format='step')
        assert isinstance(bodies, list)
        assert len(bodies) > 0
        assert 'string_1' in bodies
        assert 'base_plate' in bodies

    def test_import_cad_updates_model_geometry(self):
        client = MockCOMSOLClient()
        model = client.create_model('CADTest')
        client.import_cad(model, b'cad-data', 'part.stp')
        assert 'cad' in model['geometries']
        assert 'bodies' in model['geometries']['cad']

    def test_set_get_parameter(self):
        client = MockCOMSOLClient()
        model = client.create_model('ParamTest')
        client.set_parameter(model, 'T_preheat', 150.0, 'Preheat temp')
        val = client.get_parameter(model, 'T_preheat')
        assert val['value'] == 150.0
        assert val['description'] == 'Preheat temp'

    def test_get_nonexistent_parameter_returns_none(self):
        client = MockCOMSOLClient()
        model = client.create_model('Test')
        val = client.get_parameter(model, 'nonexistent')
        assert val is None

    def test_run_study(self):
        client = MockCOMSOLClient()
        model = client.create_model('StudyTest')
        client.run_study(model, 'std1')
        assert 'std1' in model['results']
        assert model['results']['std1']['completed'] is True

    def test_evaluate_returns_numpy_array(self):
        client = MockCOMSOLClient()
        model = client.create_model('EvalTest')
        result = client.evaluate(model, 'T')
        assert isinstance(result, np.ndarray)
        assert len(result) == 100
        assert result[0] == 1500.0  # starts high
        assert result[-1] == 100.0  # ends low

    def test_evaluate_with_dataset(self):
        client = MockCOMSOLClient()
        model = client.create_model('Test')
        result = client.evaluate(model, 'T', dataset='dset1')
        assert isinstance(result, np.ndarray)

    def test_export_data_creates_file(self):
        client = MockCOMSOLClient()
        model = client.create_model('ExportTest')
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'output.vtk')
            client.export_data(model, filepath, expression='T', format='vtk')
            assert Path(filepath).exists()

    def test_save_model(self):
        client = MockCOMSOLClient()
        model = client.create_model('SaveTest')
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'model.mph')
            client.save_model(model, filepath)
            # Mock just logs, doesn't create a real file

    def test_load_model_existing_file(self):
        client = MockCOMSOLClient()
        with tempfile.NamedTemporaryFile(suffix='.mph', delete=False) as f:
            f.write(b'mock mph')
            tmppath = f.name
        try:
            model = client.load_model(tmppath)
            assert isinstance(model, dict)
            assert 'parameters' in model
        finally:
            os.unlink(tmppath)

    def test_load_model_nonexistent_raises(self):
        client = MockCOMSOLClient()
        with pytest.raises(COMSOLError, match="not found"):
            client.load_model('/nonexistent/path/model.mph')

    def test_context_manager(self):
        with MockCOMSOLClient() as client:
            assert client._connected is True
            model = client.create_model('ContextTest')
            assert model['name'] == 'ContextTest'
        assert client._connected is False

    def test_multiple_models(self):
        client = MockCOMSOLClient()
        m1 = client.create_model('Model_A')
        m2 = client.create_model('Model_B')
        assert len(client._models) == 2
        assert m1['name'] != m2['name']

    def test_multiple_studies_on_same_model(self):
        client = MockCOMSOLClient()
        model = client.create_model('MultiStudy')
        client.run_study(model, 'std1')
        client.run_study(model, 'std2')
        assert model['results']['std1']['completed'] is True
        assert model['results']['std2']['completed'] is True


# ======================================================================
# WeldModelBuilder with MockCOMSOLClient tests
# ======================================================================

class TestWeldModelBuilderMock:
    """Test WeldModelBuilder using MockCOMSOLClient."""

    def test_create_base_model(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)
        assert isinstance(model, dict)
        assert model['name'].startswith('WeldSim_')

    def test_base_model_imports_cad(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)
        assert 'cad' in model['geometries']

    def test_base_model_no_cad(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        project.cad_file = None
        model = builder.create_base_model(project)
        # Should still create model, just without geometry
        assert isinstance(model, dict)

    def test_base_model_sets_parameters(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)
        assert 'T_preheat' in model['parameters']
        assert model['parameters']['T_preheat']['value'] == 100.0

    def test_base_model_sets_heat_input(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)
        # Q_heat_input = default_heat_input * 1000
        assert 'Q_heat_input' in model['parameters']
        assert model['parameters']['Q_heat_input']['value'] == 1500.0

    def test_base_model_sets_travel_speed(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)
        assert 'v_travel' in model['parameters']
        assert model['parameters']['v_travel']['value'] == 5.0

    def test_base_model_no_steel_grade(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        project.steel_grade = None
        model = builder.create_base_model(project)
        # Should still succeed
        assert isinstance(model, dict)

    def test_activate_string(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project, string = _make_mock_project_and_string()
        model = builder.create_base_model(project)
        builder.activate_string(model, string)
        # Should set heat source parameters
        assert 'Q_string' in model['parameters']
        assert 'v_string' in model['parameters']

    def test_activate_string_with_prev_temps(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project, string = _make_mock_project_and_string()
        string.string_number = 2
        model = builder.create_base_model(project)
        prev_temps = {'string_1': 800.0}
        builder.activate_string(model, string, prev_temps)
        # calculated_initial_temp should be set
        assert string.calculated_initial_temp is not None

    def test_calculate_initial_temp_solidification_mode(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        _, string = _make_mock_project_and_string()
        string.initial_temp_mode = 'solidification'
        temp = builder.calculate_initial_temp(string)
        assert temp == 1500.0

    def test_calculate_initial_temp_manual_mode(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        _, string = _make_mock_project_and_string()
        string.initial_temp_mode = 'manual'
        string.initial_temperature = 800.0
        temp = builder.calculate_initial_temp(string)
        assert temp == 800.0

    def test_calculate_initial_temp_manual_no_value(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        _, string = _make_mock_project_and_string()
        string.initial_temp_mode = 'manual'
        string.initial_temperature = None
        temp = builder.calculate_initial_temp(string)
        # Falls back to solidification temp
        assert temp == 1500.0

    def test_calculate_initial_temp_calculated_first_string(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        _, string = _make_mock_project_and_string()
        string.initial_temp_mode = 'calculated'
        string.string_number = 1
        temp = builder.calculate_initial_temp(string)
        assert temp == 1500.0

    def test_calculate_initial_temp_calculated_with_prev(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        _, string = _make_mock_project_and_string()
        string.initial_temp_mode = 'calculated'
        string.string_number = 2
        prev_temps = {'string_1': 900.0}
        temp = builder.calculate_initial_temp(string, prev_temps)
        # For weld metal, returns solidification temp
        assert temp == 1500.0

    def test_get_model_returns_model(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)
        assert builder.get_model() is model

    def test_get_model_before_creation(self):
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        assert builder.get_model() is None


# ======================================================================
# ResultsExtractor tests
# ======================================================================

class TestResultsExtractor:
    """Test ResultsExtractor with synthetic data."""

    def test_init_creates_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = os.path.join(tmpdir, 'results')
            extractor = ResultsExtractor(folder)
            assert Path(folder).exists()

    def test_get_time_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            times = extractor._get_time_steps(None)
            assert isinstance(times, np.ndarray)
            assert len(times) == 121
            assert times[0] == 0.0
            assert times[-1] == 120.0

    def test_evaluate_at_point(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            times = np.linspace(0, 120, 121)
            temps = extractor._evaluate_at_point(None, (0, 0, 0), times)
            assert isinstance(temps, np.ndarray)
            assert len(temps) == 121
            assert temps[0] > temps[-1]  # cooling

    def test_calculate_t8_5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            times = np.linspace(0, 120, 1000)
            temps = 25 + (1500 - 25) * np.exp(-times / 30.0)
            t85 = extractor._calculate_t8_5(times, temps)
            assert t85 is not None
            assert t85 > 0

    def test_calculate_t8_5_no_crossing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            times = np.linspace(0, 10, 100)
            temps = np.full(100, 300.0)  # constant 300 — never crosses 800
            t85 = extractor._calculate_t8_5(times, temps)
            assert t85 is None

    def test_calculate_max_cooling_rate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            times = np.linspace(0, 120, 121)
            temps = 25 + (1500 - 25) * np.exp(-times / 30.0)
            cr = extractor._calculate_max_cooling_rate(times, temps)
            assert cr is not None
            assert cr > 0

    def test_estimate_phases_fast_cooling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            phases = extractor._estimate_phases(2.0)
            assert phases['martensite'] > 0.9

    def test_estimate_phases_moderate_cooling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            phases = extractor._estimate_phases(30.0)
            assert phases['bainite'] > 0
            assert phases['martensite'] < 0.5

    def test_estimate_phases_slow_cooling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            phases = extractor._estimate_phases(100.0)
            assert phases['ferrite'] > 0.5
            assert phases['pearlite'] > 0

    def test_estimate_phases_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            phases = extractor._estimate_phases(None)
            assert phases['martensite'] == 1.0

    def test_extract_probe_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            probes = [(0, 0, 0), (0.005, 0, 0)]
            names = ['center', 'haz']
            data = extractor.extract_probe_data(None, probes, names)
            assert 'center' in data
            assert 'haz' in data
            assert 'time' in data['center']
            assert 'temperature' in data['center']

    def test_extract_probe_data_auto_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            probes = [(0, 0, 0), (0.005, 0, 0)]
            data = extractor.extract_probe_data(None, probes)
            assert 'probe_0' in data
            assert 'probe_1' in data

    def test_extract_line_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            data = extractor.extract_line_data(
                None, start=(0, 0, 0), end=(0.05, 0, 0), n_points=20
            )
            assert len(data) > 0
            for t, values in data.items():
                assert 'position' in values
                assert 'temperature' in values
                assert len(values['position']) == 20

    def test_extract_field_sequence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            output_folder = Path(tmpdir) / 'fields'
            vtk_files = extractor.extract_field_sequence(
                None, times=[0, 30, 60, 90, 120], output_folder=output_folder
            )
            assert len(vtk_files) == 5
            for f in vtk_files:
                assert f.exists()

    def test_export_vtk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            vtk_path = os.path.join(tmpdir, 'sub', 'test.vtk')
            extractor._export_vtk(None, vtk_path, 60.0)
            assert Path(vtk_path).exists()


# ======================================================================
# MockSequentialSolver — phase estimation (no DB required)
# ======================================================================

class TestMockSequentialSolverPhases:
    """Test MockSequentialSolver phase estimation methods."""

    def _make_solver(self):
        client = MockCOMSOLClient()
        return MockSequentialSolver(client)

    def test_simple_phases_very_fast_cooling(self):
        solver = self._make_solver()
        phases = solver._estimate_phases_simple(2.0)
        assert phases['martensite'] == pytest.approx(0.95)
        assert phases['bainite'] == pytest.approx(0.05)
        assert phases['ferrite'] == 0.0
        assert phases['pearlite'] == 0.0

    def test_simple_phases_moderate_cooling(self):
        solver = self._make_solver()
        phases = solver._estimate_phases_simple(10.0)
        assert phases['martensite'] > 0
        assert phases['bainite'] > 0
        total = sum(phases.values())
        assert total == pytest.approx(1.0)

    def test_simple_phases_slow_cooling(self):
        solver = self._make_solver()
        phases = solver._estimate_phases_simple(30.0)
        assert phases['bainite'] > 0
        assert phases['ferrite'] > 0

    def test_simple_phases_very_slow_cooling(self):
        solver = self._make_solver()
        phases = solver._estimate_phases_simple(100.0)
        assert phases['ferrite'] == 0.6
        assert phases['pearlite'] == 0.3
        assert phases['bainite'] == 0.1
        assert phases['martensite'] == 0.0

    def test_simple_phases_none(self):
        solver = self._make_solver()
        phases = solver._estimate_phases_simple(None)
        assert phases['martensite'] == 1.0

    def test_phase_fractions_sum_to_one(self):
        solver = self._make_solver()
        for t85 in [1, 5, 10, 15, 20, 30, 50, 80, 120]:
            phases = solver._estimate_phases_simple(t85)
            total = sum(phases.values())
            assert total == pytest.approx(1.0, abs=0.05), f"t8/5={t85}: sum={total}"

    def test_predict_hardness_no_steel(self):
        solver = self._make_solver()
        project = _MockWeldProject()
        project.steel_grade = None
        hv = solver._predict_hardness(5.0, {}, project)
        assert hv is None

    def test_cancel_flag(self):
        solver = self._make_solver()
        assert solver.is_cancelled is False
        solver.cancel()
        assert solver.is_cancelled is True


# ======================================================================
# Integration: full mock pipeline (client → builder → study)
# ======================================================================

class TestMockPipelineIntegration:
    """End-to-end test of mock COMSOL pipeline without database."""

    def test_full_pipeline_create_model_and_run(self):
        """Build model, import CAD, set params, run study, evaluate."""
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()

        # Step 1: Create base model
        model = builder.create_base_model(project)
        assert isinstance(model, dict)

        # Step 2: Activate first string
        _, string = _make_mock_project_and_string()
        builder.activate_string(model, string)

        # Step 3: Run study
        client.run_study(model, 'std1')
        assert model['results']['std1']['completed'] is True

        # Step 4: Evaluate temperature
        temps = client.evaluate(model, 'T')
        assert isinstance(temps, np.ndarray)
        assert np.max(temps) > 0

    def test_pipeline_multi_string_sequence(self):
        """Simulate two-string sequence with parameter updates."""
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        project = _MockWeldProject()
        model = builder.create_base_model(project)

        # String 1
        _, s1 = _make_mock_project_and_string()
        s1.string_number = 1
        builder.activate_string(model, s1)
        client.run_study(model, 'std1')

        # String 2
        _, s2 = _make_mock_project_and_string()
        s2.string_number = 2
        s2.id = 20
        prev_temps = {'string_1': 1500.0}
        builder.activate_string(model, s2, prev_temps)
        client.run_study(model, 'std1')

        # Both strings should have calculated_initial_temp
        assert s1.calculated_initial_temp is not None
        assert s2.calculated_initial_temp is not None

    def test_pipeline_extract_results(self):
        """Create model, run, extract results."""
        client = MockCOMSOLClient()
        model = client.create_model('ExtractTest')
        client.run_study(model, 'std1')

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)

            # Extract probe data
            probes = [(0, 0, 0), (0.003, 0, 0), (0.006, 0, 0)]
            data = extractor.extract_probe_data(model, probes, ['center', 'cghaz', 'fghaz'])
            assert len(data) == 3

            # Each probe has time and temperature
            for name in ['center', 'cghaz', 'fghaz']:
                assert name in data
                assert len(data[name]['time']) == 121
                assert len(data[name]['temperature']) == 121

    def test_pipeline_export_vtk_sequence(self):
        """Run study and export VTK field sequence."""
        client = MockCOMSOLClient()
        model = client.create_model('VTKTest')
        client.run_study(model, 'std1')

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ResultsExtractor(tmpdir)
            output_folder = Path(tmpdir) / 'vtk_sequence'
            files = extractor.extract_field_sequence(
                model, times=[0, 30, 60, 90, 120], output_folder=output_folder
            )
            assert len(files) == 5
            assert all(f.suffix == '.vtk' for f in files)


# ======================================================================
# Real COMSOLClient (without COMSOL installed) — error handling tests
# ======================================================================

class TestCOMSOLClientWithoutInstallation:
    """Test COMSOLClient when COMSOL is not available."""

    def test_is_available_without_mph(self):
        """is_available returns False when mph not installed."""
        client = COMSOLClient()
        # In a normal test env mph is not installed
        # This tests the actual import check
        available = client.is_available
        # Result depends on environment — just check it returns bool
        assert isinstance(available, bool)

    def test_connect_without_mph_raises(self):
        """connect() raises COMSOLNotAvailableError or COMSOLError."""
        client = COMSOLClient()
        if not client.is_available:
            with pytest.raises((COMSOLNotAvailableError, COMSOLError)):
                client.connect()
