"""Phase transformation tracking during cooling.

Uses simplified CCT diagram interpolation to predict phase fractions
based on cooling rate and transformation temperatures.

Implements:
- Martensite transformation (Ms, Mf temperatures)
- Simplified CCT-based phase prediction
- Koistinen-Marburger equation for martensite fraction
"""
from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np

from app.models import PhaseDiagram


@dataclass
class PhaseResult:
    """Phase transformation results."""
    martensite: float = 0.0
    bainite: float = 0.0
    ferrite: float = 0.0
    pearlite: float = 0.0
    retained_austenite: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'martensite': self.martensite,
            'bainite': self.bainite,
            'ferrite': self.ferrite,
            'pearlite': self.pearlite,
            'retained_austenite': self.retained_austenite
        }

    def normalize(self) -> 'PhaseResult':
        """Ensure fractions sum to 1.0."""
        total = self.martensite + self.bainite + self.ferrite + self.pearlite + self.retained_austenite
        if total > 0:
            self.martensite /= total
            self.bainite /= total
            self.ferrite /= total
            self.pearlite /= total
            self.retained_austenite /= total
        return self


class PhaseTracker:
    """Tracks phase transformations during cooling.

    Uses CCT/TTT diagram data to predict final phase fractions
    based on the thermal history.
    """

    # Koistinen-Marburger coefficient (typical for steels)
    KM_COEFFICIENT = 0.011  # K^-1

    def __init__(self, phase_diagram: Optional[PhaseDiagram] = None):
        """Initialize phase tracker.

        Parameters
        ----------
        phase_diagram : PhaseDiagram, optional
            Phase diagram model with transformation temperatures
        """
        self.diagram = phase_diagram

        # Get transformation temperatures
        if phase_diagram:
            temps = phase_diagram.temps_dict
            self.ms = temps.get('Ms', 350)
            self.mf = temps.get('Mf', 200)
            self.bs = temps.get('Bs', 550)
            self.bf = temps.get('Bf', 400)
            self.ac1 = temps.get('Ac1', 727)
            self.ac3 = temps.get('Ac3', 850)
        else:
            # Default values for plain carbon steel
            self.ms = 350
            self.mf = 200
            self.bs = 550
            self.bf = 400
            self.ac1 = 727
            self.ac3 = 850

    def predict_phases(
        self,
        times: np.ndarray,
        temperatures: np.ndarray,
        t8_5: Optional[float] = None
    ) -> PhaseResult:
        """Predict final phase fractions from cooling curve.

        Parameters
        ----------
        times : np.ndarray
            Time array (seconds)
        temperatures : np.ndarray
            Temperature array (Celsius)
        t8_5 : float, optional
            Cooling time 800-500°C (seconds)

        Returns
        -------
        PhaseResult
            Predicted phase fractions
        """
        result = PhaseResult()

        # Calculate average cooling rate in transformation range
        cooling_rate = self._calculate_cooling_rate(times, temperatures, t8_5)

        # Simplified CCT-based prediction based on cooling rate
        if cooling_rate > 100:  # Very fast (>100 K/s) - water quench
            result.martensite = 0.95
            result.retained_austenite = 0.05

        elif cooling_rate > 30:  # Fast (30-100 K/s) - intense quench
            result.martensite = 0.80
            result.bainite = 0.15
            result.retained_austenite = 0.05

        elif cooling_rate > 10:  # Medium (10-30 K/s) - oil quench
            result.martensite = 0.50
            result.bainite = 0.40
            result.retained_austenite = 0.10

        elif cooling_rate > 1:  # Slow (1-10 K/s) - forced air
            result.martensite = 0.10
            result.bainite = 0.70
            result.ferrite = 0.10
            result.pearlite = 0.05
            result.retained_austenite = 0.05

        else:  # Very slow (<1 K/s) - furnace cool
            result.ferrite = 0.50
            result.pearlite = 0.45
            result.bainite = 0.05
            result.martensite = 0.0
            result.retained_austenite = 0.0

        return result.normalize()

    def _calculate_cooling_rate(
        self,
        times: np.ndarray,
        temperatures: np.ndarray,
        t8_5: Optional[float] = None
    ) -> float:
        """Calculate cooling rate in transformation range."""
        if t8_5 is not None and t8_5 > 0:
            return 300.0 / t8_5  # K/s

        # Estimate from temperature array
        idx_800 = np.argmin(np.abs(temperatures - 800))
        idx_500 = np.argmin(np.abs(temperatures - 500))

        if idx_500 > idx_800:
            dt = times[idx_500] - times[idx_800]
            if dt > 0:
                return 300.0 / dt

        # Default moderate cooling rate
        return 10.0

    def koistinen_marburger(self, temperature: float) -> float:
        """Calculate martensite fraction using Koistinen-Marburger equation.

        f_m = 1 - exp(-k * (Ms - T))

        Parameters
        ----------
        temperature : float
            Current temperature in Celsius

        Returns
        -------
        float
            Martensite fraction (0-1)
        """
        if temperature >= self.ms:
            return 0.0

        undercooling = self.ms - temperature
        f_martensite = 1.0 - np.exp(-self.KM_COEFFICIENT * undercooling)

        return min(f_martensite, 1.0)

    def get_transformation_temps(self) -> dict:
        """Get transformation temperatures as dict."""
        return {
            'Ac1': self.ac1,
            'Ac3': self.ac3,
            'Ms': self.ms,
            'Mf': self.mf,
            'Bs': self.bs,
            'Bf': self.bf,
        }
