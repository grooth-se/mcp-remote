"""Heat-Affected Zone (HAZ) prediction for welding.

Uses the Rosenthal analytical solution to sweep transverse distances
from the weld line and predict:
- Zone boundaries (CGHAZ, FGHAZ, ICHAZ, base metal)
- Peak temperature profiles
- t8/5 cooling times at each distance
- Hardness traverse using Maynier equations
- Thermal cycles at representative zone positions

Zone definitions (typical for C-Mn steels):
- Fusion Zone:  T_peak > solidus (~1500 °C)
- CGHAZ:        T_peak > 1100 °C  (coarse-grained, grain growth)
- FGHAZ:        T_peak > Ac3 (~900 °C) and < 1100 °C  (fine-grained)
- ICHAZ:        T_peak > Ac1 (~727 °C) and < Ac3  (intercritical)
- Base Metal:   T_peak < Ac1
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from .rosenthal_solver import RosenthalSolver


# Default zone boundary temperatures (°C)
DEFAULT_SOLIDUS = 1500.0
DEFAULT_CGHAZ_TEMP = 1100.0
DEFAULT_AC3 = 900.0
DEFAULT_AC1 = 727.0


@dataclass
class HAZResult:
    """Results of HAZ prediction.

    Attributes
    ----------
    fusion_zone_width : float
        Half-width of fusion zone (mm)
    cghaz_width : float
        Width of CGHAZ (mm) — from fusion boundary to 1100°C isotherm
    fghaz_width : float
        Width of FGHAZ (mm) — from 1100°C to Ac3
    ichaz_width : float
        Width of ICHAZ (mm) — from Ac3 to Ac1
    total_haz_width : float
        Total HAZ width from fusion boundary to Ac1 (mm)
    distances_mm : list
        Transverse distances sampled (mm)
    peak_temperatures : list
        Peak temperature at each distance (°C)
    t8_5_values : list
        t8/5 cooling times at each distance (s), None if < 800°C
    hardness_profile : list
        Hardness (HV) at each distance
    zone_phases : dict
        Phase fractions for representative zone positions
    zone_hardness : dict
        Hardness for each zone {zone_name: HV}
    thermal_cycles : dict
        Thermal cycles at key positions {zone: {'times': [], 'temps': []}}
    """
    fusion_zone_width: float = 0.0
    cghaz_width: float = 0.0
    fghaz_width: float = 0.0
    ichaz_width: float = 0.0
    total_haz_width: float = 0.0
    distances_mm: List[float] = field(default_factory=list)
    peak_temperatures: List[float] = field(default_factory=list)
    t8_5_values: List[Optional[float]] = field(default_factory=list)
    hardness_profile: List[float] = field(default_factory=list)
    zone_phases: Dict[str, dict] = field(default_factory=dict)
    zone_hardness: Dict[str, float] = field(default_factory=dict)
    thermal_cycles: Dict[str, dict] = field(default_factory=dict)
    zone_boundaries: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to serializable dictionary."""
        return {
            'fusion_zone_width': self.fusion_zone_width,
            'cghaz_width': self.cghaz_width,
            'fghaz_width': self.fghaz_width,
            'ichaz_width': self.ichaz_width,
            'total_haz_width': self.total_haz_width,
            'distances_mm': self.distances_mm,
            'peak_temperatures': self.peak_temperatures,
            't8_5_values': self.t8_5_values,
            'hardness_profile': self.hardness_profile,
            'zone_phases': self.zone_phases,
            'zone_hardness': self.zone_hardness,
            'zone_boundaries': self.zone_boundaries,
            'thermal_cycles': self.thermal_cycles,
        }

    def max_hardness(self) -> float:
        """Return maximum hardness in the HAZ."""
        if not self.hardness_profile:
            return 0.0
        return max(self.hardness_profile)

    def passes_hardness_limit(self, limit_hv: float = 350.0) -> bool:
        """Check if all hardness values are below the limit."""
        return self.max_hardness() <= limit_hv


