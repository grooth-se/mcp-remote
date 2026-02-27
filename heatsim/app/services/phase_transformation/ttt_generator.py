"""TTT diagram generator from JMAK parameters.

Generates isothermal TTT (Time-Temperature-Transformation) diagram data
at 1% (start), 50%, and 99% (finish) transformation contours.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple

from .jmak_model import JMAKModel


def generate_ttt_diagram(
    jmak_models: Dict[str, JMAKModel],
    critical_temps: Dict[str, float],
    n_temperatures: int = 50,
    fractions: Optional[List[float]] = None
) -> Dict[str, Dict[str, List[List[float]]]]:
    """Generate TTT diagram data from JMAK models.

    For each phase, computes time-temperature curves at specified
    fraction levels (default: 1% start, 50%, 99% finish).

    Parameters
    ----------
    jmak_models : dict
        Phase name -> JMAKModel
    critical_temps : dict
        {'Ae1', 'Ae3', 'Bs', 'Ms'} temperatures
    n_temperatures : int
        Number of temperature points per curve
    fractions : list of float, optional
        Fraction levels to compute (default [0.01, 0.50, 0.99])

    Returns
    -------
    dict
        Nested dict: {phase: {fraction_label: [[time, temp], ...]}}
        fraction_label is 'start' (1%), 'fifty' (50%), 'finish' (99%)
    """
    if fractions is None:
        fractions = [0.01, 0.50, 0.99]

    fraction_labels = {0.01: 'start', 0.50: 'fifty', 0.99: 'finish'}
    ae3 = critical_temps.get('Ae3', 900)
    ae1 = critical_temps.get('Ae1', 727)
    bs = critical_temps.get('Bs', 550)
    ms = critical_temps.get('Ms', 350)

    # Temperature ranges per phase
    phase_ranges = {
        'ferrite': (bs + 20, ae1 - 5),
        'pearlite': (bs, ae1 - 5),
        'bainite': (ms + 10, bs - 5),
    }

    result = {}

    for phase, model in jmak_models.items():
        if phase not in phase_ranges:
            continue

        t_min, t_max = phase_ranges[phase]
        if t_max <= t_min:
            continue

        temperatures = np.linspace(t_max, t_min, n_temperatures)
        phase_curves = {}

        for frac in fractions:
            label = fraction_labels.get(frac, f'f{frac:.2f}')
            points = []

            for T in temperatures:
                time = model.time_to_fraction(frac, float(T))
                if time is not None and time > 0 and time < 1e8:
                    points.append([float(time), float(T)])

            if points:
                phase_curves[label] = points

        if phase_curves:
            result[phase] = phase_curves

    return result


def generate_ttt_for_plotting(
    jmak_models: Dict[str, JMAKModel],
    critical_temps: Dict[str, float],
    n_temperatures: int = 50
) -> Dict[str, Dict[str, List[List[float]]]]:
    """Generate TTT diagram data in format compatible with visualization.

    Returns start (1%) and finish (99%) curves per phase, matching the
    format used by create_ttt_overlay_plot().

    Parameters
    ----------
    jmak_models : dict
        Phase name -> JMAKModel
    critical_temps : dict
        Critical temperatures
    n_temperatures : int
        Number of temperature points

    Returns
    -------
    dict
        {phase: {'start': [[t,T],...], 'finish': [[t,T],...]}}
    """
    full_data = generate_ttt_diagram(
        jmak_models, critical_temps, n_temperatures,
        fractions=[0.01, 0.99]
    )

    # Convert to start/finish format
    result = {}
    for phase, curves in full_data.items():
        phase_dict = {}
        if 'start' in curves:
            phase_dict['start'] = curves['start']
        if 'finish' in curves:
            phase_dict['finish'] = curves['finish']
        if phase_dict:
            result[phase] = phase_dict

    return result
