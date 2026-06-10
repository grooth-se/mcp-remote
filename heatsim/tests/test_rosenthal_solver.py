"""Tests for Rosenthal analytical solver t8/5 edge cases."""

from unittest.mock import patch

import numpy as np

from app.services.rosenthal_solver import RosenthalParams, RosenthalSolver


class TestT85AtPoint:
    def _solver(self):
        return RosenthalSolver(RosenthalParams())

    def test_near_weld_line_positive(self):
        solver = self._solver()
        t85 = solver.t8_5_at_point(y=0.002)
        assert t85 is None or t85 > 0

    def test_far_from_weld_returns_none(self):
        solver = self._solver()
        assert solver.t8_5_at_point(y=0.5) is None

    def test_empty_thermal_cycle_returns_none(self):
        solver = self._solver()
        empty = (np.array([]), np.array([]))
        with patch.object(RosenthalSolver, "thermal_cycle_at_point", return_value=empty):
            assert solver.t8_5_at_point(y=0.002) is None

    def test_nan_tainted_cycle_no_crash(self):
        solver = self._solver()
        times = np.linspace(0, 10, 6)
        temps = np.array([900.0, np.nan, 700.0, np.nan, 450.0, 300.0])
        with patch.object(RosenthalSolver, "thermal_cycle_at_point", return_value=(times, temps)):
            result = solver.t8_5_at_point(y=0.002)
            assert result is None or result > 0

    def test_flat_cycle_returns_none(self):
        solver = self._solver()
        times = np.linspace(0, 10, 6)
        temps = np.full(6, 600.0)
        with patch.object(RosenthalSolver, "thermal_cycle_at_point", return_value=(times, temps)):
            assert solver.t8_5_at_point(y=0.002) is None
