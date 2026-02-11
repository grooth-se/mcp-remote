"""Jominy end-quench test simulation.

Simulates the standard ASTM A255 Jominy hardenability test and predicts
hardness at standard distances from the quenched end.

The Jominy test uses a 25.4mm (1 inch) diameter, 100mm long cylindrical
specimen. One end is quenched with a water jet while the rest air cools,
creating a gradient of cooling rates along the length.

References:
- ASTM A255 - Standard Test Methods for Determining Hardenability of Steel
- Jominy, W.E., "A Hardenability Test for Carburizing Steel", Trans. ASM, 1938
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from app.models.material import SteelComposition, PhaseDiagram
from app.services.hardness_predictor import HardnessPredictor
from app.services.phase_tracker import PhaseTracker


# Standard Jominy distances (mm) from quenched end
JOMINY_DISTANCES_MM = [1.5, 3, 5, 7, 9, 11, 13, 15, 20, 25, 30, 35, 40, 45, 50]

# Approximate t8/5 cooling times (seconds) at each Jominy distance
# Based on empirical correlations from literature
# These represent water jet quench at the end, air cooling elsewhere
JOMINY_T85_VALUES = {
    1.5: 1.5,    # Very fast cooling at quenched end
    3: 2.5,
    5: 4.0,
    7: 6.0,
    9: 8.0,
    11: 12.0,
    13: 16.0,
    15: 22.0,
    20: 40.0,
    25: 65.0,
    30: 100.0,
    35: 140.0,
    40: 190.0,
    45: 240.0,
    50: 300.0,
}

# Approximate cooling rates (K/s) at each distance
# Calculated as 300K / t8/5
JOMINY_COOLING_RATES = {d: 300.0 / t for d, t in JOMINY_T85_VALUES.items()}


@dataclass
class JominyResult:
    """Results of Jominy end-quench simulation.

    Attributes
    ----------
    distances_mm : list
        Distances from quenched end in mm
    hardness_hv : list
        Vickers hardness at each distance
    hardness_hrc : list
        Rockwell C hardness at each distance (None if HV < 200)
    t85_values : list
        t8/5 cooling times at each distance in seconds
    cooling_rates : list
        Cooling rates at each distance in K/s
    phase_fractions : list
        Phase fractions at each distance
    carbon_equivalent : float
        CE(IIW) value
    ideal_diameter : float
        Grossmann DI in inches
    j_distance_50hrc : float or None
        Jominy distance (mm) where hardness reaches 50 HRC (if applicable)
    composition : dict
        Steel composition used
    """
    distances_mm: List[float] = field(default_factory=list)
    hardness_hv: List[float] = field(default_factory=list)
    hardness_hrc: List[Optional[float]] = field(default_factory=list)
    t85_values: List[float] = field(default_factory=list)
    cooling_rates: List[float] = field(default_factory=list)
    phase_fractions: List[Dict[str, float]] = field(default_factory=list)
    carbon_equivalent: float = 0.0
    ideal_diameter: float = 0.0
    j_distance_50hrc: Optional[float] = None
    composition: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'distances_mm': self.distances_mm,
            'hardness_hv': self.hardness_hv,
            'hardness_hrc': self.hardness_hrc,
            't85_values': self.t85_values,
            'cooling_rates': self.cooling_rates,
            'phase_fractions': self.phase_fractions,
            'carbon_equivalent': self.carbon_equivalent,
            'ideal_diameter': self.ideal_diameter,
            'j_distance_50hrc': self.j_distance_50hrc,
            'composition': self.composition,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'JominyResult':
        """Create from dictionary."""
        return cls(**data)


class JominySimulator:
    """Simulates Jominy end-quench test for hardenability prediction."""

    def __init__(
        self,
        composition: SteelComposition,
        phase_diagram: Optional[PhaseDiagram] = None
    ):
        """Initialize Jominy simulator.

        Parameters
        ----------
        composition : SteelComposition
            Steel composition model
        phase_diagram : PhaseDiagram, optional
            Phase diagram for phase prediction
        """
        self.composition = composition
        self.phase_diagram = phase_diagram
        self.predictor = HardnessPredictor(composition)

        # Initialize phase tracker if diagram available
        self.phase_tracker = None
        if phase_diagram:
            self.phase_tracker = PhaseTracker(phase_diagram)

    def simulate(
        self,
        distances: Optional[List[float]] = None,
        austenitizing_temp: float = 850.0
    ) -> JominyResult:
        """Run Jominy end-quench simulation.

        Parameters
        ----------
        distances : list, optional
            Custom distances (mm) from quenched end. If None, uses standard distances.
        austenitizing_temp : float
            Austenitizing temperature in Celsius (default 850)

        Returns
        -------
        JominyResult
            Simulation results at all distances
        """
        if distances is None:
            distances = JOMINY_DISTANCES_MM.copy()

        result = JominyResult(
            distances_mm=distances,
            carbon_equivalent=self.composition.carbon_equivalent_iiw,
            ideal_diameter=self.composition.ideal_diameter_di,
            composition=self.composition.to_dict()
        )

        for d in distances:
            # Get cooling characteristics at this distance
            t85 = self._get_t85_at_distance(d)
            cooling_rate = 300.0 / t85

            result.t85_values.append(t85)
            result.cooling_rates.append(cooling_rate)

            # Predict phase fractions
            phases = self._predict_phases(t85, austenitizing_temp)
            result.phase_fractions.append(phases)

            # Predict hardness
            hv = self.predictor.predict_hardness(phases, t85)
            hrc = self.predictor.hv_to_hrc(hv)

            result.hardness_hv.append(round(hv, 1))
            result.hardness_hrc.append(round(hrc, 1) if hrc else None)

        # Calculate J distance for 50 HRC (hardenability metric)
        result.j_distance_50hrc = self._find_j_distance(
            result.distances_mm,
            result.hardness_hrc,
            target_hrc=50.0
        )

        return result

    def _get_t85_at_distance(self, distance_mm: float) -> float:
        """Get t8/5 cooling time at a given Jominy distance.

        Uses interpolation between standard values.

        Parameters
        ----------
        distance_mm : float
            Distance from quenched end in mm

        Returns
        -------
        float
            t8/5 cooling time in seconds
        """
        # Handle boundary cases
        if distance_mm <= 1.5:
            return JOMINY_T85_VALUES[1.5]
        if distance_mm >= 50:
            # Extrapolate for distances beyond 50mm
            return JOMINY_T85_VALUES[50] * (distance_mm / 50) ** 1.5

        # Interpolate between standard values
        std_distances = sorted(JOMINY_T85_VALUES.keys())
        std_t85 = [JOMINY_T85_VALUES[d] for d in std_distances]

        return float(np.interp(distance_mm, std_distances, std_t85))

    def _predict_phases(
        self,
        t85: float,
        austenitizing_temp: float = 850.0
    ) -> Dict[str, float]:
        """Predict phase fractions based on cooling rate.

        Parameters
        ----------
        t85 : float
            t8/5 cooling time in seconds
        austenitizing_temp : float
            Austenitizing temperature

        Returns
        -------
        dict
            Phase fractions {martensite, bainite, ferrite, pearlite}
        """
        if self.phase_tracker:
            # Use phase tracker if available
            # Create synthetic cooling curve for phase prediction
            times = np.linspace(0, t85 * 3, 100)

            # Simple linear cooling model from austenitizing to room temp
            total_time = t85 * 3
            temps = austenitizing_temp - (austenitizing_temp - 25) * (times / total_time)

            try:
                phases = self.phase_tracker.predict_phases(times, temps, t85)
                if phases:
                    return phases.to_dict()
            except Exception:
                pass

        # Fallback: empirical phase estimation based on t8/5
        return self._estimate_phases_from_t85(t85)

    def _estimate_phases_from_t85(self, t85: float) -> Dict[str, float]:
        """Estimate phase fractions from t8/5 using empirical rules.

        Based on typical CCT behavior for low-alloy steels.

        Parameters
        ----------
        t85 : float
            t8/5 cooling time in seconds

        Returns
        -------
        dict
            Estimated phase fractions
        """
        C = self.composition.to_dict()['C']
        CE = self.composition.carbon_equivalent_iiw

        # Estimate critical cooling times based on CE
        # Higher CE = longer times to avoid martensite
        t_ms = 2.0 + 10.0 * CE  # Martensite start threshold
        t_bs = 10.0 + 50.0 * CE  # Bainite start threshold
        t_fp = 50.0 + 200.0 * CE  # Ferrite-pearlite start threshold

        if t85 < t_ms:
            # Very fast cooling - mostly martensite
            f_m = 0.95 - 0.05 * (t85 / t_ms)
            f_b = 0.05
            f_fp = 0.0
        elif t85 < t_bs:
            # Fast cooling - martensite + bainite
            ratio = (t85 - t_ms) / (t_bs - t_ms)
            f_m = 0.90 - 0.70 * ratio
            f_b = 0.05 + 0.65 * ratio
            f_fp = 0.05 * ratio
        elif t85 < t_fp:
            # Moderate cooling - bainite dominant
            ratio = (t85 - t_bs) / (t_fp - t_bs)
            f_m = max(0.20 - 0.20 * ratio, 0)
            f_b = 0.70 - 0.50 * ratio
            f_fp = 0.10 + 0.70 * ratio
        else:
            # Slow cooling - ferrite-pearlite
            f_m = 0.0
            f_b = max(0.20 - 0.10 * ((t85 - t_fp) / t_fp), 0)
            f_fp = 1.0 - f_b

        # Normalize
        total = f_m + f_b + f_fp

        return {
            'martensite': f_m / total,
            'bainite': f_b / total,
            'ferrite': (f_fp / total) * (1 - C * 2),  # More ferrite with less C
            'pearlite': (f_fp / total) * (C * 2),
            'retained_austenite': 0.0,
        }

    def _find_j_distance(
        self,
        distances: List[float],
        hardness_hrc: List[Optional[float]],
        target_hrc: float = 50.0
    ) -> Optional[float]:
        """Find Jominy distance where hardness drops to target HRC.

        Parameters
        ----------
        distances : list
            Jominy distances in mm
        hardness_hrc : list
            HRC hardness values
        target_hrc : float
            Target HRC value (default 50)

        Returns
        -------
        float or None
            J distance in mm, or None if hardness never reaches target
        """
        valid_points = [
            (d, h) for d, h in zip(distances, hardness_hrc)
            if h is not None
        ]

        if len(valid_points) < 2:
            return None

        # Check if hardness exceeds target at quenched end
        if valid_points[0][1] < target_hrc:
            return 0.0  # Never reaches target hardness

        # Find where hardness crosses target
        for i in range(len(valid_points) - 1):
            d1, h1 = valid_points[i]
            d2, h2 = valid_points[i + 1]

            if h1 >= target_hrc and h2 < target_hrc:
                # Linear interpolation
                frac = (h1 - target_hrc) / (h1 - h2)
                return d1 + frac * (d2 - d1)

        # Hardness stays above target throughout
        return None


def simulate_jominy_test(
    composition: SteelComposition,
    phase_diagram: Optional[PhaseDiagram] = None,
    austenitizing_temp: float = 850.0
) -> JominyResult:
    """Convenience function to simulate Jominy test.

    Parameters
    ----------
    composition : SteelComposition
        Steel composition
    phase_diagram : PhaseDiagram, optional
        Phase diagram for phase prediction
    austenitizing_temp : float
        Austenitizing temperature in Celsius

    Returns
    -------
    JominyResult
        Simulation results
    """
    simulator = JominySimulator(composition, phase_diagram)
    return simulator.simulate(austenitizing_temp=austenitizing_temp)
