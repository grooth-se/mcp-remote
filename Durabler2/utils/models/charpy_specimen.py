"""
Charpy Impact Test Data Models per ASTM E23 / ISO 148-1.

This module provides dataclasses for Charpy impact test specimens,
readings, and test configuration.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np


@dataclass
class CharpyReading:
    """
    Single Charpy impact test reading.

    Attributes
    ----------
    specimen_number : int
        Sequential specimen number (1, 2, 3, ...)
    specimen_id : str
        Individual specimen identifier
    absorbed_energy : float
        Absorbed energy in Joules (J)
    lateral_expansion : float, optional
        Lateral expansion in mm (measured on broken halves)
    shear_fracture_area : float, optional
        Percentage of shear (ductile) fracture on fracture surface (%)
    """
    specimen_number: int
    specimen_id: str
    absorbed_energy: float
    lateral_expansion: Optional[float] = None
    shear_fracture_area: Optional[float] = None


@dataclass
class CharpySpecimenConfig:
    """
    Charpy specimen geometry and notch configuration per ASTM E23.

    Standard full-size: 10 x 10 x 55 mm with 2mm deep V-notch or
    5mm deep U-notch.  Sub-size specimens: 10 x 7.5, 10 x 5, 10 x 2.5.

    Attributes
    ----------
    notch_type : str
        'V' (Charpy V-notch, 45deg, 0.25mm radius) or
        'U' (Charpy U-notch, 5mm deep, 1mm radius)
    width : float
        Specimen width in mm (10 for full-size)
    height : float
        Specimen height in mm (10, 7.5, 5, or 2.5)
    length : float
        Specimen length in mm (55 standard)
    notch_depth : float
        Notch depth in mm (2 for V-notch, 5 for U-notch)
    """
    notch_type: str = "V"
    width: float = 10.0
    height: float = 10.0
    length: float = 55.0
    notch_depth: float = 2.0

    @property
    def is_subsize(self) -> bool:
        """True if specimen is sub-size (height < 10 mm)."""
        return self.height < 10.0

    @property
    def designation(self) -> str:
        """Specimen designation string, e.g. 'CVN 10x10' or 'CVN 10x7.5'."""
        h = f'{self.height:g}'
        return f'C{"V" if self.notch_type == "V" else "U"}N {self.width:g}x{h}'

    @property
    def ligament(self) -> float:
        """Ligament dimension (height - notch depth) in mm."""
        return self.height - self.notch_depth


@dataclass
class CharpyTestData:
    """
    Complete Charpy impact test data for a set of specimens.

    Attributes
    ----------
    readings : List[CharpyReading]
        List of impact test readings (typically 3 per temperature)
    specimen_config : CharpySpecimenConfig
        Specimen geometry and notch configuration
    test_temperature : float
        Test temperature in degrees Celsius
    specimen_id : str
        Specimen set identifier
    material : str
        Material description
    specimen_orientation : str
        Notch orientation (e.g. 'L-T', 'T-L', 'L-S')
    """
    readings: List[CharpyReading] = field(default_factory=list)
    specimen_config: Optional[CharpySpecimenConfig] = None
    test_temperature: float = 23.0
    specimen_id: str = ""
    material: str = ""
    specimen_orientation: str = ""

    @property
    def energy_values(self) -> np.ndarray:
        """Return array of absorbed energy values."""
        return np.array([r.absorbed_energy for r in self.readings])

    @property
    def lateral_expansion_values(self) -> np.ndarray:
        """Return array of lateral expansion values (excluding None)."""
        vals = [r.lateral_expansion for r in self.readings
                if r.lateral_expansion is not None]
        return np.array(vals) if vals else np.array([])

    @property
    def shear_area_values(self) -> np.ndarray:
        """Return array of shear fracture area values (excluding None)."""
        vals = [r.shear_fracture_area for r in self.readings
                if r.shear_fracture_area is not None]
        return np.array(vals) if vals else np.array([])

    @property
    def n_specimens(self) -> int:
        """Return number of specimens."""
        return len(self.readings)
