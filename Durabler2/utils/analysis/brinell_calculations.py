"""
Brinell Hardness Calculations per ASTM E10 with ISO 17025 Uncertainty.

This module provides the BrinellAnalyzer class for calculating Brinell
hardness statistics and uncertainty following ASTM E10 and ISO 17025.

Key Features:
    - Mean, standard deviation, and range calculations
    - Expanded uncertainty (k=2) per GUM methodology
    - ISO 17025 compliant uncertainty budget
    - Statistical analysis of hardness readings

References:
    ASTM E10 - Standard Test Method for Brinell Hardness of Metallic Materials
    ISO 6506-1 - Metallic materials - Brinell hardness test
    GUM - Guide to the Expression of Uncertainty in Measurement
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.models.test_result import MeasuredValue
from utils.models.brinell_specimen import BrinellTestData, BrinellReading


@dataclass
class BrinellResult:
    """
    Results from Brinell hardness analysis.

    Attributes
    ----------
    mean_hardness : MeasuredValue
        Mean hardness value with uncertainty
    std_dev : float
        Standard deviation of readings
    range_value : float
        Range (max - min) of readings
    min_value : float
        Minimum hardness value
    max_value : float
        Maximum hardness value
    n_readings : int
        Number of readings
    load_level : str
        Load level designation (e.g., "HBW 10/3000")
    ball_diameter : float
        Ball diameter in mm
    readings : List[BrinellReading]
        Individual readings
    """
    mean_hardness: MeasuredValue
    std_dev: float
    range_value: float
    min_value: float
    max_value: float
    n_readings: int
    load_level: str
    ball_diameter: float = 10.0
    readings: List[BrinellReading] = field(default_factory=list)


class BrinellAnalyzer:
    """
    Analyzer for Brinell hardness per ASTM E10 with ISO 17025 uncertainty.

    Uncertainty budget components:
    1. Type A: Standard uncertainty of the mean (repeatability)
    2. Type B: Machine uncertainty (calibration)
    3. Type B: Indent diameter measurement uncertainty
    4. Type B: Force application uncertainty

    Attributes
    ----------
    machine_uncertainty : float
        Relative uncertainty of hardness testing machine (default 0.002 = 0.2%)
    diameter_uncertainty : float
        Relative uncertainty in indent diameter measurement (default 0.005 = 0.5%)
    force_uncertainty : float
        Relative uncertainty in applied force (default 0.0031 = 0.31%)
    """

    def __init__(self,
                 machine_uncertainty: float = 0.002,
                 diameter_uncertainty: float = 0.005,
                 force_uncertainty: float = 0.0031):
        self.machine_uncertainty = machine_uncertainty
        self.diameter_uncertainty = diameter_uncertainty
        self.force_uncertainty = force_uncertainty

    def calculate_statistics(self, values: np.ndarray) -> Tuple[float, float, float, float, float]:
        """
        Calculate basic statistics for hardness values.

        Returns (mean, std_dev, range, min, max).
        """
        mean = np.mean(values)
        std_dev = np.std(values, ddof=1) if len(values) > 1 else 0.0
        range_val = np.max(values) - np.min(values)
        min_val = np.min(values)
        max_val = np.max(values)
        return mean, std_dev, range_val, min_val, max_val

    def calculate_uncertainty(self, values: np.ndarray, mean: float) -> float:
        """
        Calculate combined expanded uncertainty per ISO 17025 / GUM.

        The Brinell formula HBW = 2F / (pi*D*(D - sqrt(D²-d²))) depends
        strongly on indent diameter d. The sensitivity coefficient for d
        is approximately 2× relative (similar to Vickers d² dependence),
        so the same factor of 2 is used for the diameter uncertainty term.

        Returns expanded uncertainty U (k=2).
        """
        n = len(values)

        # Type A: Standard uncertainty of the mean (repeatability)
        if n > 1:
            std_dev = np.std(values, ddof=1)
            u_A = std_dev / np.sqrt(n)
        else:
            u_A = mean * 0.01

        # Type B: Machine uncertainty (from calibration certificate)
        u_machine = mean * self.machine_uncertainty

        # Type B: Indent diameter measurement uncertainty
        # HBW has strong dependence on indent diameter (~2× relative)
        u_diameter = mean * (2 * self.diameter_uncertainty)

        # Type B: Force application uncertainty
        u_force = mean * self.force_uncertainty

        # Combined standard uncertainty
        u_combined = np.sqrt(u_A**2 + u_machine**2 + u_diameter**2 + u_force**2)

        # Expanded uncertainty (k=2, ~95% confidence)
        return 2 * u_combined

    def run_analysis(self, test_data: BrinellTestData) -> BrinellResult:
        """
        Run complete Brinell hardness analysis.

        Parameters
        ----------
        test_data : BrinellTestData
            Complete test data with readings and load level

        Returns
        -------
        BrinellResult
            Complete analysis results with uncertainty
        """
        values = test_data.hardness_values

        if len(values) == 0:
            raise ValueError("No hardness readings provided")

        mean, std_dev, range_val, min_val, max_val = self.calculate_statistics(values)
        uncertainty = self.calculate_uncertainty(values, mean)

        load_designation = test_data.load_level.designation if test_data.load_level else "HBW"
        ball_d = test_data.load_level.ball_diameter if test_data.load_level else 10.0

        mean_hardness = MeasuredValue(
            value=round(mean, 1),
            uncertainty=round(uncertainty, 1),
            unit=load_designation,
            coverage_factor=2.0
        )

        return BrinellResult(
            mean_hardness=mean_hardness,
            std_dev=round(std_dev, 1),
            range_value=round(range_val, 1),
            min_value=round(min_val, 1),
            max_value=round(max_val, 1),
            n_readings=len(values),
            load_level=load_designation,
            ball_diameter=ball_d,
            readings=test_data.readings
        )

    def get_uncertainty_budget(self, values: np.ndarray, mean: float) -> dict:
        """
        Get detailed uncertainty budget breakdown.

        Returns dict with u_A, u_machine, u_diameter, u_force,
        u_combined, U_expanded, k, n_readings.
        """
        n = len(values)

        if n > 1:
            std_dev = np.std(values, ddof=1)
            u_A = std_dev / np.sqrt(n)
        else:
            u_A = mean * 0.01

        u_machine = mean * self.machine_uncertainty
        u_diameter = mean * (2 * self.diameter_uncertainty)
        u_force = mean * self.force_uncertainty

        u_combined = np.sqrt(u_A**2 + u_machine**2 + u_diameter**2 + u_force**2)
        U_expanded = 2 * u_combined

        return {
            'u_A': round(u_A, 2),
            'u_machine': round(u_machine, 2),
            'u_diameter': round(u_diameter, 2),
            'u_force': round(u_force, 2),
            'u_combined': round(u_combined, 2),
            'U_expanded': round(U_expanded, 2),
            'k': 2,
            'n_readings': n
        }
