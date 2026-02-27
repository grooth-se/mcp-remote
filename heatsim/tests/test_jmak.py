"""Tests for JMAK kinetics, Scheil additivity, and critical temperatures."""
import math
import pytest
import numpy as np

from app.services.phase_transformation.critical_temperatures import (
    calculate_critical_temperatures, calc_ae1, calc_ae3, calc_bs, calc_ms, calc_mf,
)
from app.services.phase_transformation.jmak_model import (
    JMAKModel, gaussian_b_function, arrhenius_b_function,
    create_b_function, fit_jmak_parameters,
)
from app.services.phase_transformation.martensite_model import KoistinenMarburgerModel
from app.services.phase_transformation.scheil_additivity import (
    calculate_cct_transformation,
)
from app.services.phase_transformation.ttt_generator import (
    generate_ttt_diagram, generate_ttt_for_plotting,
)
from app.services.phase_transformation.cct_generator import (
    generate_cct_from_ttt, generate_cct_phase_fractions,
)


# --- Fixtures ---

@pytest.fixture
def aisi4340_comp():
    return {
        'C': 0.40, 'Mn': 0.70, 'Si': 0.25,
        'Cr': 0.80, 'Ni': 1.80, 'Mo': 0.25,
    }


@pytest.fixture
def f22_comp():
    return {
        'C': 0.12, 'Mn': 0.45, 'Si': 0.25,
        'Cr': 2.25, 'Ni': 0.0, 'Mo': 1.0,
    }


@pytest.fixture
def plain_carbon_comp():
    return {
        'C': 0.45, 'Mn': 0.75, 'Si': 0.25,
        'Cr': 0.0, 'Ni': 0.0, 'Mo': 0.0,
    }


@pytest.fixture
def pearlite_jmak():
    """JMAK model for pearlite with Gaussian b-function."""
    b_func = gaussian_b_function(b_max=0.001, t_nose=650, sigma=60)
    return JMAKModel(n=1.5, b_func=b_func, temp_range=(400, 727))


@pytest.fixture
def bainite_jmak():
    """JMAK model for bainite."""
    b_func = gaussian_b_function(b_max=0.005, t_nose=450, sigma=50)
    return JMAKModel(n=2.5, b_func=b_func, temp_range=(250, 550))


@pytest.fixture
def km_model():
    """Koistinen-Marburger model."""
    return KoistinenMarburgerModel(ms=320, mf=120, alpha=0.011)


# === Critical Temperatures ===

class TestCriticalTemperatures:
    def test_ae1_plain_carbon(self, plain_carbon_comp):
        """Ae1 should be near 727°C for plain carbon steel."""
        temps = calculate_critical_temperatures(plain_carbon_comp)
        assert 700 < temps['Ae1'] < 750

    def test_ae3_plain_carbon(self, plain_carbon_comp):
        temps = calculate_critical_temperatures(plain_carbon_comp)
        assert 750 < temps['Ae3'] < 870

    def test_ae3_higher_than_ae1(self, aisi4340_comp):
        temps = calculate_critical_temperatures(aisi4340_comp)
        assert temps['Ae3'] > temps['Ae1']

    def test_bs_alloyed(self, aisi4340_comp):
        temps = calculate_critical_temperatures(aisi4340_comp)
        assert 300 < temps['Bs'] < 600

    def test_ms_plain_carbon(self, plain_carbon_comp):
        temps = calculate_critical_temperatures(plain_carbon_comp)
        assert 200 < temps['Ms'] < 400

    def test_ms_f22(self, f22_comp):
        temps = calculate_critical_temperatures(f22_comp)
        # F22 has higher Ms due to low carbon
        assert 350 < temps['Ms'] < 500

    def test_mf_below_ms(self, aisi4340_comp):
        temps = calculate_critical_temperatures(aisi4340_comp)
        assert temps['Mf'] < temps['Ms']

    def test_calculate_all_keys(self, aisi4340_comp):
        temps = calculate_critical_temperatures(aisi4340_comp)
        assert 'Ae1' in temps
        assert 'Ae3' in temps
        assert 'Bs' in temps
        assert 'Ms' in temps
        assert 'Mf' in temps

    def test_overrides(self, aisi4340_comp):
        temps = calculate_critical_temperatures(aisi4340_comp, overrides={'Ae1': 700})
        assert temps['Ae1'] == 700

    def test_minimal_composition(self):
        comp = {'C': 0.20}
        temps = calculate_critical_temperatures(comp)
        assert temps['Ae1'] > 600
        assert temps['Ms'] > 200

    def test_individual_calc_ae1(self):
        ae1 = calc_ae1(Mn=0.75, Ni=0.0, Si=0.25, Cr=0.0, W=0.0)
        assert 700 < ae1 < 750

    def test_individual_calc_ms(self):
        ms = calc_ms(C=0.40, Mn=0.70, Ni=1.80, Cr=0.80, Mo=0.25, Si=0.25)
        assert 200 < ms < 400


