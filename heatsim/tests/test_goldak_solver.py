"""Tests for Goldak double-ellipsoid heat source solver."""
import pytest
import numpy as np

from app.services.goldak_solver import (
    GoldakSolver, GoldakParams, GoldakSolverConfig, GoldakResult,
    estimate_pool_params, SOLIDUS_TEMP,
)


class TestGoldakParams:
    """Test GoldakParams dataclass."""

    def test_default_fractions_sum_to_two(self):
        params = GoldakParams()
        assert params.f_f + params.f_r == pytest.approx(2.0)

    def test_default_pool_dimensions_positive(self):
        params = GoldakParams()
        assert params.b > 0
        assert params.c > 0
        assert params.a_f > 0
        assert params.a_r > 0

    def test_rear_longer_than_front(self):
        params = GoldakParams()
        assert params.a_r > params.a_f

    def test_custom_params(self):
        params = GoldakParams(Q=5000, v=0.003, b=0.005, c=0.004)
        assert params.Q == 5000
        assert params.v == 0.003
        assert params.b == 0.005

    def test_alpha_property(self):
        params = GoldakParams(k=40.0, rho=7850.0, Cp=500.0)
        expected = 40.0 / (7850.0 * 500.0)
        assert params.alpha == pytest.approx(expected)


class TestGoldakSolverConfig:

    def test_default_grid(self):
        config = GoldakSolverConfig()
        assert config.ny == 41
        assert config.nz == 31

    def test_default_time_step(self):
        config = GoldakSolverConfig()
        assert config.dt == 0.05

    def test_custom_config(self):
        config = GoldakSolverConfig(ny=21, nz=11, dt=0.1, total_time=60.0)
        assert config.ny == 21
        assert config.nz == 11
        assert config.total_time == 60.0


class TestGoldakSource:
    """Test the Goldak heat source distribution."""

    def test_source_is_nonnegative(self):
        """Heat source should be non-negative everywhere."""
        params = GoldakParams()
        config = GoldakSolverConfig(ny=21, nz=11)
        solver = GoldakSolver(params, config)
        # At t where torch is at the section
        t_pass = config.total_time * 0.15
        q = solver._goldak_source_2d(t_pass)
        assert np.all(q >= 0)

    def test_source_peak_at_center(self):
        """Maximum heat source should be at y=0, z=0."""
        params = GoldakParams()
        config = GoldakSolverConfig(ny=21, nz=11)
        solver = GoldakSolver(params, config)
        t_pass = config.total_time * 0.15
        q = solver._goldak_source_2d(t_pass)
        # Center indices
        iy_center = config.ny // 2
        # Peak should be at (z=0, y=0)
        assert q[0, iy_center] == np.max(q)

    def test_source_decays_with_distance(self):
        """Source should decay away from center in y."""
        params = GoldakParams()
        config = GoldakSolverConfig(ny=41, nz=11)
        solver = GoldakSolver(params, config)
        t_pass = config.total_time * 0.15
        q = solver._goldak_source_2d(t_pass)
        iy_center = config.ny // 2
        # q at center > q at edge (surface z=0)
        assert q[0, iy_center] > q[0, 0]

    def test_source_zero_far_from_torch(self):
        """Source should be negligible when torch is far from section."""
        params = GoldakParams()
        config = GoldakSolverConfig(ny=11, nz=11, total_time=120.0)
        solver = GoldakSolver(params, config)
        # Very early time — torch far away
        q_early = solver._goldak_source_2d(0.0)
        q_peak = solver._goldak_source_2d(config.total_time * 0.15)
        # Early source should be much smaller than peak
        assert np.max(q_early) < np.max(q_peak) * 0.01

    def test_source_symmetric_in_y(self):
        """Source should be symmetric about y=0."""
        params = GoldakParams()
        config = GoldakSolverConfig(ny=41, nz=11)
        solver = GoldakSolver(params, config)
        t_pass = config.total_time * 0.15
        q = solver._goldak_source_2d(t_pass)
        # Compare left and right halves at surface
        ny_mid = config.ny // 2
        np.testing.assert_allclose(
            q[0, :ny_mid], q[0, ny_mid + 1:][::-1], rtol=1e-10
        )


