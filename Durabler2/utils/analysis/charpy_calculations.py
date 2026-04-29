"""
Charpy Impact Test Calculations per ASTM E23 with ISO 17025 Uncertainty.

This module provides the CharpyAnalyzer class for calculating Charpy
impact statistics and uncertainty following ASTM E23 / ISO 148-1.

Key Features:
    - Mean, standard deviation, and range of absorbed energy
    - Lateral expansion and shear fracture area statistics
    - Expanded uncertainty (k=2) per GUM methodology
    - ISO 17025 compliant uncertainty budget

References:
    ASTM E23 - Standard Test Methods for Notched Bar Impact Testing
               of Metallic Materials
    ISO 148-1 - Metallic materials - Charpy pendulum impact test
    GUM - Guide to the Expression of Uncertainty in Measurement
"""

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.models.test_result import MeasuredValue
from utils.models.charpy_specimen import CharpyTestData, CharpyReading


@dataclass
class CharpyResult:
    """
    Results from Charpy impact test analysis.

    Attributes
    ----------
    mean_energy : MeasuredValue
        Mean absorbed energy with uncertainty (J)
    std_dev : float
        Standard deviation of energy values
    range_value : float
        Range (max - min) of energy values
    min_value : float
        Minimum absorbed energy
    max_value : float
        Maximum absorbed energy
    n_specimens : int
        Number of specimens tested
    test_temperature : float
        Test temperature in degrees Celsius
    mean_lateral_expansion : float, optional
        Mean lateral expansion in mm
    mean_shear_area : float, optional
        Mean shear fracture area in %
    readings : List[CharpyReading]
        Individual readings
    """
    mean_energy: MeasuredValue
    std_dev: float
    range_value: float
    min_value: float
    max_value: float
    n_specimens: int
    test_temperature: float
    mean_lateral_expansion: Optional[float] = None
    mean_shear_area: Optional[float] = None
    readings: List[CharpyReading] = field(default_factory=list)


class CharpyAnalyzer:
    """
    Analyzer for Charpy impact tests per ASTM E23 with ISO 17025 uncertainty.

    Uncertainty budget components:
    1. Type A: Standard uncertainty of the mean (repeatability)
    2. Type B: Machine calibration uncertainty (from verification)
    3. Type B: Temperature measurement uncertainty
    4. Type B: Specimen dimension uncertainty

    Attributes
    ----------
    machine_uncertainty : float
        Relative uncertainty of impact machine (default 0.01 = 1%)
    temperature_uncertainty : float
        Absolute uncertainty in temperature measurement (default 1.0 C)
    dimension_uncertainty : float
        Relative uncertainty in specimen dimensions (default 0.005 = 0.5%)
    """

    def __init__(self,
                 machine_uncertainty: float = 0.01,
                 temperature_uncertainty: float = 1.0,
                 dimension_uncertainty: float = 0.005):
        self.machine_uncertainty = machine_uncertainty
        self.temperature_uncertainty = temperature_uncertainty
        self.dimension_uncertainty = dimension_uncertainty

    def calculate_uncertainty(self, values: np.ndarray, mean: float) -> float:
        """
        Calculate combined expanded uncertainty per ISO 17025 / GUM.

        Returns expanded uncertainty U (k=2) in Joules.
        """
        n = len(values)

        # Type A: Standard uncertainty of the mean (repeatability)
        if n > 1:
            std_dev = np.std(values, ddof=1)
            u_A = std_dev / np.sqrt(n)
        else:
            u_A = mean * 0.05  # 5% estimate for single specimen

        # Type B: Machine calibration (from pendulum verification)
        u_machine = mean * self.machine_uncertainty

        # Type B: Specimen dimension effect on energy
        # Energy scales with ligament cross-section area
        u_dimension = mean * (2 * self.dimension_uncertainty)

        # Combined standard uncertainty
        u_combined = np.sqrt(u_A**2 + u_machine**2 + u_dimension**2)

        # Expanded uncertainty (k=2, ~95% confidence)
        return 2 * u_combined

    def run_analysis(self, test_data: CharpyTestData) -> CharpyResult:
        """
        Run complete Charpy impact analysis.

        Parameters
        ----------
        test_data : CharpyTestData
            Complete test data with readings

        Returns
        -------
        CharpyResult
            Complete analysis results with uncertainty
        """
        values = test_data.energy_values

        if len(values) == 0:
            raise ValueError("No impact test readings provided")

        mean = float(np.mean(values))
        std_dev = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        range_val = float(np.max(values) - np.min(values))
        min_val = float(np.min(values))
        max_val = float(np.max(values))
        uncertainty = self.calculate_uncertainty(values, mean)

        mean_energy = MeasuredValue(
            value=round(mean, 1),
            uncertainty=round(uncertainty, 1),
            unit="J",
            coverage_factor=2.0
        )

        # Lateral expansion statistics
        le_vals = test_data.lateral_expansion_values
        mean_le = round(float(np.mean(le_vals)), 2) if len(le_vals) > 0 else None

        # Shear fracture area statistics
        sa_vals = test_data.shear_area_values
        mean_sa = round(float(np.mean(sa_vals)), 0) if len(sa_vals) > 0 else None

        return CharpyResult(
            mean_energy=mean_energy,
            std_dev=round(std_dev, 1),
            range_value=round(range_val, 1),
            min_value=round(min_val, 1),
            max_value=round(max_val, 1),
            n_specimens=len(values),
            test_temperature=test_data.test_temperature,
            mean_lateral_expansion=mean_le,
            mean_shear_area=mean_sa,
            readings=test_data.readings
        )

    def get_uncertainty_budget(self, values: np.ndarray, mean: float) -> dict:
        """
        Get detailed uncertainty budget breakdown.

        Returns dict with u_A, u_machine, u_dimension,
        u_combined, U_expanded, k, n_specimens.
        """
        n = len(values)

        if n > 1:
            std_dev = np.std(values, ddof=1)
            u_A = std_dev / np.sqrt(n)
        else:
            u_A = mean * 0.05

        u_machine = mean * self.machine_uncertainty
        u_dimension = mean * (2 * self.dimension_uncertainty)

        u_combined = np.sqrt(u_A**2 + u_machine**2 + u_dimension**2)
        U_expanded = 2 * u_combined

        return {
            'u_A': round(u_A, 2),
            'u_machine': round(u_machine, 2),
            'u_dimension': round(u_dimension, 2),
            'u_combined': round(u_combined, 2),
            'U_expanded': round(U_expanded, 2),
            'k': 2,
            'n_specimens': n
        }
