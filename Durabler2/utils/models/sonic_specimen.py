"""
Sonic Resonance (Ultrasonic) specimen data model.

Contains specimen geometry, mass, and ultrasonic velocity measurements
for determining elastic modulus, shear modulus, and Poisson's ratio.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import math


@dataclass
class SonicSpecimen:
    """
    Container for ultrasonic test specimen data.

    Parameters
    ----------
    specimen_id : str
        Specimen identifier
    specimen_type : str
        'round' or 'square'
    diameter : float
        Diameter for round specimens (mm)
    side_length : float
        Side length for square specimens (mm)
    length : float
        Specimen length (mm)
    mass : float
        Specimen mass (g)
    material : str
        Material designation
    """
    specimen_id: str
    specimen_type: str  # 'round' or 'square'
    diameter: float = 0.0  # mm, for round specimens
    side_length: float = 0.0  # mm, for square specimens
    length: float = 0.0  # mm
    mass: float = 0.0  # grams
    material: str = ""

    @property
    def cross_section_area(self) -> float:
        """Calculate cross-sectional area in mm²."""
        if self.specimen_type == 'round':
            return math.pi * (self.diameter / 2) ** 2
        else:  # square
            return self.side_length ** 2

    @property
    def volume(self) -> float:
        """Calculate specimen volume in mm³."""
        return self.cross_section_area * self.length

    @property
    def volume_m3(self) -> float:
        """Calculate specimen volume in m³."""
        return self.volume * 1e-9  # mm³ to m³

    @property
    def mass_kg(self) -> float:
        """Mass in kg."""
        return self.mass / 1000  # g to kg

    @property
    def density(self) -> float:
        """
        Calculate density in kg/m³.

        Returns
        -------
        float
            Density (kg/m³)
        """
        if self.volume_m3 > 0:
            return self.mass_kg / self.volume_m3
        return 0.0

    @property
    def density_gcc(self) -> float:
        """Density in g/cm³."""
        return self.density / 1000  # kg/m³ to g/cm³


@dataclass
class UltrasonicMeasurements:
    """
    Container for ultrasonic velocity measurements.

    Parameters
    ----------
    longitudinal_velocities : List[float]
        Three measurements of longitudinal (compression) wave velocity (m/s)
    shear_velocities : List[float]
        Three measurements of shear wave velocity (m/s)
    """
    longitudinal_velocities: List[float] = field(default_factory=list)
    shear_velocities: List[float] = field(default_factory=list)

    @property
    def longitudinal_avg(self) -> float:
        """Average longitudinal wave velocity (m/s)."""
        if self.longitudinal_velocities:
            return sum(self.longitudinal_velocities) / len(self.longitudinal_velocities)
        return 0.0

    @property
    def shear_avg(self) -> float:
        """Average shear wave velocity (m/s)."""
        if self.shear_velocities:
            return sum(self.shear_velocities) / len(self.shear_velocities)
        return 0.0

    @property
    def longitudinal_std(self) -> float:
        """Standard deviation of longitudinal velocities."""
        if len(self.longitudinal_velocities) < 2:
            return 0.0
        avg = self.longitudinal_avg
        variance = sum((v - avg) ** 2 for v in self.longitudinal_velocities) / (len(self.longitudinal_velocities) - 1)
        return math.sqrt(variance)

    @property
    def shear_std(self) -> float:
        """Standard deviation of shear velocities."""
        if len(self.shear_velocities) < 2:
            return 0.0
        avg = self.shear_avg
        variance = sum((v - avg) ** 2 for v in self.shear_velocities) / (len(self.shear_velocities) - 1)
        return math.sqrt(variance)
