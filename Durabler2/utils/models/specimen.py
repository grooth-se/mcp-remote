"""
Specimen data models for tensile testing.

Supports both round (cylindrical) and rectangular (flat) specimens
per ASTM E8/E8M standard.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
import math


class GeometryType(Enum):
    """Specimen geometry type."""
    ROUND = "round"
    RECTANGULAR = "rectangular"


@dataclass
class RoundSpecimen:
    """
    Cylindrical tensile specimen per ASTM E8 Figure 4.

    Parameters
    ----------
    specimen_id : str
        Unique specimen identifier
    diameter : float
        Measured diameter in mm (average of 3 measurements)
    diameter_std : float
        Standard deviation of diameter measurements in mm
    gauge_length : float
        Original gauge length L0 in mm (typically 5*d or 50mm)
    parallel_length : float
        Parallel length Lc in mm
    material : str, optional
        Material designation
    batch_number : str, optional
        Material batch/heat number
    final_diameter : float, optional
        Diameter at fracture surface in mm (for Z% calculation)
    """
    specimen_id: str
    diameter: float
    diameter_std: float
    gauge_length: float
    parallel_length: float
    material: str = ""
    batch_number: str = ""
    final_diameter: Optional[float] = None

    @property
    def geometry_type(self) -> GeometryType:
        """Return geometry type."""
        return GeometryType.ROUND

    @property
    def area(self) -> float:
        """
        Original cross-sectional area A0 in mm^2.

        A0 = pi * (d/2)^2
        """
        return math.pi * (self.diameter / 2) ** 2

    @property
    def area_uncertainty(self) -> float:
        """
        Uncertainty in cross-sectional area from diameter measurement.

        Using uncertainty propagation:
        u(A) = |dA/dd| * u(d) = pi * d/2 * u(d)
        """
        return math.pi * self.diameter / 2 * self.diameter_std


@dataclass
class RectangularSpecimen:
    """
    Flat tensile specimen per ASTM E8 Figure 1.

    Parameters
    ----------
    specimen_id : str
        Unique specimen identifier
    width : float
        Measured width in mm (average of 3 measurements)
    width_std : float
        Standard deviation of width measurements in mm
    thickness : float
        Measured thickness in mm (average of 3 measurements)
    thickness_std : float
        Standard deviation of thickness measurements in mm
    gauge_length : float
        Original gauge length L0 in mm
    parallel_length : float
        Parallel length Lc in mm
    material : str, optional
        Material designation
    batch_number : str, optional
        Material batch/heat number
    """
    specimen_id: str
    width: float
    width_std: float
    thickness: float
    thickness_std: float
    gauge_length: float
    parallel_length: float
    material: str = ""
    batch_number: str = ""

    @property
    def geometry_type(self) -> GeometryType:
        """Return geometry type."""
        return GeometryType.RECTANGULAR

    @property
    def area(self) -> float:
        """
        Original cross-sectional area A0 in mm^2.

        A0 = width * thickness
        """
        return self.width * self.thickness

    @property
    def area_uncertainty(self) -> float:
        """
        Combined uncertainty in cross-sectional area.

        Using uncertainty propagation:
        u(A)^2 = (t * u(w))^2 + (w * u(t))^2
        """
        return math.sqrt(
            (self.thickness * self.width_std) ** 2 +
            (self.width * self.thickness_std) ** 2
        )
