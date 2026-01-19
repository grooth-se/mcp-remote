"""
Vickers Hardness Calculations per ASTM E92 with ISO 17025 Uncertainty.

This module provides the VickersAnalyzer class for calculating Vickers
hardness statistics and uncertainty following ASTM E92 and ISO 17025.

Key Features:
    - Mean, standard deviation, and range calculations
    - Expanded uncertainty (k=2) per GUM methodology
    - ISO 17025 compliant uncertainty budget
    - Statistical analysis of hardness readings

References:
    ASTM E92 - Standard Test Methods for Vickers Hardness and
               Knoop Hardness of Metallic Materials
    ISO 6507-1 - Metallic materials - Vickers hardness test
    GUM - Guide to the Expression of Uncertainty in Measurement
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np
from scipy import stats

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.models.test_result import MeasuredValue
from utils.models.vickers_specimen import VickersTestData, VickersReading


@dataclass
class VickersResult:
    """
    Results from Vickers hardness analysis.

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
        Load level designation (e.g., "HV10")
    readings : List[VickersReading]
        Individual readings
    """
    mean_hardness: MeasuredValue
    std_dev: float
    range_value: float
    min_value: float
    max_value: float
    n_readings: int
    load_level: str
    readings: List[VickersReading] = field(default_factory=list)


class VickersAnalyzer:
    """
    Analyzer for Vickers hardness per ASTM E92 with ISO 17025 uncertainty.

    This class implements the complete analysis workflow including:
    1. Statistical analysis of hardness readings
    2. Uncertainty budget calculation per GUM
    3. ISO 17025 compliant expanded uncertainty (k=2)

    Attributes
    ----------
    machine_uncertainty : float
        Relative uncertainty of hardness testing machine (default 0.02 = 2%)
    diagonal_uncertainty : float
        Relative uncertainty in diagonal measurement (default 0.01 = 1%)
    force_uncertainty : float
        Relative uncertainty in applied force (default 0.01 = 1%)
    """

    def __init__(self,
                 machine_uncertainty: float = 0.02,
                 diagonal_uncertainty: float = 0.01,
                 force_uncertainty: float = 0.01):
        """
        Initialize Vickers analyzer with uncertainty values.

        Parameters
        ----------
        machine_uncertainty : float
            Relative uncertainty of hardness testing machine
        diagonal_uncertainty : float
            Relative uncertainty in diagonal measurement
        force_uncertainty : float
            Relative uncertainty in applied force
        """
        self.machine_uncertainty = machine_uncertainty
        self.diagonal_uncertainty = diagonal_uncertainty
        self.force_uncertainty = force_uncertainty

    def calculate_statistics(self, values: np.ndarray) -> Tuple[float, float, float, float, float]:
        """
        Calculate basic statistics for hardness values.

        Parameters
        ----------
        values : np.ndarray
            Array of hardness values

        Returns
        -------
        Tuple[float, float, float, float, float]
            (mean, std_dev, range, min, max)
        """
        mean = np.mean(values)
        std_dev = np.std(values, ddof=1) if len(values) > 1 else 0.0
        range_val = np.max(values) - np.min(values)
        min_val = np.min(values)
        max_val = np.max(values)

        return mean, std_dev, range_val, min_val, max_val

    def calculate_uncertainty(self,
                             values: np.ndarray,
                             mean: float) -> float:
        """
        Calculate combined expanded uncertainty per ISO 17025 / GUM.

        Uncertainty budget components:
        1. Type A: Standard uncertainty of the mean (repeatability)
        2. Type B: Machine uncertainty (calibration)
        3. Type B: Diagonal measurement uncertainty
        4. Type B: Force application uncertainty

        Parameters
        ----------
        values : np.ndarray
            Array of hardness values
        mean : float
            Mean hardness value

        Returns
        -------
        float
            Expanded uncertainty U (k=2)

        Notes
        -----
        Combined standard uncertainty:
        u_c = sqrt(u_A^2 + u_machine^2 + u_diagonal^2 + u_force^2)

        Expanded uncertainty (k=2):
        U = 2 * u_c
        """
        n = len(values)

        # Type A: Standard uncertainty of the mean (repeatability)
        if n > 1:
            std_dev = np.std(values, ddof=1)
            u_A = std_dev / np.sqrt(n)
        else:
            # Single reading: estimate from machine repeatability
            u_A = mean * 0.01  # 1% estimate

        # Type B: Machine uncertainty (from calibration certificate)
        # Typically 2% for calibrated hardness testers
        u_machine = mean * self.machine_uncertainty

        # Type B: Diagonal measurement uncertainty
        # HV is proportional to 1/d^2, so relative uncertainty in HV
        # is approximately 2 * relative uncertainty in diagonal
        u_diagonal = mean * (2 * self.diagonal_uncertainty)

        # Type B: Force application uncertainty
        # HV is proportional to F, so relative uncertainty transfers directly
        u_force = mean * self.force_uncertainty

        # Combined standard uncertainty
        u_combined = np.sqrt(u_A**2 + u_machine**2 + u_diagonal**2 + u_force**2)

        # Expanded uncertainty (coverage factor k=2 for ~95% confidence)
        U = 2 * u_combined

        return U

    def run_analysis(self, test_data: VickersTestData) -> VickersResult:
        """
        Run complete Vickers hardness analysis.

        Parameters
        ----------
        test_data : VickersTestData
            Complete test data with readings and load level

        Returns
        -------
        VickersResult
            Complete analysis results with uncertainty
        """
        values = test_data.hardness_values

        if len(values) == 0:
            raise ValueError("No hardness readings provided")

        # Calculate statistics
        mean, std_dev, range_val, min_val, max_val = self.calculate_statistics(values)

        # Calculate uncertainty
        uncertainty = self.calculate_uncertainty(values, mean)

        # Create MeasuredValue for mean hardness
        load_designation = test_data.load_level.designation if test_data.load_level else "HV"
        mean_hardness = MeasuredValue(
            value=round(mean, 1),
            uncertainty=round(uncertainty, 1),
            unit=load_designation,
            coverage_factor=2.0
        )

        return VickersResult(
            mean_hardness=mean_hardness,
            std_dev=round(std_dev, 1),
            range_value=round(range_val, 1),
            min_value=round(min_val, 1),
            max_value=round(max_val, 1),
            n_readings=len(values),
            load_level=load_designation,
            readings=test_data.readings
        )

    def get_uncertainty_budget(self,
                               values: np.ndarray,
                               mean: float) -> dict:
        """
        Get detailed uncertainty budget breakdown.

        Parameters
        ----------
        values : np.ndarray
            Array of hardness values
        mean : float
            Mean hardness value

        Returns
        -------
        dict
            Dictionary with uncertainty components:
            - u_A: Type A (repeatability)
            - u_machine: Machine uncertainty
            - u_diagonal: Diagonal measurement uncertainty
            - u_force: Force uncertainty
            - u_combined: Combined standard uncertainty
            - U_expanded: Expanded uncertainty (k=2)
        """
        n = len(values)

        # Type A
        if n > 1:
            std_dev = np.std(values, ddof=1)
            u_A = std_dev / np.sqrt(n)
        else:
            u_A = mean * 0.01

        # Type B components
        u_machine = mean * self.machine_uncertainty
        u_diagonal = mean * (2 * self.diagonal_uncertainty)
        u_force = mean * self.force_uncertainty

        # Combined
        u_combined = np.sqrt(u_A**2 + u_machine**2 + u_diagonal**2 + u_force**2)
        U_expanded = 2 * u_combined

        return {
            'u_A': round(u_A, 2),
            'u_machine': round(u_machine, 2),
            'u_diagonal': round(u_diagonal, 2),
            'u_force': round(u_force, 2),
            'u_combined': round(u_combined, 2),
            'U_expanded': round(U_expanded, 2),
            'k': 2,
            'n_readings': n
        }
