"""CCT diagram generator from TTT data via Scheil additivity.

Runs the Scheil additivity calculation at multiple cooling rates to
generate CCT (Continuous Cooling Transformation) diagram data.

Output format matches that of cct_predictor.predict():
    {phase: {'start': [[t,T],...], 'finish': [[t,T],...]}}
"""
import numpy as np
from typing import Dict, List, Optional

from .jmak_model import JMAKModel
from .martensite_model import KoistinenMarburgerModel
from .scheil_additivity import calculate_cct_transformation


def generate_cct_from_ttt(
    jmak_models: Dict[str, JMAKModel],
    martensite_model: Optional[KoistinenMarburgerModel] = None,
    critical_temps: Optional[Dict[str, float]] = None,
    cooling_rates: Optional[List[float]] = None,
    austenitizing_temp: float = 900.0,
    end_temp: float = 25.0,
    start_fraction: float = 0.01,
    finish_fraction: float = 0.99
) -> Dict[str, Dict[str, List[List[float]]]]:
    """Generate CCT curves by running Scheil at multiple cooling rates.

    For each cooling rate, simulates a linear cooling curve from
    austenitizing temperature to end temperature, applies Scheil
    additivity, and records the time/temperature at which each phase
    starts (1%) and finishes (99%).

    Parameters
    ----------
    jmak_models : dict
        Phase name -> JMAKModel
    martensite_model : KoistinenMarburgerModel, optional
        Martensite model
    critical_temps : dict, optional
        Critical temperatures
    cooling_rates : list of float, optional
        Cooling rates to simulate (K/s). Default: logarithmic from 0.1 to 200
    austenitizing_temp : float
        Starting temperature (deg C)
    end_temp : float
        Final temperature (deg C)
    start_fraction : float
        Fraction threshold for "start" curve (default 0.01)
    finish_fraction : float
        Fraction threshold for "finish" curve (default 0.99)

    Returns
    -------
    dict
        {phase: {'start': [[time,temp],...], 'finish': [[time,temp],...]}}
        Same format as CCTCurvePredictor.predict()
    """
    if critical_temps is None:
        critical_temps = {}

    if cooling_rates is None:
        # Logarithmic distribution of cooling rates
        cooling_rates = np.logspace(-1, 2.3, 30).tolist()  # 0.1 to ~200 K/s

    curves = {}
    phase_starts = {}   # phase -> list of (time, temp)
    phase_finishes = {}  # phase -> list of (time, temp)

    for cr in sorted(cooling_rates):
        # Generate linear cooling curve
        delta_T = austenitizing_temp - end_temp
        total_time = delta_T / cr
        n_steps = max(int(total_time * 10), 500)  # At least 0.1s resolution
        n_steps = min(n_steps, 5000)  # Cap for performance

        times = np.linspace(0, total_time, n_steps)
        temperatures = austenitizing_temp - cr * times

        # Run Scheil additivity
        result = calculate_cct_transformation(
            times, temperatures,
            jmak_models, martensite_model, critical_temps
        )

        # Extract start/finish points for each phase
        for phase in result.phase_fractions:
            if phase == 'retained_austenite':
                continue

            frac = result.phase_fractions[phase]
            final_frac = frac[-1]

            if final_frac < 0.005:
                continue

            # Start point
            start_threshold = start_fraction * final_frac
            start_indices = np.where(frac >= start_threshold)[0]
            if len(start_indices) > 0:
                idx = start_indices[0]
                if phase not in phase_starts:
                    phase_starts[phase] = []
                phase_starts[phase].append([float(times[idx]), float(temperatures[idx])])

            # Finish point
            finish_threshold = finish_fraction * final_frac
            finish_indices = np.where(frac >= finish_threshold)[0]
            if len(finish_indices) > 0:
                idx = finish_indices[0]
                if phase not in phase_finishes:
                    phase_finishes[phase] = []
                phase_finishes[phase].append([float(times[idx]), float(temperatures[idx])])

    # Build output in standard format
    for phase in set(list(phase_starts.keys()) + list(phase_finishes.keys())):
        phase_dict = {}
        if phase in phase_starts and len(phase_starts[phase]) >= 2:
            # Sort by temperature descending
            start_pts = sorted(phase_starts[phase], key=lambda p: -p[1])
            phase_dict['start'] = start_pts
        if phase in phase_finishes and len(phase_finishes[phase]) >= 2:
            finish_pts = sorted(phase_finishes[phase], key=lambda p: -p[1])
            phase_dict['finish'] = finish_pts

        if phase_dict:
            curves[phase] = phase_dict

    return curves


def generate_cct_phase_fractions(
    jmak_models: Dict[str, JMAKModel],
    martensite_model: Optional[KoistinenMarburgerModel] = None,
    critical_temps: Optional[Dict[str, float]] = None,
    cooling_rates: Optional[List[float]] = None,
    austenitizing_temp: float = 900.0,
    end_temp: float = 25.0
) -> Dict[float, Dict[str, float]]:
    """Generate final phase fractions at each cooling rate.

    Useful for plotting phase fraction vs cooling rate diagrams.

    Parameters
    ----------
    jmak_models : dict
        Phase name -> JMAKModel
    martensite_model : KoistinenMarburgerModel, optional
    critical_temps : dict, optional
    cooling_rates : list of float, optional
    austenitizing_temp : float
    end_temp : float

    Returns
    -------
    dict
        {cooling_rate: {phase: fraction, ...}, ...}
    """
    if cooling_rates is None:
        cooling_rates = np.logspace(-1, 2.3, 20).tolist()

    results = {}

    for cr in sorted(cooling_rates):
        delta_T = austenitizing_temp - end_temp
        total_time = delta_T / cr
        n_steps = max(int(total_time * 5), 200)
        n_steps = min(n_steps, 3000)

        times = np.linspace(0, total_time, n_steps)
        temperatures = austenitizing_temp - cr * times

        result = calculate_cct_transformation(
            times, temperatures,
            jmak_models, martensite_model, critical_temps
        )

        results[float(cr)] = result.final_fractions

    return results
