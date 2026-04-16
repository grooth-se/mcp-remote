"""
Brinell Hardness Test Data Models per ASTM E10.

This module provides dataclasses for Brinell hardness test specimens,
readings, and material properties.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np


@dataclass
class BrinellReading:
    """
    Single Brinell hardness reading.

    Attributes
    ----------
    reading_number : int
        Sequential reading number (1, 2, 3, ...)
    location : str
        Test location description
    hardness_value : float
        Brinell hardness value (HBW)
    indent_diameter : float, optional
        Indent diameter measurement in millimeters
    """
    reading_number: int
    location: str
    hardness_value: float
    indent_diameter: Optional[float] = None


@dataclass
class BrinellLoadLevel:
    """
    Brinell hardness load level configuration.

    Standard load levels per ASTM E10 are defined by ball diameter D
    and test force F, designated as HBW D/F.

    Attributes
    ----------
    designation : str
        Load level designation (e.g., "HBW 10/3000")
    ball_diameter : float
        Ball diameter in millimeters (1, 2.5, 5, 10)
    force_kgf : float
        Test force in kilogram-force
    """
    designation: str
    ball_diameter: float
    force_kgf: float

    @property
    def force_N(self) -> float:
        """Convert kgf to Newtons."""
        return self.force_kgf * 9.80665

    @property
    def force_factor(self) -> float:
        """Test force factor F/D² (common values: 30, 15, 10, 5, 2.5, 1)."""
        return self.force_kgf / (self.ball_diameter ** 2)

    @classmethod
    def from_designation(cls, designation: str) -> 'BrinellLoadLevel':
        """Parse designation string like 'HBW 10/3000' into a BrinellLoadLevel."""
        import re
        m = re.match(r'HBW\s*(\d+\.?\d*)\s*/\s*(\d+\.?\d*)', designation)
        if m:
            d = float(m.group(1))
            f = float(m.group(2))
            return cls(designation=f'HBW {m.group(1)}/{m.group(2)}',
                       ball_diameter=d, force_kgf=f)
        raise ValueError(f"Invalid Brinell designation: {designation}")

    @classmethod
    def get_common_levels(cls) -> List['BrinellLoadLevel']:
        """Return list of commonly used Brinell load levels per ASTM E10."""
        return [
            cls("HBW 10/3000", 10.0, 3000),
            cls("HBW 10/1500", 10.0, 1500),
            cls("HBW 5/750", 5.0, 750),
            cls("HBW 5/250", 5.0, 250),
            cls("HBW 2.5/187.5", 2.5, 187.5),
            cls("HBW 2.5/62.5", 2.5, 62.5),
            cls("HBW 1/30", 1.0, 30),
            cls("HBW 1/10", 1.0, 10),
            cls("HBW 1/1", 1.0, 1),
        ]


@dataclass
class BrinellTestData:
    """
    Complete Brinell hardness test data.

    Attributes
    ----------
    readings : List[BrinellReading]
        List of hardness readings
    load_level : BrinellLoadLevel
        Test load level
    specimen_id : str
        Specimen identifier
    material : str
        Material description
    test_date : str
        Date of test
    operator : str
        Test operator name
    photo_path : str, optional
        Path to indent photograph
    """
    readings: List[BrinellReading] = field(default_factory=list)
    load_level: Optional[BrinellLoadLevel] = None
    specimen_id: str = ""
    material: str = ""
    test_date: str = ""
    operator: str = ""
    photo_path: Optional[str] = None

    @property
    def hardness_values(self) -> np.ndarray:
        """Return array of hardness values."""
        return np.array([r.hardness_value for r in self.readings])

    @property
    def locations(self) -> List[str]:
        """Return list of test locations."""
        return [r.location for r in self.readings]

    @property
    def n_readings(self) -> int:
        """Return number of readings."""
        return len(self.readings)
