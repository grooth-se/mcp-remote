"""
Vickers Hardness Test Data Models per ASTM E92.

This module provides dataclasses for Vickers hardness test specimens,
readings, and material properties.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np


@dataclass
class VickersReading:
    """
    Single Vickers hardness reading.

    Attributes
    ----------
    reading_number : int
        Sequential reading number (1, 2, 3, ...)
    location : str
        Test location description
    hardness_value : float
        Vickers hardness value (HV)
    diagonal_1 : float, optional
        First diagonal measurement in micrometers
    diagonal_2 : float, optional
        Second diagonal measurement in micrometers
    """
    reading_number: int
    location: str
    hardness_value: float
    diagonal_1: Optional[float] = None
    diagonal_2: Optional[float] = None

    @property
    def mean_diagonal(self) -> Optional[float]:
        """Calculate mean diagonal if both measurements available."""
        if self.diagonal_1 and self.diagonal_2:
            return (self.diagonal_1 + self.diagonal_2) / 2
        return None


@dataclass
class VickersLoadLevel:
    """
    Vickers hardness load level configuration.

    Standard load levels per ASTM E92:
    - HV 0.01 to HV 100 (test force in kgf)

    Attributes
    ----------
    designation : str
        Load level designation (e.g., "HV10", "HV30")
    force_kgf : float
        Test force in kilogram-force
    force_N : float
        Test force in Newtons
    """
    designation: str
    force_kgf: float

    @property
    def force_N(self) -> float:
        """Convert kgf to Newtons."""
        return self.force_kgf * 9.80665

    @classmethod
    def get_standard_levels(cls) -> List['VickersLoadLevel']:
        """Return list of standard Vickers load levels per ASTM E92."""
        return [
            cls("HV 0.01", 0.01),
            cls("HV 0.015", 0.015),
            cls("HV 0.02", 0.02),
            cls("HV 0.025", 0.025),
            cls("HV 0.05", 0.05),
            cls("HV 0.1", 0.1),
            cls("HV 0.2", 0.2),
            cls("HV 0.3", 0.3),
            cls("HV 0.5", 0.5),
            cls("HV 1", 1.0),
            cls("HV 2", 2.0),
            cls("HV 3", 3.0),
            cls("HV 5", 5.0),
            cls("HV 10", 10.0),
            cls("HV 20", 20.0),
            cls("HV 30", 30.0),
            cls("HV 50", 50.0),
            cls("HV 100", 100.0),
        ]

    @classmethod
    def get_common_levels(cls) -> List['VickersLoadLevel']:
        """Return list of commonly used Vickers load levels."""
        return [
            cls("HV 1", 1.0),
            cls("HV 5", 5.0),
            cls("HV 10", 10.0),
            cls("HV 30", 30.0),
            cls("HV 50", 50.0),
            cls("HV 100", 100.0),
        ]


@dataclass
class VickersTestData:
    """
    Complete Vickers hardness test data.

    Attributes
    ----------
    readings : List[VickersReading]
        List of hardness readings
    load_level : VickersLoadLevel
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
    readings: List[VickersReading] = field(default_factory=list)
    load_level: Optional[VickersLoadLevel] = None
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