# === JMAK Model ===

class TestJMAKModel:
    def test_fraction_starts_at_zero(self, pearlite_jmak):
        f = pearlite_jmak.fraction_transformed(0.001, 650)
        assert f < 0.01

    def test_fraction_approaches_one(self, pearlite_jmak):
        # b_max=0.001, n=1.5 at T=650 (nose): b=0.001
        # X = 1 - exp(-0.001 * t^1.5)
        # For t=1e6: 0.001 * (1e6)^1.5 = 0.001 * 1e9 = 1e6 >> 1
        f = pearlite_jmak.fraction_transformed(1e6, 650)
        assert f > 0.99

    def test_fraction_monotonically_increasing(self, pearlite_jmak):
        times = [1, 10, 100, 1000, 10000]
        fractions = [pearlite_jmak.fraction_transformed(t, 650) for t in times]
        for i in range(len(fractions) - 1):
            assert fractions[i + 1] >= fractions[i]

    def test_time_to_fraction_inverse(self, pearlite_jmak):
        target = 0.50
        t = pearlite_jmak.time_to_fraction(target, 650)
        if t is not None:
            f = pearlite_jmak.fraction_transformed(t, 650)
            assert abs(f - target) < 0.01

    def test_time_to_fraction_at_nose(self, pearlite_jmak):
        """At the nose temperature, transformation should be fastest."""
        t_nose = pearlite_jmak.time_to_fraction(0.5, 650)
        t_off = pearlite_jmak.time_to_fraction(0.5, 550)
        # Both should return values, nose should be faster
        if t_nose is not None and t_off is not None:
            assert t_nose <= t_off

    def test_outside_temp_range(self, pearlite_jmak):
        # Above range max (727)
        f = pearlite_jmak.fraction_transformed(100, 800)
        assert f == 0.0

    def test_incubation_time(self, pearlite_jmak):
        tau = pearlite_jmak.incubation_time(650, threshold=0.01)
        assert tau is not None
        assert tau > 0

    def test_transformation_rate(self, pearlite_jmak):
        rate = pearlite_jmak.transformation_rate(100, 650)
        assert rate >= 0


class TestBFunctions:
    def test_gaussian_peak_at_nose(self):
        b = gaussian_b_function(b_max=1.0, t_nose=600, sigma=50)
        assert b(600) == pytest.approx(1.0)

    def test_gaussian_decays(self):
        b = gaussian_b_function(b_max=1.0, t_nose=600, sigma=50)
        assert b(500) < b(600)
        assert b(700) < b(600)

    def test_arrhenius_increases_with_temp(self):
        b = arrhenius_b_function(b0=1e10, Q=150000)
        assert b(800 + 273) > b(600 + 273)

    def test_create_b_function_gaussian(self):
        b = create_b_function('gaussian', {'b_max': 1.0, 't_nose': 650, 'sigma': 50})
        assert b(650) == pytest.approx(1.0)

    def test_create_b_function_arrhenius(self):
        b = create_b_function('arrhenius', {'b0': 1e10, 'Q': 150000})
        assert callable(b)


