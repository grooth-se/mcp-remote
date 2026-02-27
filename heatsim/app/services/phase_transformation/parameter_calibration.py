"""Parameter calibration from experimental dilatometry data.

Fits JMAK parameters (n, b(T)) from isothermal and continuous cooling
test data. Supports:
- Isothermal dilatometry (fraction vs time at constant temperature)
- CCT dilatometry (fraction vs temperature at constant cooling rate)
"""
import math
from typing import Dict, List, Tuple, Optional

import numpy as np
from scipy.optimize import curve_fit, minimize

from .jmak_model import JMAKModel, fit_jmak_parameters, create_b_function


def calibrate_isothermal(
    data_points: List[Dict],
    phase: str
) -> Tuple[float, str, dict]:
    """Calibrate JMAK parameters from isothermal dilatometry data.

    Each data point has: temperature, time, fraction_transformed.
    Groups by temperature, linearizes JMAK to get n and b(T), then
    fits a Gaussian b-function.

    Parameters
    ----------
    data_points : list of dict
        Each dict has keys: 'temperature', 'time', 'fraction_transformed'
    phase : str
        Phase name ('ferrite', 'pearlite', 'bainite')

    Returns
    -------
    tuple of (n_value, b_model_type, b_parameters)
    """
    if len(data_points) < 3:
        raise ValueError("Need at least 3 data points for calibration")

    temperatures = np.array([d['temperature'] for d in data_points])
    times = np.array([d['time'] for d in data_points])
    fractions = np.array([d['fraction_transformed'] for d in data_points])

    n_value, model_type, b_params = fit_jmak_parameters(
        temperatures, times, fractions, model_type='gaussian'
    )

    return n_value, model_type, b_params


def calibrate_b_function(
    temperature_b_pairs: List[Tuple[float, float]],
    model_type: str = 'gaussian'
) -> dict:
    """Fit b(T) function from temperature-b value pairs.

    Used when n is known/fixed and b values have been extracted
    from individual isothermal experiments.

    Parameters
    ----------
    temperature_b_pairs : list of (temperature, b_value)
    model_type : str
        'gaussian' or 'arrhenius'

    Returns
    -------
    dict
        Fitted parameters for the b-function model
    """
    temps = np.array([p[0] for p in temperature_b_pairs])
    b_vals = np.array([p[1] for p in temperature_b_pairs])

    if model_type == 'gaussian':
        idx_max = np.argmax(b_vals)
        b_max_init = b_vals[idx_max]
        t_nose_init = temps[idx_max]
        sigma_init = (temps.max() - temps.min()) / 4

        def gaussian(T, b_max, t_nose, sigma):
            return b_max * np.exp(-0.5 * ((T - t_nose) / sigma) ** 2)

        try:
            popt, _ = curve_fit(
                gaussian, temps, b_vals,
                p0=[b_max_init, t_nose_init, sigma_init],
                bounds=([0, temps.min() - 100, 10],
                        [np.inf, temps.max() + 100, 500])
            )
            return {'b_max': float(popt[0]), 't_nose': float(popt[1]), 'sigma': float(popt[2])}
        except RuntimeError:
            return {'b_max': float(b_max_init), 't_nose': float(t_nose_init), 'sigma': float(sigma_init)}

    elif model_type == 'arrhenius':
        R = 8.314
        T_K = temps + 273.15
        valid = b_vals > 0
        ln_b = np.log(b_vals[valid])
        inv_T = 1.0 / T_K[valid]
        coeffs = np.polyfit(inv_T, ln_b, 1)
        return {'b0': float(math.exp(coeffs[1])), 'Q': float(-coeffs[0] * R)}

    raise ValueError(f"Unknown model type: {model_type}")


