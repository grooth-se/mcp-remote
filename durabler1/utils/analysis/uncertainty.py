"""
Uncertainty propagation following GUM (Guide to Expression of Uncertainty in Measurement).

This module implements Type A and Type B uncertainty evaluation methods
for ISO 17025 compliant measurement uncertainty calculations.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from scipy import stats


@dataclass
class UncertaintyComponent:
    """
    A single uncertainty component in an uncertainty budget.

    Parameters
    ----------
    name : str
        Name/description of the uncertainty source
    value : float
        Standard uncertainty u
    type : str
        'A' (statistical) or 'B' (other knowledge)
    distribution : str
        'normal', 'rectangular', 'triangular'
    sensitivity_coefficient : float
        Sensitivity coefficient ci (partial derivative)
    degrees_of_freedom : int
        Degrees of freedom for this component
    source : str
        Description of the uncertainty source
    """
    name: str
    value: float
    type: str
    distribution: str
    sensitivity_coefficient: float = 1.0
    degrees_of_freedom: int = 50
    source: str = ""

    @property
    def contribution(self) -> float:
        """Variance contribution (ci * ui)^2."""
        return (self.sensitivity_coefficient * self.value) ** 2


@dataclass
class UncertaintyBudget:
    """
    Complete uncertainty budget for a measurand.

    Implements GUM methodology for combining uncertainty components
    and calculating expanded uncertainty.

    Parameters
    ----------
    measurand_name : str
        Name of the quantity being measured
    measurand_value : float
        Value of the measurand
    unit : str
        Unit of measurement
    components : List[UncertaintyComponent]
        List of uncertainty components
    """
    measurand_name: str
    measurand_value: float
    unit: str
    components: List[UncertaintyComponent] = field(default_factory=list)

    def add_type_a(
        self,
        name: str,
        values: np.ndarray,
        sensitivity: float = 1.0,
        source: str = ""
    ) -> UncertaintyComponent:
        """
        Add Type A uncertainty from repeated measurements.

        Standard uncertainty is the standard error of the mean:
        u = s / sqrt(n)

        Parameters
        ----------
        name : str
            Name of the uncertainty component
        values : np.ndarray
            Array of repeated measurements
        sensitivity : float
            Sensitivity coefficient ci
        source : str
            Description of the source

        Returns
        -------
        UncertaintyComponent
            The created component
        """
        n = len(values)
        if n < 2:
            raise ValueError("Need at least 2 measurements for Type A evaluation")

        std = np.std(values, ddof=1)
        standard_uncertainty = std / np.sqrt(n)

        component = UncertaintyComponent(
            name=name,
            value=standard_uncertainty,
            type='A',
            distribution='normal',
            sensitivity_coefficient=sensitivity,
            degrees_of_freedom=n - 1,
            source=source or f"Statistical analysis of {n} measurements"
        )
        self.components.append(component)
        return component

    def add_type_b_rectangular(
        self,
        name: str,
        half_width: float,
        sensitivity: float = 1.0,
        source: str = ""
    ) -> UncertaintyComponent:
        """
        Add Type B uncertainty with rectangular distribution.

        For specifications like "+/- a", the standard uncertainty is:
        u = a / sqrt(3)

        Parameters
        ----------
        name : str
            Name of the uncertainty component
        half_width : float
            Half-width 'a' of the rectangular distribution
        sensitivity : float
            Sensitivity coefficient ci
        source : str
            Description of the source

        Returns
        -------
        UncertaintyComponent
            The created component
        """
        standard_uncertainty = half_width / np.sqrt(3)

        component = UncertaintyComponent(
            name=name,
            value=standard_uncertainty,
            type='B',
            distribution='rectangular',
            sensitivity_coefficient=sensitivity,
            degrees_of_freedom=50,
            source=source
        )
        self.components.append(component)
        return component

    def add_type_b_triangular(
        self,
        name: str,
        half_width: float,
        sensitivity: float = 1.0,
        source: str = ""
    ) -> UncertaintyComponent:
        """
        Add Type B uncertainty with triangular distribution.

        For triangular distribution with half-width 'a':
        u = a / sqrt(6)

        Parameters
        ----------
        name : str
            Name of the uncertainty component
        half_width : float
            Half-width 'a' of the triangular distribution
        sensitivity : float
            Sensitivity coefficient ci
        source : str
            Description of the source

        Returns
        -------
        UncertaintyComponent
            The created component
        """
        standard_uncertainty = half_width / np.sqrt(6)

        component = UncertaintyComponent(
            name=name,
            value=standard_uncertainty,
            type='B',
            distribution='triangular',
            sensitivity_coefficient=sensitivity,
            degrees_of_freedom=50,
            source=source
        )
        self.components.append(component)
        return component

    def add_type_b_normal(
        self,
        name: str,
        expanded_uncertainty: float,
        coverage_factor: float = 2.0,
        sensitivity: float = 1.0,
        degrees_of_freedom: int = 50,
        source: str = ""
    ) -> UncertaintyComponent:
        """
        Add Type B uncertainty from calibration certificate (normal distribution).

        Parameters
        ----------
        name : str
            Name of the uncertainty component
        expanded_uncertainty : float
            Expanded uncertainty U from certificate
        coverage_factor : float
            Coverage factor k (usually 2 for 95%)
        sensitivity : float
            Sensitivity coefficient ci
        degrees_of_freedom : int
            Degrees of freedom (often stated on certificate)
        source : str
            Description (e.g., certificate number)

        Returns
        -------
        UncertaintyComponent
            The created component
        """
        standard_uncertainty = expanded_uncertainty / coverage_factor

        component = UncertaintyComponent(
            name=name,
            value=standard_uncertainty,
            type='B',
            distribution='normal',
            sensitivity_coefficient=sensitivity,
            degrees_of_freedom=degrees_of_freedom,
            source=source
        )
        self.components.append(component)
        return component

    @property
    def combined_standard_uncertainty(self) -> float:
        """
        Calculate combined standard uncertainty uc.

        uc^2 = sum(ci^2 * ui^2)

        Returns
        -------
        float
            Combined standard uncertainty
        """
        if not self.components:
            return 0.0

        variance_sum = sum(c.contribution for c in self.components)
        return np.sqrt(variance_sum)

    @property
    def effective_degrees_of_freedom(self) -> float:
        """
        Calculate effective degrees of freedom using Welch-Satterthwaite formula.

        nu_eff = uc^4 / sum((ci*ui)^4 / nu_i)

        Returns
        -------
        float
            Effective degrees of freedom
        """
        uc = self.combined_standard_uncertainty
        if uc == 0:
            return float('inf')

        denominator = sum(
            c.contribution ** 2 / c.degrees_of_freedom
            for c in self.components
            if c.degrees_of_freedom > 0
        )

        if denominator == 0:
            return 50.0

        return uc ** 4 / denominator

    def expanded_uncertainty(self, confidence: float = 0.95) -> tuple:
        """
        Calculate expanded uncertainty U = k * uc.

        Parameters
        ----------
        confidence : float
            Confidence level (default 0.95 = 95%)

        Returns
        -------
        tuple
            (U, k) - expanded uncertainty and coverage factor
        """
        nu_eff = self.effective_degrees_of_freedom
        uc = self.combined_standard_uncertainty

        if nu_eff == float('inf') or nu_eff > 1000:
            k = stats.norm.ppf((1 + confidence) / 2)
        else:
            k = stats.t.ppf((1 + confidence) / 2, nu_eff)

        U = k * uc
        return U, k

    def to_dict(self) -> Dict:
        """
        Export budget as dictionary for reporting.

        Returns
        -------
        dict
            Complete uncertainty budget information
        """
        U, k = self.expanded_uncertainty()

        return {
            'measurand': self.measurand_name,
            'value': self.measurand_value,
            'unit': self.unit,
            'combined_uncertainty': self.combined_standard_uncertainty,
            'expanded_uncertainty': U,
            'coverage_factor': k,
            'effective_dof': self.effective_degrees_of_freedom,
            'components': [
                {
                    'name': c.name,
                    'type': c.type,
                    'distribution': c.distribution,
                    'standard_uncertainty': c.value,
                    'sensitivity': c.sensitivity_coefficient,
                    'contribution': c.contribution,
                    'degrees_of_freedom': c.degrees_of_freedom,
                    'source': c.source
                }
                for c in self.components
            ]
        }