class TestGoldakSolver:
    """Test the 2D FD solver."""

    def _make_solver(self, Q=5000, total_time=30.0, ny=21, nz=11):
        params = GoldakParams(Q=Q, v=0.005)
        config = GoldakSolverConfig(ny=ny, nz=nz, dt=0.1,
                                    total_time=total_time, output_interval=10)
        return GoldakSolver(params, config)

    def test_solver_completes(self):
        """Solver runs without error and returns GoldakResult."""
        solver = self._make_solver(total_time=10.0)
        result = solver.solve()
        assert isinstance(result, GoldakResult)
        assert result.peak_temperature_map.shape == (11, 21)

    def test_peak_temp_exceeds_preheat(self):
        """Peak temperature should exceed initial temperature near weld."""
        solver = self._make_solver(Q=5000, total_time=30.0)
        result = solver.solve()
        assert np.max(result.peak_temperature_map) > solver.params.T0 + 100

    def test_temperature_decays_with_distance(self):
        """Peak temperature should decrease away from weld center."""
        solver = self._make_solver(Q=5000, total_time=30.0)
        result = solver.solve()
        surface_profile = result.peak_temperature_map[0, :]
        center_idx = solver.config.ny // 2
        # Center > edge
        assert surface_profile[center_idx] > surface_profile[0]

    def test_zero_power_gives_uniform_temperature(self):
        """With Q=0, temperature should remain at T0."""
        solver = self._make_solver(Q=0.0, total_time=10.0)
        result = solver.solve()
        # All temperatures should be approximately T0
        np.testing.assert_allclose(
            result.peak_temperature_map, solver.params.T0, atol=1.0
        )

    def test_snapshots_stored(self):
        """Temperature field snapshots are stored at output intervals."""
        solver = self._make_solver(total_time=10.0)
        result = solver.solve()
        assert result.temperature_field.shape[0] > 1
        assert len(result.times) == result.temperature_field.shape[0]

    def test_probe_thermal_cycles_recorded(self):
        """Thermal cycles at probe points are recorded."""
        solver = self._make_solver(Q=5000, total_time=30.0)
        result = solver.solve()
        assert 'center' in result.probe_thermal_cycles
        center_cycle = result.probe_thermal_cycles['center']
        assert len(center_cycle['times']) > 1
        assert len(center_cycle['temps']) == len(center_cycle['times'])

    def test_t8_5_map_shape(self):
        """t8/5 map has correct shape."""
        solver = self._make_solver(Q=5000, total_time=60.0)
        result = solver.solve()
        assert result.t8_5_map.shape == (11, 21)

    def test_solver_info_present(self):
        """Solver info dict is populated."""
        solver = self._make_solver(total_time=10.0)
        result = solver.solve()
        assert 'wall_time_s' in result.solver_info
        assert 'n_steps' in result.solver_info
        assert result.solver_info['ny'] == 21
        assert result.solver_info['nz'] == 11

    def test_goldak_params_in_result(self):
        """Goldak parameters are included in result."""
        solver = self._make_solver()
        result = solver.solve()
        assert 'Q_W' in result.goldak_params
        assert 'b_mm' in result.goldak_params

    def test_initial_field_used(self):
        """Custom initial field is used as starting condition."""
        solver = self._make_solver(Q=0.0, total_time=5.0)
        initial = np.full((11, 21), 200.0)
        result = solver.solve(initial_field=initial)
        # Temperature should start near 200, not default T0
        # With Q=0 and convection, it may cool slightly, but should be > T0
        assert np.mean(result.peak_temperature_map) > solver.params.T0 + 50

    def test_progress_callback_called(self):
        """Progress callback is invoked during simulation."""
        solver = self._make_solver(total_time=10.0)
        progress_values = []
        result = solver.solve(progress_callback=lambda p: progress_values.append(p))
        assert len(progress_values) > 0
        assert progress_values[-1] > 0

    def test_to_dict_serializable(self):
        """Result.to_dict() returns JSON-serializable data."""
        import json
        solver = self._make_solver(total_time=10.0)
        result = solver.solve()
        d = result.to_dict()
        # Should not raise
        json.dumps(d)
        assert 'peak_temperature_map' in d
        assert 'surface_peak_temps' in d

    def test_center_t8_5_property(self):
        """center_t8_5 property returns float or None."""
        solver = self._make_solver(total_time=10.0)
        result = solver.solve()
        val = result.center_t8_5
        assert val is None or isinstance(val, float)


