"""Johnson-Mehl-Avrami-Kolmogorov (JMAK) kinetics model.

Implements the JMAK equation for isothermal phase transformations:
    X(t) = 1 - exp(-b(T) * t^n)

where X is the fraction transformed, n is the Avrami exponent, and
b(T) is the temperature-dependent rate parameter.

b(T) model options:
    - Gaussian: b = b_max * exp(-0.5 * ((T - T_nose) / sigma)^2)
    - Arrhenius: b = b0 * exp(-Q / (R * T_K))
    - Polynomial: b = sum(a_i * T^i)
"""
import math
from typing import Callable, Optional, Dict, List, Tuple

import numpy as np
from scipy.optimize import curve_fit


def gaussian_b_function(b_max: float, t_nose: float, sigma: float) -> Callable:
    """Create a Gaussian b(T) function.

    b(T) = b_max * exp(-0.5 * ((T - T_nose) / sigma)^2)

    This gives a C-curve shape: maximum rate at the nose temperature,
    decreasing symmetrically above and below.

    Parameters
    ----------
    b_max : float
        Maximum b value at the nose temperature
    t_nose : float
        Nose temperature (deg C) where transformation is fastest
    sigma : float
        Width parameter (deg C) controlling the spread

    Returns
    -------
    callable
        Function b(T) -> float
    """
    def b_func(T):
        return b_max * math.exp(-0.5 * ((T - t_nose) / sigma) ** 2)
    return b_func


def arrhenius_b_function(b0: float, Q: float) -> Callable:
    """Create an Arrhenius b(T) function.

    b(T) = b0 * exp(-Q / (R * T_K))

    Parameters
    ----------
    b0 : float
        Pre-exponential factor
    Q : float
        Activation energy (J/mol)

    Returns
    -------
    callable
        Function b(T_celsius) -> float
    """
    R = 8.314  # J/(mol*K)

    def b_func(T):
        T_K = T + 273.15
        if T_K <= 0:
            return 0.0
        return b0 * math.exp(-Q / (R * T_K))
    return b_func


def polynomial_b_function(coefficients: List[float]) -> Callable:
    """Create a polynomial b(T) function.

    b(T) = a0 + a1*T + a2*T^2 + ...

    Parameters
    ----------
    coefficients : list of float
        Polynomial coefficients [a0, a1, a2, ...]

    Returns
    -------
    callable
        Function b(T) -> float
    """
    def b_func(T):
        val = sum(c * T**i for i, c in enumerate(coefficients))
        return max(val, 0.0)  # b must be non-negative
    return b_func


def create_b_function(model_type: str, parameters: dict) -> Callable:
    """Factory to create b(T) function from model type and parameters.

    Parameters
    ----------
    model_type : str
        'gaussian', 'arrhenius', or 'polynomial'
    parameters : dict
        Model-specific parameters

    Returns
    -------
    callable
        Function b(T) -> float
    """
    if model_type == 'gaussian':
        return gaussian_b_function(
            b_max=parameters['b_max'],
            t_nose=parameters['t_nose'],
            sigma=parameters['sigma']
        )
    elif model_type == 'arrhenius':
        return arrhenius_b_function(
            b0=parameters['b0'],
            Q=parameters['Q']
        )
    elif model_type == 'polynomial':
        return polynomial_b_function(parameters['coefficients'])
    else:
        raise ValueError(f"Unknown b-function model type: {model_type}")


class JMAKModel:
    """JMAK kinetics model for a single diffusional phase transformation.

    Implements X(t, T) = 1 - exp(-b(T) * t^n) for isothermal holds
    and provides time-to-fraction and rate calculations.

    Parameters
    ----------
    n : float
        Avrami exponent
    b_func : callable
        Temperature-dependent rate function b(T_celsius) -> float
    temp_range : tuple of float, optional
        (T_min, T_max) in deg C where this model is valid
    """

    def __init__(self, n: float, b_func: Callable,
                 temp_range: Optional[Tuple[float, float]] = None):
        self.n = n
        self.b_func = b_func
        self.temp_range = temp_range

    def fraction_transformed(self, time: float, temperature: float) -> float:
        """Calculate fraction transformed at given time and temperature.

        X(t, T) = 1 - exp(-b(T) * t^n)

        Parameters
        ----------
        time : float
            Time in seconds (must be >= 0)
        temperature : float
            Temperature in deg C

        Returns
        -------
        float
            Fraction transformed (0 to 1)
        """
        if time <= 0:
            return 0.0
        if self.temp_range:
            if temperature < self.temp_range[0] or temperature > self.temp_range[1]:
                return 0.0

        b = self.b_func(temperature)
        if b <= 0:
            return 0.0

        exponent = b * (time ** self.n)
        # Clamp to avoid overflow
        exponent = min(exponent, 700)
        return 1.0 - math.exp(-exponent)

    def time_to_fraction(self, fraction: float, temperature: float) -> Optional[float]:
        """Calculate time required to reach a given fraction at temperature.

        t = (ln(1/(1-X)) / b(T))^(1/n)

        Parameters
        ----------
        fraction : float
            Target fraction transformed (0 < X < 1)
        temperature : float
            Temperature in deg C

        Returns
        -------
        float or None
            Time in seconds, or None if transformation cannot occur
        """
        if fraction <= 0 or fraction >= 1:
            return None
        if self.temp_range:
            if temperature < self.temp_range[0] or temperature > self.temp_range[1]:
                return None

        b = self.b_func(temperature)
        if b <= 0:
            return None

        log_term = math.log(1.0 / (1.0 - fraction))
        time = (log_term / b) ** (1.0 / self.n)
        return time

    def transformation_rate(self, time: float, temperature: float) -> float:
        """Calculate instantaneous transformation rate dX/dt.

        dX/dt = n * b(T) * t^(n-1) * exp(-b(T) * t^n)

        Parameters
        ----------
        time : float
            Time in seconds
        temperature : float
            Temperature in deg C

        Returns
        -------
        float
            Rate of transformation (1/s)
        """
        if time <= 0:
            return 0.0
        if self.temp_range:
            if temperature < self.temp_range[0] or temperature > self.temp_range[1]:
                return 0.0

        b = self.b_func(temperature)
        if b <= 0:
            return 0.0

        bt_n = b * (time ** self.n)
        bt_n = min(bt_n, 700)
        return self.n * b * (time ** (self.n - 1)) * math.exp(-bt_n)

    def incubation_time(self, temperature: float, threshold: float = 0.01) -> Optional[float]:
        """Calculate incubation time (time to threshold fraction).

        Parameters
        ----------
        temperature : float
            Temperature in deg C
        threshold : float
            Fraction to consider as "start" of transformation (default 1%)

        Returns
        -------
        float or None
            Incubation time in seconds
        """
        return self.time_to_fraction(threshold, temperature)