class HAZPredictor:
    """Predicts HAZ characteristics from Rosenthal thermal solution.

    Sweeps transverse distance from the weld line, computing peak
    temperatures, cooling times, and hardness at each point to build
    a complete HAZ profile.
    """

    def __init__(
        self,
        rosenthal: RosenthalSolver,
        composition=None,
        phase_diagram=None,
        ac1: float = DEFAULT_AC1,
        ac3: float = DEFAULT_AC3,
    ):
        """Initialize HAZ predictor.

        Parameters
        ----------
        rosenthal : RosenthalSolver
            Configured Rosenthal solver
        composition : SteelComposition, optional
            Steel composition for hardness prediction
        phase_diagram : PhaseDiagram, optional
            Phase diagram for transformation temperatures
        ac1 : float
            Ac1 temperature (°C), overridden by phase_diagram if available
        ac3 : float
            Ac3 temperature (°C), overridden by phase_diagram if available
        """
        self.rosenthal = rosenthal
        self.composition = composition
        self.phase_diagram = phase_diagram

        # Set transformation temperatures
        if phase_diagram:
            temps = phase_diagram.temps_dict
            self.ac1 = temps.get('Ac1', ac1)
            self.ac3 = temps.get('Ac3', ac3)
        else:
            self.ac1 = ac1
            self.ac3 = ac3

    def predict(
        self,
        n_points: int = 50,
        max_distance_mm: float = 20.0,
        z: float = 0.0,
        hardness_limit: float = 350.0,
    ) -> HAZResult:
        """Run full HAZ prediction.

        Parameters
        ----------
        n_points : int
            Number of sample points across the traverse
        max_distance_mm : float
            Maximum distance from weld center to sample (mm)
        z : float
            Depth below surface (m)
        hardness_limit : float
            HV limit for pass/fail assessment

        Returns
        -------
        HAZResult
        """
        result = HAZResult()

        # Convert distances to meters for Rosenthal
        distances_mm = np.linspace(0.5, max_distance_mm, n_points)
        distances_m = distances_mm / 1000.0

        # 1. Calculate peak temperatures at all distances
        peak_temps = self.rosenthal.peak_temperature_at_distance(distances_m, z)

        # 2. Find zone boundaries
        fz_dist = self.rosenthal.haz_boundary_distance(DEFAULT_SOLIDUS, z) * 1000  # mm
        cghaz_dist = self.rosenthal.haz_boundary_distance(DEFAULT_CGHAZ_TEMP, z) * 1000
        fghaz_dist = self.rosenthal.haz_boundary_distance(self.ac3, z) * 1000
        ichaz_dist = self.rosenthal.haz_boundary_distance(self.ac1, z) * 1000

        result.fusion_zone_width = fz_dist
        result.cghaz_width = max(0, cghaz_dist - fz_dist)
        result.fghaz_width = max(0, fghaz_dist - cghaz_dist)
        result.ichaz_width = max(0, ichaz_dist - fghaz_dist)
        result.total_haz_width = max(0, ichaz_dist - fz_dist)

        result.zone_boundaries = {
            'fusion': fz_dist,
            'cghaz': cghaz_dist,
            'fghaz': fghaz_dist,
            'ichaz': ichaz_dist,
        }

        # 3. Calculate t8/5 at each distance
        t8_5_values = []
        for d_m in distances_m:
            t85 = self.rosenthal.t8_5_at_point(d_m, z)
            t8_5_values.append(t85)

        # 4. Calculate hardness at each distance
        hardness_values = []
        if self.composition:
            from .hardness_predictor import HardnessPredictor
            from .phase_tracker import PhaseTracker

            predictor = HardnessPredictor(self.composition)
            tracker = PhaseTracker(self.phase_diagram)

            for i, (d_mm, t_peak, t85) in enumerate(
                zip(distances_mm, peak_temps, t8_5_values)
            ):
                if t_peak < self.ac1:
                    # Below Ac1 — base metal, no transformation
                    hardness_values.append(150.0)  # Typical base metal
                elif t85 is not None and t85 > 0:
                    # In HAZ — predict phases and hardness
                    cooling_rate = 300.0 / t85
                    phases = tracker.predict_phases(
                        np.array([0, t85]), np.array([800, 500]), t8_5=t85
                    )
                    hv = predictor.predict_hardness(phases.to_dict(), t85)
                    hardness_values.append(hv)
                else:
                    # Peak > Ac1 but t8/5 not calculable (near weld center)
                    # Use fast cooling estimate
                    phases = tracker.predict_phases(
                        np.array([0, 2]), np.array([800, 500]), t8_5=2.0
                    )
                    hv = predictor.predict_hardness(phases.to_dict(), 2.0)
                    hardness_values.append(hv)
        else:
            # No composition — estimate based on peak temperature only
            for t_peak in peak_temps:
                if t_peak > DEFAULT_CGHAZ_TEMP:
                    hardness_values.append(350.0)  # High estimate
                elif t_peak > self.ac3:
                    hardness_values.append(280.0)
                elif t_peak > self.ac1:
                    hardness_values.append(220.0)
                else:
                    hardness_values.append(150.0)

        # 5. Zone-representative phases and hardness
        zone_positions = {}
        if fz_dist > 0 and cghaz_dist > fz_dist:
            zone_positions['cghaz'] = (fz_dist + cghaz_dist) / 2
        if cghaz_dist > 0 and fghaz_dist > cghaz_dist:
            zone_positions['fghaz'] = (cghaz_dist + fghaz_dist) / 2
        if fghaz_dist > 0 and ichaz_dist > fghaz_dist:
            zone_positions['ichaz'] = (fghaz_dist + ichaz_dist) / 2

        if self.composition:
            from .hardness_predictor import HardnessPredictor
            from .phase_tracker import PhaseTracker

            predictor = HardnessPredictor(self.composition)
            tracker = PhaseTracker(self.phase_diagram)

            for zone_name, zone_mm in zone_positions.items():
                d_m = zone_mm / 1000.0
                t85 = self.rosenthal.t8_5_at_point(d_m, z)
                if t85 and t85 > 0:
                    phases = tracker.predict_phases(
                        np.array([0, t85]), np.array([800, 500]), t8_5=t85
                    )
                    hv = predictor.predict_hardness(phases.to_dict(), t85)
                    result.zone_phases[zone_name] = phases.to_dict()
                    result.zone_hardness[zone_name] = hv

        # 6. Thermal cycles at representative positions
        cycle_positions = {
            'centerline': 0.001,  # 1mm from center
        }
        for zone_name, zone_mm in zone_positions.items():
            cycle_positions[zone_name] = zone_mm / 1000.0

        # Add base metal position
        if ichaz_dist > 0:
            cycle_positions['base_metal'] = (ichaz_dist + 5) / 1000.0

        for label, y_m in cycle_positions.items():
            times, temps = self.rosenthal.thermal_cycle_at_point(
                y_m, z, duration=120.0, n_points=200
            )
            result.thermal_cycles[label] = {
                'times': times.tolist(),
                'temps': temps.tolist(),
            }

        # Store results
        result.distances_mm = distances_mm.tolist()
        result.peak_temperatures = peak_temps.tolist()
        result.t8_5_values = t8_5_values
        result.hardness_profile = hardness_values

        return result