class TestPoolEstimation:
    """Test weld pool parameter estimation."""

    def test_reasonable_width_for_mig(self):
        est = estimate_pool_params(1.5, 'mig_mag')
        assert 0.002 < est['b'] < 0.010  # 2-10mm

    def test_reasonable_penetration_for_saw(self):
        est = estimate_pool_params(2.0, 'saw')
        assert est['c'] > est['b'] * 0.5  # SAW has deep penetration

    def test_gtaw_shallower_than_saw(self):
        est_gtaw = estimate_pool_params(1.0, 'gtaw')
        est_saw = estimate_pool_params(1.0, 'saw')
        assert est_gtaw['c'] < est_saw['c']

    def test_higher_heat_input_wider_pool(self):
        est_low = estimate_pool_params(0.5, 'mig_mag')
        est_high = estimate_pool_params(3.0, 'mig_mag')
        assert est_high['b'] > est_low['b']

    def test_rear_longer_than_front(self):
        est = estimate_pool_params(1.5, 'mig_mag')
        assert est['a_r'] > est['a_f']

    def test_returns_mm_values(self):
        est = estimate_pool_params(1.5, 'mig_mag')
        assert 'b_mm' in est
        assert est['b_mm'] == pytest.approx(est['b'] * 1000)

    def test_all_processes(self):
        for process in ['gtaw', 'mig_mag', 'saw', 'smaw']:
            est = estimate_pool_params(1.5, process)
            assert est['b'] > 0
            assert est['c'] > 0


class TestGoldakHAZExtraction:
    """Test HAZ zone extraction from Goldak results."""

    def test_haz_extraction_structure(self):
        """extract_haz_from_field returns expected keys."""
        params = GoldakParams(Q=5000, v=0.005)
        config = GoldakSolverConfig(ny=31, nz=21, dt=0.1,
                                    total_time=40.0, output_interval=20)
        solver = GoldakSolver(params, config)
        result = solver.solve()
        solver.solve_result = result  # Set for extraction
        haz = solver.extract_haz_from_field()
        assert 'zone_boundaries' in haz
        assert 'distances_mm' in haz
        assert 'peak_temperatures' in haz


class TestGoldakSolverEdgeCases:
    """Edge case tests."""

    def test_even_ny_becomes_odd(self):
        """Even ny is incremented to odd for center node."""
        config = GoldakSolverConfig(ny=20)
        solver = GoldakSolver(GoldakParams(), config)
        assert solver.config.ny == 21

    def test_very_small_time_step(self):
        """Solver handles small dt without error."""
        params = GoldakParams(Q=3000)
        config = GoldakSolverConfig(ny=11, nz=11, dt=0.01, total_time=2.0,
                                    output_interval=10)
        solver = GoldakSolver(params, config)
        result = solver.solve()
        assert result is not None

    def test_weld_pool_boundary_extraction(self):
        """Weld pool boundary is a dict with y_mm and z_mm."""
        params = GoldakParams(Q=5000)
        config = GoldakSolverConfig(ny=21, nz=11, dt=0.1, total_time=30.0,
                                    output_interval=20)
        solver = GoldakSolver(params, config)
        result = solver.solve()
        assert 'y_mm' in result.weld_pool_boundary
        assert 'z_mm' in result.weld_pool_boundary

    def test_fusion_zone_area(self):
        """Fusion zone area is non-negative."""
        params = GoldakParams(Q=5000)
        config = GoldakSolverConfig(ny=21, nz=11, dt=0.1, total_time=30.0,
                                    output_interval=20)
        solver = GoldakSolver(params, config)
        result = solver.solve()
        assert result.fusion_zone_area_mm2 >= 0