class TestFitJMAK:
    def test_fit_isothermal_data(self):
        """Fit JMAK to synthetic isothermal data."""
        n_true = 2.0
        b_max = 0.001
        t_nose = 650
        sigma = 60

        temperatures = []
        times = []
        fractions = []

        for T in [600, 625, 650, 675, 700]:
            b = b_max * math.exp(-0.5 * ((T - t_nose) / sigma) ** 2)
            for t in [1, 10, 50, 100, 500, 1000]:
                f = 1 - math.exp(-b * t ** n_true)
                f = max(0.001, min(0.999, f))
                temperatures.append(T)
                times.append(t)
                fractions.append(f)

        n, model_type, params = fit_jmak_parameters(
            np.array(temperatures), np.array(times), np.array(fractions),
            model_type='gaussian'
        )
        assert 1.0 < n < 4.0
        assert model_type == 'gaussian'
        assert 'b_max' in params


# === Koistinen-Marburger ===

class TestKoistinenMarburger:
    def test_no_martensite_above_ms(self, km_model):
        f = km_model.fraction_at_temperature(350)
        assert f == 0.0

    def test_full_martensite_well_below_mf(self, km_model):
        f = km_model.fraction_at_temperature(0)
        assert f > 0.95

    def test_fraction_at_mf(self, km_model):
        f = km_model.fraction_at_temperature(120)
        assert 0.80 < f < 1.0

    def test_monotonic_with_undercooling(self, km_model):
        temps = [310, 280, 250, 200, 150, 100, 50]
        fracs = [km_model.fraction_at_temperature(t) for t in temps]
        for i in range(len(fracs) - 1):
            assert fracs[i + 1] >= fracs[i]

    def test_temperature_at_fraction(self, km_model):
        t = km_model.temperature_at_fraction(0.50)
        assert t is not None
        f = km_model.fraction_at_temperature(t)
        assert abs(f - 0.50) < 0.01

    def test_fraction_from_cooling(self, km_model):
        """fraction_from_cooling returns a scalar (final martensite fraction)."""
        temps = np.linspace(400, 0, 200)
        frac = km_model.fraction_from_cooling(temps)
        # Should be a float, not an array
        assert isinstance(frac, float)
        assert frac > 0.95  # Well below Mf

    def test_fraction_from_cooling_above_ms(self, km_model):
        """No martensite if minimum temperature is above Ms."""
        temps = np.linspace(800, 350, 100)
        frac = km_model.fraction_from_cooling(temps)
        assert frac == 0.0

    def test_from_composition(self, aisi4340_comp):
        km = KoistinenMarburgerModel.from_composition(aisi4340_comp)
        assert km.ms > 200
        assert km.alpha > 0


# === Scheil Additivity ===

