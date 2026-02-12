"""Hardness prediction using Maynier equations.

Predicts hardness (HV/HRC) based on steel composition, cooling rate (t8/5),
and phase fractions at different radial positions.

References:
- Maynier et al., "Creusot-Loire System for the Prediction of the Mechanical
  Properties of Low Alloy Steel Products", Hardenability Concepts with
  Applications to Steel, AIME, 1978
- ASTM E140 for HV to HRC conversion
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math
import numpy as np

from app.models.material import SteelComposition


# Position labels for 4-point radial analysis
POSITION_LABELS = {
    'center': 'Center',
    'one_third': '1/3 R',
    'two_thirds': '2/3 R',
    'surface': 'Surface',
}

POSITION_KEYS = ['center', 'one_third', 'two_thirds', 'surface']


@dataclass
class HardnessResult:
    """Results of hardness prediction at multiple positions.

    Attributes
    ----------
    hardness_hv : dict
        Vickers hardness at each position {position_key: HV}
    hardness_hrc : dict
        Rockwell C hardness at each position {position_key: HRC}
    t8_5_values : dict
        t8/5 cooling times at each position {position_key: seconds}
    phase_fractions : dict
        Phase fractions at each position {position_key: {phase: fraction}}
    carbon_equivalent : float
        CE(IIW) value
    ideal_diameter : float
        Grossmann DI in inches
    composition : dict
        Steel composition used for prediction
    """
    hardness_hv: Dict[str, float] = field(default_factory=dict)
    hardness_hrc: Dict[str, float] = field(default_factory=dict)
    t8_5_values: Dict[str, float] = field(default_factory=dict)
    phase_fractions: Dict[str, Dict[str, float]] = field(default_factory=dict)
    carbon_equivalent: float = 0.0
    ideal_diameter: float = 0.0
    composition: Dict[str, float] = field(default_factory=dict)
    # Mechanical properties
    uts_mpa: Dict[str, float] = field(default_factory=dict)
    ys_mpa: Dict[str, float] = field(default_factory=dict)
    elongation_pct: Dict[str, float] = field(default_factory=dict)
    toughness_rating: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'hardness_hv': self.hardness_hv,
            'hardness_hrc': self.hardness_hrc,
            't8_5_values': self.t8_5_values,
            'phase_fractions': self.phase_fractions,
            'carbon_equivalent': self.carbon_equivalent,
            'ideal_diameter': self.ideal_diameter,
            'composition': self.composition,
            'uts_mpa': self.uts_mpa,
            'ys_mpa': self.ys_mpa,
            'elongation_pct': self.elongation_pct,
            'toughness_rating': self.toughness_rating,
        }


class HardnessPredictor:
    """Predicts hardness using Maynier equations.

    The Maynier equations predict phase-specific hardness based on
    chemical composition and cooling rate, then combine them using
    a rule of mixtures based on phase fractions.
    """

    def __init__(self, composition: SteelComposition):
        """Initialize predictor with steel composition.

        Parameters
        ----------
        composition : SteelComposition
            Steel composition model instance
        """
        self.comp = composition.to_dict()
        self.carbon_equivalent = composition.carbon_equivalent_iiw
        self.ideal_diameter = composition.ideal_diameter_di

    def _martensite_hardness(self, vr: float = 100.0) -> float:
        """Calculate martensite hardness using Maynier equation.

        HV_M = 127 + 949*C + 27*Si + 11*Mn + 8*Ni + 16*Cr + 21*log10(Vr)

        Parameters
        ----------
        vr : float
            Cooling rate in K/s (default 100 K/s)

        Returns
        -------
        float
            Martensite hardness in HV
        """
        C = self.comp['C']
        Si = self.comp['Si']
        Mn = self.comp['Mn']
        Ni = self.comp['Ni']
        Cr = self.comp['Cr']

        # Clamp cooling rate to avoid log of zero
        vr = max(vr, 0.1)

        hv = (127 + 949*C + 27*Si + 11*Mn + 8*Ni + 16*Cr +
              21*math.log10(vr))

        return max(hv, 100.0)  # Minimum reasonable hardness

    def _bainite_hardness(self, t8_5: float) -> float:
        """Calculate bainite hardness using Maynier equation.

        HV_B = -109 + 1.7C + 75*C + 19*Si + 4*Mn + 1.1*Ni + 8*Cr + 21*Mo
               + 18.1*log10(t8_5) * (72*C + 13*Si + 5*Mn + 3*Ni + 2*Cr + 6*Mo)
               - ... (simplified form)

        This is a simplified Maynier bainite equation.

        Parameters
        ----------
        t8_5 : float
            Cooling time 800-500 degC in seconds

        Returns
        -------
        float
            Bainite hardness in HV
        """
        C = self.comp['C']
        Si = self.comp['Si']
        Mn = self.comp['Mn']
        Ni = self.comp['Ni']
        Cr = self.comp['Cr']
        Mo = self.comp['Mo']

        # Clamp t8/5 to reasonable range
        t8_5 = max(t8_5, 0.1)

        # Simplified Maynier bainite equation
        hv = (-109 + 1.7*C + 75*C + 19*Si + 4*Mn + 1.1*Ni + 8*Cr + 21*Mo +
              18.1*math.log10(t8_5) * (72*C + 13*Si + 5*Mn + 3*Ni + 2*Cr + 6*Mo))

        # More practical simplified form
        hv = 200 + 500*C + 30*Si + 20*Mn + 10*Ni + 30*Cr + 50*Mo - 5*math.log10(t8_5)

        return max(hv, 150.0)

    def _ferrite_pearlite_hardness(self, t8_5: float) -> float:
        """Calculate ferrite+pearlite hardness using Maynier equation.

        HV_FP = 42 + 223*C + 53*Si + 30*Mn + 12.6*Ni + 7*Cr + 19*Mo
                + (10 - 19*Si + 4*Ni + 8*Cr + 130*V) * log10(Vr)

        Parameters
        ----------
        t8_5 : float
            Cooling time 800-500 degC in seconds

        Returns
        -------
        float
            Ferrite+pearlite hardness in HV
        """
        C = self.comp['C']
        Si = self.comp['Si']
        Mn = self.comp['Mn']
        Ni = self.comp['Ni']
        Cr = self.comp['Cr']
        Mo = self.comp['Mo']
        V = self.comp['V']

        # Clamp t8/5 to reasonable range
        t8_5 = max(t8_5, 0.1)

        # Convert t8/5 to cooling rate (300 K / t8_5 seconds)
        vr = 300.0 / t8_5

        hv = (42 + 223*C + 53*Si + 30*Mn + 12.6*Ni + 7*Cr + 19*Mo +
              (10 - 19*Si + 4*Ni + 8*Cr + 130*V) * math.log10(vr))

        return max(hv, 100.0)

    def predict_hardness(
        self,
        phase_fractions: Dict[str, float],
        t8_5: float
    ) -> float:
        """Predict composite hardness at a single position.

        Uses rule of mixtures to combine phase-specific hardness values
        weighted by phase fractions.

        Parameters
        ----------
        phase_fractions : dict
            Phase fractions {martensite, bainite, ferrite, pearlite, retained_austenite}
        t8_5 : float
            Cooling time 800-500 degC in seconds

        Returns
        -------
        float
            Composite hardness in HV
        """
        # Calculate cooling rate for martensite equation
        vr = 300.0 / max(t8_5, 0.1)

        # Calculate phase-specific hardness
        hv_m = self._martensite_hardness(vr)
        hv_b = self._bainite_hardness(t8_5)
        hv_fp = self._ferrite_pearlite_hardness(t8_5)

        # Get phase fractions
        f_m = phase_fractions.get('martensite', 0.0)
        f_b = phase_fractions.get('bainite', 0.0)
        f_f = phase_fractions.get('ferrite', 0.0)
        f_p = phase_fractions.get('pearlite', 0.0)
        f_ra = phase_fractions.get('retained_austenite', 0.0)

        # Combine using rule of mixtures
        # Treat ferrite and pearlite together, retained austenite as soft
        hv_composite = (f_m * hv_m +
                        f_b * hv_b +
                        (f_f + f_p) * hv_fp +
                        f_ra * 200.0)  # Retained austenite ~200 HV

        return max(hv_composite, 100.0)

    def predict_uts(self, hv: float) -> float:
        """Estimate ultimate tensile strength from Vickers hardness.

        UTS (MPa) ~ 3.45 * HV for steels (valid range HV 100-700).

        Parameters
        ----------
        hv : float
            Vickers hardness

        Returns
        -------
        float
            Estimated UTS in MPa
        """
        return 3.45 * hv

    def predict_ys(self, uts: float, phase_fractions: Dict[str, float]) -> float:
        """Estimate yield strength from UTS, adjusted by dominant microstructure.

        Martensite-dominant: YS ~ 0.90 * UTS
        Bainite-dominant: YS ~ 0.85 * UTS
        Ferrite-pearlite: YS ~ 0.70 * UTS

        Parameters
        ----------
        uts : float
            Ultimate tensile strength in MPa
        phase_fractions : dict
            Phase fractions

        Returns
        -------
        float
            Estimated yield strength in MPa
        """
        f_m = phase_fractions.get('martensite', 0.0)
        f_b = phase_fractions.get('bainite', 0.0)
        if f_m > 0.5:
            ratio = 0.90
        elif f_b > 0.3:
            ratio = 0.85
        else:
            ratio = 0.70
        return ratio * uts

    def predict_elongation(self, phase_fractions: Dict[str, float]) -> float:
        """Estimate elongation (%) from phase fractions using rule of mixtures.

        Typical elongation by phase:
        - Ferrite-pearlite: 20-30%
        - Bainite: 12-20%
        - Martensite (untempered): 5-12%
        - Retained austenite: ~20%

        Parameters
        ----------
        phase_fractions : dict
            Phase fractions

        Returns
        -------
        float
            Estimated elongation in percent
        """
        f_m = phase_fractions.get('martensite', 0.0)
        f_b = phase_fractions.get('bainite', 0.0)
        f_f = phase_fractions.get('ferrite', 0.0)
        f_p = phase_fractions.get('pearlite', 0.0)
        f_ra = phase_fractions.get('retained_austenite', 0.0)
        return f_m * 8.0 + f_b * 16.0 + (f_f + f_p) * 25.0 + f_ra * 20.0

    def predict_toughness_rating(self, phase_fractions: Dict[str, float]) -> str:
        """Qualitative impact toughness rating based on microstructure.

        High untempered martensite (>80%) is brittle: 'poor'.
        Mixed microstructure (40-80% martensite): 'acceptable'.
        Bainite/ferrite-dominated: 'good'.

        Parameters
        ----------
        phase_fractions : dict
            Phase fractions

        Returns
        -------
        str
            'good', 'acceptable', or 'poor'
        """
        f_m = phase_fractions.get('martensite', 0.0)
        if f_m > 0.80:
            return 'poor'
        elif f_m > 0.40:
            return 'acceptable'
        else:
            return 'good'

    def hv_to_hrc(self, hv: float) -> Optional[float]:
        """Convert Vickers hardness to Rockwell C.

        Uses ASTM E140 approximation. HRC is only valid for HV > ~200.

        Parameters
        ----------
        hv : float
            Vickers hardness

        Returns
        -------
        float or None
            Rockwell C hardness, or None if HV is too low
        """
        if hv < 200:
            return None

        # ASTM E140 polynomial approximation
        # Based on standard conversion tables:
        # 240 HV = 21 HRC, 390 HV = 40 HRC, 513 HV = 50 HRC
        # 577 HV = 54 HRC, 640 HV = 58 HRC, 746 HV = 63 HRC
        # Using polynomial fit: HRC = a*HV^2 + b*HV + c
        # Fit: HRC = -0.0001*HV^2 + 0.1755*HV - 8.48
        hrc = -0.0001 * hv * hv + 0.1755 * hv - 8.48

        return max(min(hrc, 68.0), 20.0)  # HRC valid range ~20-68


def predict_hardness_profile(
    composition: SteelComposition,
    temperatures: np.ndarray,
    times: np.ndarray,
    phase_tracker,
    t8_5_values: Optional[Dict[str, float]] = None
) -> HardnessResult:
    """Predict hardness at 4 radial positions.

    Convenience function for simulation integration.

    Parameters
    ----------
    composition : SteelComposition
        Steel composition model
    temperatures : np.ndarray
        Temperature field [time, position]
    times : np.ndarray
        Time array in seconds
    phase_tracker : PhaseTracker
        Phase tracker instance for phase prediction
    t8_5_values : dict, optional
        Pre-calculated t8/5 at each position. If None, calculated from temperatures.

    Returns
    -------
    HardnessResult
        Hardness prediction results at 4 positions
    """
    if phase_tracker is None:
        raise ValueError("phase_tracker is required for hardness prediction")

    predictor = HardnessPredictor(composition)
    result = HardnessResult(
        carbon_equivalent=composition.carbon_equivalent_iiw,
        ideal_diameter=composition.ideal_diameter_di,
        composition=composition.to_dict()
    )

    n_positions = temperatures.shape[1]

    # Calculate indices for the 4 positions
    indices = {
        'center': 0,
        'one_third': n_positions // 3,
        'two_thirds': 2 * n_positions // 3,
        'surface': n_positions - 1,
    }

    for pos_key, idx in indices.items():
        # Get temperature at this position
        temp_at_pos = temperatures[:, idx]

        # Calculate or use provided t8/5
        if t8_5_values and pos_key in t8_5_values:
            t8_5 = t8_5_values[pos_key]
        else:
            t8_5 = _calculate_t8_5(times, temp_at_pos)

        result.t8_5_values[pos_key] = t8_5

        # Predict phases at this position
        phases = phase_tracker.predict_phases(times, temp_at_pos, t8_5)
        if phases is None:
            # Default to ferrite-pearlite if phase prediction fails
            phase_dict = {'martensite': 0.0, 'bainite': 0.0, 'ferrite': 0.5, 'pearlite': 0.5, 'retained_austenite': 0.0}
        else:
            phase_dict = phases.to_dict()
        result.phase_fractions[pos_key] = phase_dict

        # Predict hardness
        hv = predictor.predict_hardness(phase_dict, t8_5)
        result.hardness_hv[pos_key] = round(hv, 1)

        # Convert to HRC
        hrc = predictor.hv_to_hrc(hv)
        result.hardness_hrc[pos_key] = round(hrc, 1) if hrc else None

        # Mechanical properties
        uts = predictor.predict_uts(hv)
        result.uts_mpa[pos_key] = round(uts, 0)
        result.ys_mpa[pos_key] = round(predictor.predict_ys(uts, phase_dict), 0)
        result.elongation_pct[pos_key] = round(predictor.predict_elongation(phase_dict), 1)
        result.toughness_rating[pos_key] = predictor.predict_toughness_rating(phase_dict)

    return result


def _calculate_t8_5(times: np.ndarray, temperatures: np.ndarray) -> float:
    """Calculate t8/5 cooling time from temperature history.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    temperatures : np.ndarray
        Temperature array in Celsius

    Returns
    -------
    float
        Cooling time from 800 to 500 degC in seconds
    """
    # Find when temperature crosses 800 and 500 during cooling
    idx_800 = None
    idx_500 = None

    # Look for first crossing of 800 from above (cooling)
    for i in range(1, len(temperatures)):
        if temperatures[i-1] > 800 and temperatures[i] <= 800:
            # Interpolate for more accuracy
            frac = (800 - temperatures[i]) / (temperatures[i-1] - temperatures[i])
            idx_800 = i - frac
            break

    # Look for first crossing of 500 after 800 crossing
    if idx_800 is not None:
        start_idx = int(idx_800) + 1
        for i in range(start_idx, len(temperatures)):
            if temperatures[i-1] > 500 and temperatures[i] <= 500:
                frac = (500 - temperatures[i]) / (temperatures[i-1] - temperatures[i])
                idx_500 = i - frac
                break

    if idx_800 is not None and idx_500 is not None:
        # Interpolate times
        t_800 = np.interp(idx_800, np.arange(len(times)), times)
        t_500 = np.interp(idx_500, np.arange(len(times)), times)
        return max(t_500 - t_800, 0.1)

    # Fallback: estimate from cooling rate
    if temperatures.max() > 800 and temperatures.min() < 500:
        # Use simple approach
        idx_800_approx = np.argmin(np.abs(temperatures - 800))
        idx_500_approx = np.argmin(np.abs(temperatures - 500))
        if idx_500_approx > idx_800_approx:
            return max(times[idx_500_approx] - times[idx_800_approx], 0.1)

    # Default moderate cooling
    return 10.0
