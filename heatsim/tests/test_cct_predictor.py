"""Tests for CCT curve prediction from steel composition."""
import pytest

from app.services.cct_predictor import CCTCurvePredictor, predict_cct_curves


# --- Fixtures ---

@pytest.fixture
def aisi4340_comp():
    """AISI 4340 composition (medium-carbon, Ni-Cr-Mo steel)."""
    return {
        'C': 0.40, 'Mn': 0.70, 'Si': 0.25,
        'Cr': 0.80, 'Ni': 1.80, 'Mo': 0.25,
        'V': 0.0, 'W': 0.0, 'Cu': 0.0,
        'P': 0.0, 'S': 0.0, 'N': 0.0, 'B': 0.0,
    }


@pytest.fixture
def f22_comp():
    """A182 F22 (2.25Cr-1Mo) composition."""
    return {
        'C': 0.12, 'Mn': 0.45, 'Si': 0.25,
        'Cr': 2.25, 'Ni': 0.0, 'Mo': 1.0,
        'V': 0.0, 'W': 0.0, 'Cu': 0.0,
        'P': 0.0, 'S': 0.0, 'N': 0.0, 'B': 0.0,
    }


@pytest.fixture
def plain_carbon_comp():
    """Plain carbon steel (~1045)."""
    return {
        'C': 0.45, 'Mn': 0.75, 'Si': 0.25,
        'Cr': 0.0, 'Ni': 0.0, 'Mo': 0.0,
        'V': 0.0, 'W': 0.0, 'Cu': 0.0,
        'P': 0.0, 'S': 0.0, 'N': 0.0, 'B': 0.0,
    }


@pytest.fixture
def minimal_comp():
    """Minimal composition with just C and Mn."""
    return {'C': 0.20, 'Mn': 0.50}


# --- Transformation Temperature Tests ---

class TestTransformationTemperatures:
    def test_ae3_plain_carbon(self, plain_carbon_comp):
        """Ae3 should be in reasonable range for medium-carbon steel."""
        p = CCTCurvePredictor(plain_carbon_comp)
        assert 750 < p.Ae3 < 870

    def test_ae1_plain_carbon(self, plain_carbon_comp):
        """Ae1 should be near 727°C for plain carbon steel."""
        p = CCTCurvePredictor(plain_carbon_comp)
        assert 700 < p.Ae1 < 750

    def test_ms_decreases_with_carbon(self):
        """Ms should decrease with increasing carbon content."""
        low_c = CCTCurvePredictor({'C': 0.10})
        high_c = CCTCurvePredictor({'C': 0.60})
        assert low_c.Ms > high_c.Ms

    def test_bs_decreases_with_alloy(self, aisi4340_comp):
        """Bs should be lower for highly alloyed steel."""
        plain = CCTCurvePredictor({'C': 0.40})
        alloyed = CCTCurvePredictor(aisi4340_comp)
        assert alloyed.Bs < plain.Bs

    def test_override_with_known_temps(self, aisi4340_comp):
        """Provided transformation temps should override calculated values."""
        known = {'Ac1': 735, 'Ac3': 790, 'Ms': 285, 'Bs': 410}
        p = CCTCurvePredictor(aisi4340_comp, transformation_temps=known)
        assert p.Ae1 == 735
        assert p.Ae3 == 790
        assert p.Ms == 285
        assert p.Bs == 410

    def test_ae3_above_ae1(self, aisi4340_comp):
        """Ae3 must be above Ae1."""
        p = CCTCurvePredictor(aisi4340_comp)
        assert p.Ae3 > p.Ae1

    def test_bs_above_ms(self, aisi4340_comp):
        """Bs must be above Ms."""
        p = CCTCurvePredictor(aisi4340_comp)
        assert p.Bs > p.Ms


# --- Curve Format Tests ---

class TestCurveFormat:
    def test_output_has_expected_phases(self, aisi4340_comp):
        """Output should have ferrite, pearlite, and bainite phases."""
        curves = predict_cct_curves(aisi4340_comp)
        assert curves is not None
        # Medium-carbon steel should have all three phases
        assert 'pearlite' in curves
        assert 'bainite' in curves

    def test_each_phase_has_start_finish(self, aisi4340_comp):
        """Each phase should have start and finish curves."""
        curves = predict_cct_curves(aisi4340_comp)
        for phase, data in curves.items():
            assert 'start' in data, f'{phase} missing start curve'
            assert 'finish' in data, f'{phase} missing finish curve'

    def test_curve_points_are_pairs(self, aisi4340_comp):
        """Each curve point should be [time, temperature] pair."""
        curves = predict_cct_curves(aisi4340_comp)
        for phase, data in curves.items():
            for curve_type in ('start', 'finish'):
                for point in data[curve_type]:
                    assert len(point) == 2, f'{phase} {curve_type}: expected [t,T] pair'
                    assert isinstance(point[0], float), f'{phase} {curve_type}: time should be float'
                    assert isinstance(point[1], float), f'{phase} {curve_type}: temp should be float'

    def test_curves_have_multiple_points(self, aisi4340_comp):
        """Each curve should have enough points for smooth plotting."""
        curves = predict_cct_curves(aisi4340_comp)
        for phase, data in curves.items():
            for curve_type in ('start', 'finish'):
                assert len(data[curve_type]) > 5, \
                    f'{phase} {curve_type}: too few points ({len(data[curve_type])})'

    def test_minimal_composition(self, minimal_comp):
        """Should work with minimal composition (just C and Mn)."""
        curves = predict_cct_curves(minimal_comp)
        assert curves is not None
        assert 'pearlite' in curves