def calibrate_from_cct(
    cct_data_points: List[Dict],
    n_initial: float = 2.0,
    model_type: str = 'gaussian'
) -> Tuple[float, str, dict]:
    """Calibrate JMAK parameters from CCT dilatometry data.

    Uses an optimization approach: for each candidate (n, b_params),
    runs Scheil additivity at the experimental cooling rates and
    minimizes the error in predicted vs measured start/finish temperatures.

    Parameters
    ----------
    cct_data_points : list of dict
        Each dict has: 'cooling_rate', 'start_temperature', 'finish_temperature'
        for the phase being calibrated.
    n_initial : float
        Initial guess for Avrami exponent
    model_type : str
        'gaussian' b-function model

    Returns
    -------
    tuple of (n_value, model_type, b_parameters)
    """
    if len(cct_data_points) < 3:
        raise ValueError("Need at least 3 CCT data points")

    cooling_rates = np.array([d['cooling_rate'] for d in cct_data_points])
    start_temps = np.array([d['start_temperature'] for d in cct_data_points])
    finish_temps = np.array([d.get('finish_temperature', d['start_temperature'] - 50)
                             for d in cct_data_points])

    # Initial estimates from CCT data
    # Nose temperature: temperature where start occurs at shortest time
    min_cr_idx = np.argmin(cooling_rates)
    t_nose_init = float(np.mean(start_temps))
    sigma_init = float(np.std(start_temps)) if np.std(start_temps) > 10 else 50.0

    # Estimate b_max from the fastest transformation (lowest cooling rate where transformation occurs)
    # At nose: t_start ~ (ln(100)/b_max)^(1/n) => b_max ~ ln(100) / t_start^n
    # t_start for slowest CR that still shows transformation
    t_start_est = (900 - start_temps[min_cr_idx]) / cooling_rates[min_cr_idx]
    b_max_init = max(math.log(100) / max(t_start_est ** n_initial, 0.01), 1e-10)

    def objective(params):
        n, b_max, t_nose, sigma = params
        if n <= 0 or b_max <= 0 or sigma <= 0:
            return 1e10

        b_func = lambda T: b_max * math.exp(-0.5 * ((T - t_nose) / sigma) ** 2)
        model = JMAKModel(n=n, b_func=b_func)

        error = 0.0
        for i, cr in enumerate(cooling_rates):
            # Simulate cooling
            delta_T = 900 - 25
            total_time = delta_T / cr
            n_steps = 500
            times = np.linspace(0, total_time, n_steps)
            temperatures = 900 - cr * times

            # Find predicted start temperature (1% fraction)
            for j in range(1, n_steps):
                frac = model.fraction_transformed(times[j], temperatures[j])
                if frac >= 0.01:
                    pred_start = temperatures[j]
                    error += (pred_start - start_temps[i]) ** 2
                    break

        return error

    from scipy.optimize import differential_evolution
    bounds = [
        (0.5, 4.0),       # n
        (1e-15, 1e5),     # b_max
        (200, 800),        # t_nose
        (20, 300),         # sigma
    ]

    try:
        result = differential_evolution(objective, bounds, maxiter=200, tol=0.01,
                                         seed=42, polish=True)
        n_opt, b_max_opt, t_nose_opt, sigma_opt = result.x
        return float(n_opt), model_type, {
            'b_max': float(b_max_opt),
            't_nose': float(t_nose_opt),
            'sigma': float(sigma_opt),
        }
    except Exception:
        # Return initial estimates
        return n_initial, model_type, {
            'b_max': float(b_max_init),
            't_nose': float(t_nose_init),
            'sigma': float(sigma_init),
        }


def extract_jmak_from_isothermal_curve(
    times: np.ndarray,
    fractions: np.ndarray,
    temperature: float
) -> Tuple[float, float]:
    """Extract n and b from a single isothermal transformation curve.

    Linearizes: ln(-ln(1-X)) = n*ln(t) + ln(b)

    Parameters
    ----------
    times : np.ndarray
        Time values (seconds)
    fractions : np.ndarray
        Fraction transformed (0-1)
    temperature : float
        Hold temperature (deg C)

    Returns
    -------
    tuple of (n, b)
        Avrami exponent and rate parameter at this temperature
    """
    # Filter valid range
    mask = (fractions > 0.01) & (fractions < 0.99) & (times > 0)
    if mask.sum() < 2:
        raise ValueError("Insufficient valid data points")

    y = np.log(-np.log(1 - fractions[mask]))
    x = np.log(times[mask])

    coeffs = np.polyfit(x, y, 1)
    n = float(coeffs[0])
    b = float(math.exp(coeffs[1]))

    return n, b