def fit_jmak_parameters(temperatures: np.ndarray,
                         times: np.ndarray,
                         fractions: np.ndarray,
                         model_type: str = 'gaussian'
                         ) -> Tuple[float, str, dict]:
    """Fit JMAK parameters from experimental isothermal data.

    Expects data from multiple isothermal hold experiments at different
    temperatures.

    Parameters
    ----------
    temperatures : np.ndarray
        Hold temperatures (deg C), one per experiment
    times : np.ndarray
        Time values (seconds), same length
    fractions : np.ndarray
        Measured fraction transformed (0-1), same length

    model_type : str
        Type of b(T) model to fit: 'gaussian' or 'arrhenius'

    Returns
    -------
    tuple of (n, model_type, b_parameters)
        n : float - fitted Avrami exponent
        model_type : str - b-function model type
        b_parameters : dict - fitted b-function parameters
    """
    # Step 1: Linearize JMAK for each temperature to get n and b
    # ln(-ln(1-X)) = n*ln(t) + ln(b)
    unique_temps = np.unique(temperatures)
    n_values = []
    b_values = []
    temp_for_b = []

    for T in unique_temps:
        mask = (temperatures == T) & (fractions > 0.001) & (fractions < 0.999)
        t_data = times[mask]
        f_data = fractions[mask]

        if len(t_data) < 2:
            continue

        # Linearize
        y = np.log(-np.log(1 - f_data))
        x = np.log(t_data)

        # Linear regression: y = n*x + ln(b)
        coeffs = np.polyfit(x, y, 1)
        n_val = coeffs[0]
        b_val = math.exp(coeffs[1])

        if n_val > 0 and b_val > 0:
            n_values.append(n_val)
            b_values.append(b_val)
            temp_for_b.append(T)

    if not n_values:
        raise ValueError("Insufficient data for JMAK fitting")

    # Average n across temperatures (should be approximately constant)
    n_avg = float(np.mean(n_values))

    # Step 2: Fit b(T) model
    temp_arr = np.array(temp_for_b)
    b_arr = np.array(b_values)

    if model_type == 'gaussian':
        b_params = _fit_gaussian_b(temp_arr, b_arr)
    elif model_type == 'arrhenius':
        b_params = _fit_arrhenius_b(temp_arr, b_arr)
    else:
        raise ValueError(f"Unsupported model type for fitting: {model_type}")

    return n_avg, model_type, b_params


def _fit_gaussian_b(temperatures: np.ndarray, b_values: np.ndarray) -> dict:
    """Fit Gaussian b(T) model to temperature-b value pairs."""
    # Initial guesses
    idx_max = np.argmax(b_values)
    b_max_init = b_values[idx_max]
    t_nose_init = temperatures[idx_max]
    sigma_init = (temperatures.max() - temperatures.min()) / 4

    def gaussian(T, b_max, t_nose, sigma):
        return b_max * np.exp(-0.5 * ((T - t_nose) / sigma) ** 2)

    try:
        popt, _ = curve_fit(
            gaussian, temperatures, b_values,
            p0=[b_max_init, t_nose_init, sigma_init],
            bounds=([0, temperatures.min() - 100, 10],
                    [np.inf, temperatures.max() + 100, 500]),
            maxfev=10000
        )
        return {
            'b_max': float(popt[0]),
            't_nose': float(popt[1]),
            'sigma': float(popt[2]),
        }
    except (RuntimeError, ValueError):
        # Fallback: use raw values
        return {
            'b_max': float(b_max_init),
            't_nose': float(t_nose_init),
            'sigma': float(sigma_init),
        }


def _fit_arrhenius_b(temperatures: np.ndarray, b_values: np.ndarray) -> dict:
    """Fit Arrhenius b(T) model to temperature-b value pairs."""
    R = 8.314
    T_K = temperatures + 273.15

    # Linearize: ln(b) = ln(b0) - Q/(R*T)
    ln_b = np.log(b_values[b_values > 0])
    inv_T = 1.0 / T_K[b_values > 0]

    if len(ln_b) < 2:
        return {'b0': 1.0, 'Q': 100000.0}

    coeffs = np.polyfit(inv_T, ln_b, 1)
    Q = -coeffs[0] * R
    b0 = math.exp(coeffs[1])

    return {
        'b0': float(b0),
        'Q': float(Q),
    }
