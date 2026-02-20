"""Tests for Hollomon-Jaffe tempering hardness calculation."""
import math
import pytest
from unittest.mock import MagicMock

from app.services.hardness_predictor import HardnessPredictor, HardnessResult, POSITION_KEYS


@pytest.fixture
def mock_composition():
    """Create a mock SteelComposition for AISI 4340."""
    comp = MagicMock()
    comp.to_dict.return_value = {
        'C': 0.40, 'Mn': 0.70, 'Si': 0.25,
        'Cr': 0.80, 'Ni': 1.80, 'Mo': 0.25,
        'V': 0.0, 'W': 0.0, 'Cu': 0.0,
        'P': 0.0, 'S': 0.0, 'N': 0.0, 'B': 0.0,
        'Hp': 20.0,
    }
    comp.carbon_equivalent_iiw = 0.40 + 0.70/6 + (0.80 + 0.25)/5 + 1.80/15
    comp.ideal_diameter_di = 3.5
    return comp


class TestHJPFormula:
    def test_hjp_formula(self, mock_composition):
        """HJP = T_K * (Hp + log10(t_hours)) should match manual calculation."""
        predictor = HardnessPredictor(mock_composition)
        temp_c = 600
        hold_min = 60  # 1 hour
        hp = 20.0

        _, hjp = predictor.tempered_hardness(500.0, temp_c, hold_min, hp)

        # Manual: (600 + 273.15) * (20 + log10(1.0)) = 873.15 * 20 = 17463
        expected = (600 + 273.15) * (20.0 + math.log10(1.0))
        assert abs(hjp - expected) < 1.0

    def test_hjp_typical_range(self, mock_composition):
        """HJP should be in typical range 12000-22000 for normal tempering."""
        predictor = HardnessPredictor(mock_composition)

        # Low temp, short time: ~12000
        _, hjp_low = predictor.tempered_hardness(500.0, 300, 30, 20.0)
        assert 10000 < hjp_low < 15000

        # High temp, long time: ~20000
        _, hjp_high = predictor.tempered_hardness(500.0, 700, 240, 20.0)
        assert 18000 < hjp_high < 23000


class TestTemperedHardness:
    def test_tempered_hardness_lower_than_quenched(self, mock_composition):
        """Tempered hardness must be <= as-quenched hardness."""
        predictor = HardnessPredictor(mock_composition)
        hv_quenched = 550.0

        hv_tempered, _ = predictor.tempered_hardness(hv_quenched, 600, 60, 20.0)
        assert hv_tempered <= hv_quenched

    def test_higher_temp_more_softening(self, mock_composition):
        """Higher tempering temperature should produce more softening."""
        predictor = HardnessPredictor(mock_composition)
        hv_quenched = 550.0

        hv_low, _ = predictor.tempered_hardness(hv_quenched, 400, 60, 20.0)
        hv_high, _ = predictor.tempered_hardness(hv_quenched, 650, 60, 20.0)

        assert hv_high <= hv_low

    def test_longer_time_more_softening(self, mock_composition):
        """Longer hold time should produce more softening."""
        predictor = HardnessPredictor(mock_composition)
        hv_quenched = 550.0

        hv_short, _ = predictor.tempered_hardness(hv_quenched, 550, 30, 20.0)
        hv_long, _ = predictor.tempered_hardness(hv_quenched, 550, 480, 20.0)

        assert hv_long <= hv_short

    def test_tempered_hardness_floor(self, mock_composition):
        """Tempered hardness should never drop below FP equilibrium hardness."""
        predictor = HardnessPredictor(mock_composition)
        hv_quenched = 550.0

        # Extreme tempering: very high temp, very long time
        hv_tempered, _ = predictor.tempered_hardness(hv_quenched, 750, 6000, 20.0)

        # FP floor for C=0.40: 42 + 223*0.40 + 53*0.25 + 30*0.70 = ~163
        assert hv_tempered >= 100.0  # At least minimum

    def test_no_tempering_no_tempered_hardness(self):
        """HardnessResult with no tempering should have empty tempered dicts."""
        result = HardnessResult()
        result.hardness_hv = {'center': 500.0, 'surface': 450.0}
        d = result.to_dict()
        assert d['tempered_hardness_hv'] == {}
        assert d['tempered_hardness_hrc'] == {}
        assert d['hollomon_jaffe_parameter'] == 0.0


class TestTemperedResultInDict:
    def test_tempered_result_in_dict(self, mock_composition):
        """to_dict() should include all tempered hardness fields."""
        result = HardnessResult()
        result.hardness_hv = {'center': 550.0}
        result.tempered_hardness_hv = {'center': 400.0}
        result.tempered_hardness_hrc = {'center': 40.0}
        result.hollomon_jaffe_parameter = 17463.0
        result.tempering_temperature = 600.0
        result.tempering_time = 60.0

        d = result.to_dict()
        assert d['tempered_hardness_hv'] == {'center': 400.0}
        assert d['tempered_hardness_hrc'] == {'center': 40.0}
        assert d['hollomon_jaffe_parameter'] == 17463.0
        assert d['tempering_temperature'] == 600.0
        assert d['tempering_time'] == 60.0