class TestScheilAdditivity:
    def test_linear_cooling_through_pearlite(self, pearlite_jmak, km_model):
        """Linear cooling from 800 to 200 should produce some transformation."""
        n_steps = 500
        times = np.linspace(0, 2000, n_steps)
        temps = np.linspace(750, 200, n_steps)

        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320, 'Mf': 120}
        jmak_models = {'pearlite': pearlite_jmak}

        result = calculate_cct_transformation(
            times, temps, jmak_models, km_model, critical_temps
        )

        assert result is not None
        final = result.final_fractions
        total = sum(final.values())
        assert 0.99 < total < 1.01

    def test_fast_cooling_mostly_martensite(self, pearlite_jmak, bainite_jmak, km_model):
        """Very fast cooling should produce mostly martensite."""
        n_steps = 200
        times = np.linspace(0, 5, n_steps)
        temps = np.linspace(900, 0, n_steps)

        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320, 'Mf': 120}
        jmak_models = {'pearlite': pearlite_jmak, 'bainite': bainite_jmak}

        result = calculate_cct_transformation(
            times, temps, jmak_models, km_model, critical_temps
        )

        assert result.final_fractions.get('martensite', 0) > 0.5

    def test_slow_cooling_more_diffusional(self, pearlite_jmak, km_model):
        """Very slow cooling should allow diffusional transformation."""
        n_steps = 1000
        times = np.linspace(0, 50000, n_steps)
        temps = np.linspace(800, 200, n_steps)

        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320, 'Mf': 120}
        jmak_models = {'pearlite': pearlite_jmak}

        result = calculate_cct_transformation(
            times, temps, jmak_models, km_model, critical_temps
        )

        # Slow cooling -> significant pearlite
        assert result.final_fractions.get('pearlite', 0) > 0.1


# === TTT Generation ===

class TestTTTGeneration:
    def test_generate_ttt_diagram(self, pearlite_jmak, bainite_jmak):
        jmak_models = {'pearlite': pearlite_jmak, 'bainite': bainite_jmak}
        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320}

        data = generate_ttt_diagram(jmak_models, critical_temps, n_temperatures=20)

        assert 'pearlite' in data
        # Keys are 'start', 'fifty', 'finish'
        assert 'start' in data['pearlite']
        for point in data['pearlite']['start']:
            assert len(point) == 2  # [time, temperature]
            assert point[0] > 0  # time > 0
            assert point[1] > 0  # temperature > 0

    def test_generate_ttt_for_plotting(self, pearlite_jmak):
        jmak_models = {'pearlite': pearlite_jmak}
        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320}

        curves = generate_ttt_for_plotting(jmak_models, critical_temps)
        assert 'pearlite' in curves
        assert 'start' in curves['pearlite']
        assert 'finish' in curves['pearlite']
        assert len(curves['pearlite']['start']) > 0


# === CCT Generation ===

class TestCCTGeneration:
    def test_generate_cct_from_ttt(self, pearlite_jmak, bainite_jmak, km_model):
        jmak_models = {'pearlite': pearlite_jmak, 'bainite': bainite_jmak}
        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320, 'Mf': 120}

        curves = generate_cct_from_ttt(
            jmak_models, km_model, critical_temps,
            cooling_rates=[0.1, 1, 10, 100]
        )

        assert len(curves) > 0
        for phase, phase_curves in curves.items():
            if isinstance(phase_curves, dict):
                assert 'start' in phase_curves or 'finish' in phase_curves

    def test_generate_cct_phase_fractions(self, pearlite_jmak, km_model):
        jmak_models = {'pearlite': pearlite_jmak}
        critical_temps = {'Ae1': 727, 'Ae3': 840, 'Bs': 550, 'Ms': 320, 'Mf': 120}

        # Returns {cooling_rate: {phase: fraction}}
        fractions = generate_cct_phase_fractions(
            jmak_models, km_model, critical_temps,
            cooling_rates=[0.1, 1, 10, 100]
        )

        assert len(fractions) == 4
        for cr, phase_dict in fractions.items():
            assert isinstance(cr, float)
            assert isinstance(phase_dict, dict)
            total = sum(phase_dict.values())
            assert 0.95 < total < 1.05


# === Parameter Calibration ===

class TestParameterCalibration:
    def test_extract_jmak_from_isothermal(self):
        from app.services.phase_transformation.parameter_calibration import (
            extract_jmak_from_isothermal_curve
        )

        n_true = 2.0
        b_true = 0.001
        times = np.array([1, 5, 10, 50, 100, 500, 1000], dtype=float)
        fractions = 1 - np.exp(-b_true * times ** n_true)

        n, b = extract_jmak_from_isothermal_curve(times, fractions, temperature=650)
        assert 1.5 < n < 2.5
        assert b > 0
