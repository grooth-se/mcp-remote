"""Scheil additivity rule for continuous cooling transformations.

The Scheil (or isokinetic) additivity rule converts isothermal TTT data
to continuous cooling predictions. The transformation starts when:

    integral(dt / tau(T)) >= 1

where tau(T) is the isothermal incubation time at temperature T.

For phase fraction tracking during continuous cooling, we integrate
the JMAK rate at each temperature step using a virtual-time approach.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .jmak_model import JMAKModel
from .martensite_model import KoistinenMarburgerModel


@dataclass
class CoolingTransformationResult:
    """Result of Scheil additivity calculation along a cooling curve.

    Attributes
    ----------
    times : np.ndarray
        Time array (seconds)
    temperatures : np.ndarray
        Temperature array (deg C)
    phase_fractions : dict of str -> np.ndarray
        Time-resolved fraction for each phase
    final_fractions : dict of str -> float
        Final phase fractions at end of cooling
    transformation_start : dict of str -> tuple
        (time, temperature) where each phase starts transforming (1%)
    transformation_finish : dict of str -> tuple
        (time, temperature) where each phase finishes (99%)
    """
    times: np.ndarray = field(default_factory=lambda: np.array([]))
    temperatures: np.ndarray = field(default_factory=lambda: np.array([]))
    phase_fractions: Dict[str, np.ndarray] = field(default_factory=dict)
    final_fractions: Dict[str, float] = field(default_factory=dict)
    transformation_start: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    transformation_finish: Dict[str, Tuple[float, float]] = field(default_factory=dict)


def calculate_cct_transformation(
    times: np.ndarray,
    temperatures: np.ndarray,
    jmak_models: Dict[str, JMAKModel],
    martensite_model: Optional[KoistinenMarburgerModel] = None,
    critical_temps: Optional[Dict[str, float]] = None
) -> CoolingTransformationResult:
    """Calculate phase transformations along a continuous cooling curve.

    Uses Scheil additivity with virtual time to integrate JMAK kinetics
    at each time step. Diffusional phases (ferrite, pearlite, bainite)
    consume austenite, and remaining austenite transforms to martensite
    below Ms via Koistinen-Marburger.

    Parameters
    ----------
    times : np.ndarray
        Time array (seconds), monotonically increasing
    temperatures : np.ndarray
        Temperature array (deg C), generally decreasing (cooling)
    jmak_models : dict
        Phase name -> JMAKModel for each diffusional phase
    martensite_model : KoistinenMarburgerModel, optional
        Martensite transformation model
    critical_temps : dict, optional
        Critical temperatures {'Ae1', 'Ae3', 'Bs', 'Ms'}

    Returns
    -------
    CoolingTransformationResult
    """
    n_steps = len(times)
    result = CoolingTransformationResult(
        times=times,
        temperatures=temperatures,
    )

    ct = critical_temps or {}
    ae3 = ct.get('Ae3', 900)
    ae1 = ct.get('Ae1', 727)
    bs = ct.get('Bs', 550)
    ms = ct.get('Ms', 350)

    # Phase ordering: transformations occur in sequence as temperature drops
    # ferrite (below Ae3), pearlite (below Ae1), bainite (below Bs),
    # martensite (below Ms, athermal)
    diffusional_phases = []
    phase_temp_limits = {}

    if 'ferrite' in jmak_models:
        diffusional_phases.append('ferrite')
        phase_temp_limits['ferrite'] = (bs + 20, ae3)
    if 'pearlite' in jmak_models:
        diffusional_phases.append('pearlite')
        phase_temp_limits['pearlite'] = (bs, ae1)
    if 'bainite' in jmak_models:
        diffusional_phases.append('bainite')
        phase_temp_limits['bainite'] = (ms, bs)

    # Initialize fraction arrays
    for phase in diffusional_phases:
        result.phase_fractions[phase] = np.zeros(n_steps)
    result.phase_fractions['martensite'] = np.zeros(n_steps)
    result.phase_fractions['retained_austenite'] = np.ones(n_steps)

    # Track cumulative diffusional fraction
    total_diffusional = np.zeros(n_steps)

    # Virtual time for each phase (for Scheil additivity)
    virtual_times = {phase: 0.0 for phase in diffusional_phases}

    for i in range(1, n_steps):
        dt = times[i] - times[i - 1]
        T = temperatures[i]

        # Track austenite consumed by diffusional transformations
        austenite_available = 1.0 - total_diffusional[i - 1]

        for phase in diffusional_phases:
            if austenite_available <= 0.001:
                result.phase_fractions[phase][i] = result.phase_fractions[phase][i - 1]
                continue

            t_min, t_max = phase_temp_limits[phase]
            model = jmak_models[phase]

            if T < t_min or T > t_max:
                # Outside transformation range - reset virtual time
                virtual_times[phase] = 0.0
                result.phase_fractions[phase][i] = result.phase_fractions[phase][i - 1]
                continue

            # Scheil virtual-time approach:
            # 1. Find virtual time that gives current fraction at new temperature
            current_frac = result.phase_fractions[phase][i - 1] / max(austenite_available, 0.001)
            current_frac = min(max(current_frac, 0.0), 0.999)

            if current_frac > 0.001:
                vt = model.time_to_fraction(current_frac, T)
                if vt is not None:
                    virtual_times[phase] = vt
            # else: keep previous virtual time

            # 2. Advance virtual time by dt
            virtual_times[phase] += dt

            # 3. Calculate new fraction at this temperature with advanced time
            new_frac = model.fraction_transformed(virtual_times[phase], T)
            new_frac_abs = new_frac * austenite_available

            # Ensure monotonically increasing
            new_frac_abs = max(new_frac_abs, result.phase_fractions[phase][i - 1])
            result.phase_fractions[phase][i] = min(new_frac_abs, austenite_available)

        # Update total diffusional fraction
        total_diffusional[i] = sum(
            result.phase_fractions[p][i] for p in diffusional_phases
        )
        total_diffusional[i] = min(total_diffusional[i], 1.0)

        # Martensite (athermal - depends only on temperature, not time)
        austenite_for_martensite = 1.0 - total_diffusional[i]
        if martensite_model and T < ms and austenite_for_martensite > 0.001:
            f_m = martensite_model.fraction_at_temperature(T)
            result.phase_fractions['martensite'][i] = f_m * austenite_for_martensite
        else:
            result.phase_fractions['martensite'][i] = result.phase_fractions['martensite'][max(0, i - 1)]

        # Retained austenite
        total_all = total_diffusional[i] + result.phase_fractions['martensite'][i]
        result.phase_fractions['retained_austenite'][i] = max(1.0 - total_all, 0.0)

    # Extract final fractions
    for phase in list(result.phase_fractions.keys()):
        result.final_fractions[phase] = float(result.phase_fractions[phase][-1])

    # Find transformation start/finish points
    for phase in diffusional_phases + ['martensite']:
        frac = result.phase_fractions[phase]
        max_frac = frac[-1]
        if max_frac < 0.001:
            continue

        # Start: first point where fraction > 1% of final
        threshold_start = 0.01 * max_frac
        start_idx = np.argmax(frac > threshold_start)
        if frac[start_idx] > threshold_start:
            result.transformation_start[phase] = (
                float(times[start_idx]), float(temperatures[start_idx])
            )

        # Finish: first point where fraction > 99% of final
        threshold_finish = 0.99 * max_frac
        finish_idx = np.argmax(frac > threshold_finish)
        if frac[finish_idx] > threshold_finish:
            result.transformation_finish[phase] = (
                float(times[finish_idx]), float(temperatures[finish_idx])
            )

    return result


def calculate_scheil_integral(
    times: np.ndarray,
    temperatures: np.ndarray,
    jmak_model: JMAKModel,
    fraction_threshold: float = 0.01
) -> Optional[Tuple[float, float]]:
    """Calculate when transformation starts using Scheil integral.

    Integrates dt/tau(T) and returns the (time, temperature) when
    the integral reaches 1.

    Parameters
    ----------
    times : np.ndarray
        Time array
    temperatures : np.ndarray
        Temperature array
    jmak_model : JMAKModel
        JMAK model for the phase
    fraction_threshold : float
        Fraction threshold defining "start" (default 1%)

    Returns
    -------
    tuple of (time, temperature) or None
        When transformation starts
    """
    integral = 0.0
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        T = temperatures[i]
        tau = jmak_model.incubation_time(T, fraction_threshold)
        if tau is not None and tau > 0:
            integral += dt / tau
            if integral >= 1.0:
                return (float(times[i]), float(T))
    return None