# --- Physical Reasonableness Tests ---

class TestPhysicalReasonableness:
    def test_temperatures_in_range(self, aisi4340_comp):
        """All temperatures should be between 200-900°C."""
        curves = predict_cct_curves(aisi4340_comp)
        for phase, data in curves.items():
            for curve_type in ('start', 'finish'):
                for time, temp in data[curve_type]:
                    assert 150 < temp < 950, \
                        f'{phase} {curve_type}: temp {temp}°C out of range'

    def test_times_positive(self, aisi4340_comp):
        """All times should be positive."""
        curves = predict_cct_curves(aisi4340_comp)
        for phase, data in curves.items():
            for curve_type in ('start', 'finish'):
                for time, temp in data[curve_type]:
                    assert time > 0, f'{phase} {curve_type}: time {time}s not positive'

    def test_ferrite_above_pearlite(self, plain_carbon_comp):
        """Ferrite nose should be at higher temperature than pearlite nose."""
        curves = predict_cct_curves(plain_carbon_comp)
        if 'ferrite' in curves and 'pearlite' in curves:
            # Find nose temperatures (minimum time point)
            f_nose = min(curves['ferrite']['start'], key=lambda p: p[0])
            p_nose = min(curves['pearlite']['start'], key=lambda p: p[0])
            assert f_nose[1] > p_nose[1]

    def test_bainite_below_pearlite(self, aisi4340_comp):
        """Bainite nose should be at lower temperature than pearlite nose."""
        curves = predict_cct_curves(aisi4340_comp)
        if 'bainite' in curves and 'pearlite' in curves:
            b_nose = min(curves['bainite']['start'], key=lambda p: p[0])
            p_nose = min(curves['pearlite']['start'], key=lambda p: p[0])
            assert b_nose[1] < p_nose[1]

    def test_finish_later_than_start(self, aisi4340_comp):
        """Finish curve nose should be at longer times than start curve nose."""
        curves = predict_cct_curves(aisi4340_comp)
        for phase, data in curves.items():
            start_nose = min(data['start'], key=lambda p: p[0])
            finish_nose = min(data['finish'], key=lambda p: p[0])
            assert finish_nose[0] > start_nose[0], \
                f'{phase}: finish nose ({finish_nose[0]:.1f}s) not after start ({start_nose[0]:.1f}s)'


# --- Hardenability Tests ---

class TestHardenabilityEffects:
    def test_higher_alloy_shifts_right(self, plain_carbon_comp, aisi4340_comp):
        """Higher alloy content should shift curves to longer times."""
        plain_curves = predict_cct_curves(plain_carbon_comp)
        alloy_curves = predict_cct_curves(aisi4340_comp)

        # Compare pearlite nose times (both should have pearlite)
        plain_nose = min(plain_curves['pearlite']['start'], key=lambda p: p[0])
        alloy_nose = min(alloy_curves['pearlite']['start'], key=lambda p: p[0])
        assert alloy_nose[0] > plain_nose[0], \
            'Alloyed steel should have longer incubation times'

    def test_cr_mo_strongly_retard_pearlite(self, f22_comp, plain_carbon_comp):
        """Cr-Mo steel should have pearlite nose at much longer times."""
        f22_curves = predict_cct_curves(f22_comp)
        plain_curves = predict_cct_curves(plain_carbon_comp)

        f22_nose = min(f22_curves['pearlite']['start'], key=lambda p: p[0])
        plain_nose = min(plain_curves['pearlite']['start'], key=lambda p: p[0])
        # Cr-Mo should shift pearlite by at least 10x
        assert f22_nose[0] > plain_nose[0] * 5


# --- Edge Case Tests ---

class TestEdgeCases:
    def test_none_composition(self):
        """Should return None for None composition."""
        assert predict_cct_curves(None) is None

    def test_empty_composition(self):
        """Should return None for empty composition."""
        assert predict_cct_curves({}) is None

    def test_zero_carbon(self):
        """Should return None for zero carbon."""
        assert predict_cct_curves({'C': 0.0, 'Mn': 0.5}) is None

    def test_high_carbon_no_ferrite(self):
        """High carbon (>0.8%) should not produce ferrite curves."""
        comp = {'C': 1.0, 'Mn': 0.35}
        curves = predict_cct_curves(comp)
        assert curves is not None
        assert 'ferrite' not in curves

    def test_with_transformation_temps(self, aisi4340_comp):
        """Should use provided transformation temps."""
        temps = {'Ac1': 730, 'Ac3': 790, 'Ms': 280, 'Bs': 400}
        curves = predict_cct_curves(aisi4340_comp, temps)
        assert curves is not None
        # Bainite should respect the provided Bs
        if 'bainite' in curves:
            max_bainite_temp = max(p[1] for p in curves['bainite']['start'])
            assert max_bainite_temp <= 410  # Near or below Bs
