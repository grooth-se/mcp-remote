"""
Test result data models with uncertainty support.

All measured values include expanded uncertainty (k=2) following
GUM (Guide to Expression of Uncertainty in Measurement) methodology.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class MeasuredValue:
    """
    A measured value with associated uncertainty (GUM compliant).

    Parameters
    ----------
    value : float
        The measured/calculated value
    uncertainty : float
        Expanded uncertainty U (k=2, 95% confidence)
    unit : str
        Unit of measurement
    coverage_factor : float
        Coverage factor k (default 2.0 for 95% confidence)
    degrees_of_freedom : int
        Effective degrees of freedom
    """
    value: float
    uncertainty: float
    unit: str
    coverage_factor: float = 2.0
    degrees_of_freedom: int = 50

    @property
    def standard_uncertainty(self) -> float:
        """Standard uncertainty u = U/k."""
        return self.uncertainty / self.coverage_factor

    @property
    def relative_uncertainty(self) -> float:
        """Relative expanded uncertainty U/value (as fraction)."""
        if self.value == 0:
            return float('inf')
        return abs(self.uncertainty / self.value)

    def __str__(self) -> str:
        """Format as value +/- uncertainty unit."""
        return f"{self.value:.4g} +/- {self.uncertainty:.2g} {self.unit}"

    def to_dict(self) -> dict:
        """Export as dictionary for reporting."""
        return {
            'value': self.value,
            'uncertainty': self.uncertainty,
            'unit': self.unit,
            'coverage_factor': self.coverage_factor,
            'degrees_of_freedom': self.degrees_of_freedom
        }


@dataclass
class TensileResult:
    """
    Complete tensile test results per ASTM E8/E8M.

    Parameters
    ----------
    specimen_id : str
        Specimen identifier
    test_date : str
        Date of test
    test_standard : str
        Reference standard (default ASTM E8/E8M-22)
    """
    specimen_id: str
    test_date: str
    test_standard: str = "ASTM E8/E8M-22"

    # Required results
    yield_strength_rp02: Optional[MeasuredValue] = None     # Rp0.2, MPa
    ultimate_tensile_strength: Optional[MeasuredValue] = None  # Rm, MPa
    youngs_modulus: Optional[MeasuredValue] = None          # E, GPa
    elongation_at_fracture: Optional[MeasuredValue] = None  # A%, %
    uniform_elongation: Optional[MeasuredValue] = None      # Ag, %
    reduction_of_area: Optional[MeasuredValue] = None       # Z%, % (round only)

    # Additional data
    fracture_location: str = ""
    validity_notes: List[str] = field(default_factory=list)
    is_valid: bool = True

    def to_dict(self) -> dict:
        """Export all results as dictionary for reporting."""
        result = {
            'specimen_id': self.specimen_id,
            'test_date': self.test_date,
            'test_standard': self.test_standard,
            'is_valid': self.is_valid,
            'validity_notes': self.validity_notes,
            'fracture_location': self.fracture_location
        }

        # Add measured values if present
        if self.yield_strength_rp02:
            result['Rp02'] = self.yield_strength_rp02.to_dict()
        if self.ultimate_tensile_strength:
            result['Rm'] = self.ultimate_tensile_strength.to_dict()
        if self.youngs_modulus:
            result['E'] = self.youngs_modulus.to_dict()
        if self.elongation_at_fracture:
            result['A_percent'] = self.elongation_at_fracture.to_dict()
        if self.uniform_elongation:
            result['Ag'] = self.uniform_elongation.to_dict()
        if self.reduction_of_area:
            result['Z_percent'] = self.reduction_of_area.to_dict()

        return result
