"""
KIC Fracture Toughness Calculations per ASTM E399.

This module provides the KICAnalyzer class for calculating plane-strain
fracture toughness (KIC) from load-displacement test data following
ASTM E399 standard.

Key Features:
    - 5% secant offset method for PQ determination
    - Stress intensity factor calculation for SE(B) and C(T) specimens
    - ASTM E399 validity checks
    - Uncertainty propagation using GUM methodology

References:
    ASTM E399 - Standard Test Method for Linear-Elastic Plane-Strain
    Fracture Toughness of Metallic Materials
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import numpy as np
from scipy import stats
from scipy.optimize import brentq

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.models.test_result import MeasuredValue
from utils.models.kic_specimen import KICSpecimen, KICMaterial


@dataclass
class KICResult:
    """
    Results from KIC fracture toughness analysis.

    Attributes
    ----------
    P_max : MeasuredValue
        Maximum load in kN
    P_Q : MeasuredValue
        Conditional load PQ in kN (from 5% secant offset)
    K_Q : MeasuredValue
        Conditional fracture toughness in MPa*sqrt(m)
    K_IC : MeasuredValue or None
        Valid plane-strain fracture toughness (None if invalid)
    P_ratio : float
        Pmax/PQ ratio
    compliance : float
        Initial elastic compliance in mm/kN
    r_squared : float
        R-squared value from compliance linear fit
    is_valid : bool
        True if KIC is valid per ASTM E399
    validity_notes : List[str]
        Detailed validity check results
    """
    P_max: MeasuredValue
    P_Q: MeasuredValue
    K_Q: MeasuredValue
    K_IC: Optional[MeasuredValue]
    P_ratio: float
    compliance: float
    r_squared: float
    is_valid: bool
    validity_notes: List[str] = field(default_factory=list)


class KICAnalyzer:
    """
    Analyzer for KIC fracture toughness per ASTM E399.

    This class implements the complete analysis workflow including:
    1. Initial compliance determination
    2. 5% secant offset method for PQ
    3. KQ calculation
    4. Validity checks
    5. Uncertainty propagation

    Attributes
    ----------
    force_uncertainty : float
        Relative uncertainty in force measurement (default 0.01 = 1%)
    disp_uncertainty : float
        Relative uncertainty in displacement measurement (default 0.01 = 1%)
    dim_uncertainty : float
        Relative uncertainty in dimensions (default 0.005 = 0.5%)
    """

    def __init__(self,
                 force_uncertainty: float = 0.01,
                 disp_uncertainty: float = 0.01,
                 dim_uncertainty: float = 0.005):
        """
        Initialize KIC analyzer with uncertainty values.

        Parameters
        ----------
        force_uncertainty : float
            Relative uncertainty in force measurement
        disp_uncertainty : float
            Relative uncertainty in displacement measurement
        dim_uncertainty : float
            Relative uncertainty in specimen dimensions
        """
        self.force_uncertainty = force_uncertainty
        self.disp_uncertainty = disp_uncertainty
        self.dim_uncertainty = dim_uncertainty

    def calculate_compliance(self,
                            force: np.ndarray,
                            displacement: np.ndarray,
                            lower_frac: float = 0.0,
                            upper_frac: float = 0.30) -> Tuple[float, float, float]:
        """
        Calculate initial elastic compliance from load-displacement curve.

        Uses linear regression on the initial linear portion of the curve.
        The displacement is zeroed (offset removed) before fitting.

        Per ASTM E399, the compliance should be determined from the initial
        linear elastic portion of the load-displacement record. Using 0-30%
        of Pmax provides a wider range for more accurate determination of
        the elastic compliance line.

        Parameters
        ----------
        force : np.ndarray
            Force array in kN
        displacement : np.ndarray
            Displacement array in mm
        lower_frac : float
            Lower bound of force range as fraction of Pmax (default 0.0)
        upper_frac : float
            Upper bound of force range as fraction of Pmax (default 0.30)

        Returns
        -------
        Tuple[float, float, float]
            (compliance in mm/kN, displacement offset in mm, R-squared value)
        """
        P_max = np.max(force)

        # Zero the displacement by subtracting the initial offset
        disp_offset = np.min(displacement)
        disp_zeroed = displacement - disp_offset

        # Calculate compliance from the initial linear portion of the curve
        # Use 0-30% of Pmax for more accurate elastic compliance determination
        P_lower = P_max * lower_frac
        P_upper = P_max * upper_frac

        mask = (force >= P_lower) & (force <= P_upper)

        if np.sum(mask) < 10:
            # Fall back to first 10% of data points
            n_points = max(10, len(force) // 10)
            mask = np.zeros(len(force), dtype=bool)
            mask[:n_points] = True

        P_linear = force[mask]
        v_linear = disp_zeroed[mask]

        # Linear regression: v = C * P + v0
        slope, intercept, r_value, p_value, std_err = stats.linregress(P_linear, v_linear)
        r_squared = r_value**2
        best_compliance = slope if slope > 0 else 0.01

        # Store the displacement offset for plotting
        self._disp_offset = disp_offset

        return best_compliance, disp_offset, r_squared

    def determine_PQ_secant_offset(self,
                                    force: np.ndarray,
                                    displacement: np.ndarray,
                                    compliance: float,
                                    disp_offset: float = 0.0) -> Tuple[float, int]:
        """
        Determine PQ using the 5% secant offset method per ASTM E399.

        The 5% secant line has slope 0.95 times the initial compliance slope
        (i.e., compliance increased by 5%).

        Parameters
        ----------
        force : np.ndarray
            Force array in kN
        displacement : np.ndarray
            Displacement array in mm
        compliance : float
            Initial elastic compliance in mm/kN
        disp_offset : float
            Displacement offset to subtract (seating, etc.)

        Returns
        -------
        Tuple[float, int]
            (PQ value in kN, index in array)

        Notes
        -----
        The 5% secant line: v = 1.05 * C * P (from zeroed origin)
        We find the intersection of this line with the load-displacement curve.

        If the 5% offset line doesn't intersect the curve before Pmax,
        then PQ = Pmax.
        """
        # Zero the displacement
        disp_zeroed = displacement - disp_offset

        # 5% offset compliance
        C_5 = compliance * 1.05

        # Find Pmax
        P_max = np.max(force)
        idx_max = np.argmax(force)

        # Look for intersection: curve crosses the 5% secant line
        # Secant line (from origin): v_secant = C_5 * P
        # Find where: disp_zeroed > C_5 * force (curve is to the right of secant)

        # Calculate the 5% secant displacement for each force value
        v_secant = C_5 * force

        # Find where the actual displacement exceeds the secant line
        diff = disp_zeroed - v_secant

        # Start from a point after initial noise (2% of data or 50 points)
        start_idx = max(50, len(force) // 50)

        P_Q = P_max
        idx_Q = idx_max

        # Find first point where diff becomes positive (curve crosses secant)
        # and force is above 10% of P_max
        for i in range(start_idx, idx_max):
            if diff[i] > 0 and force[i] > 0.1 * P_max:
                # Interpolate to find exact crossing
                if i > 0 and diff[i-1] <= 0:
                    # Linear interpolation between i-1 and i
                    frac = -diff[i-1] / (diff[i] - diff[i-1])
                    P_Q = force[i-1] + frac * (force[i] - force[i-1])
                    idx_Q = i
                else:
                    P_Q = force[i]
                    idx_Q = i
                break

        # Store for use in plotting
        self._disp_zeroed = disp_zeroed

        return P_Q, idx_Q

    def calculate_KQ(self,
                     P_Q: float,
                     specimen: KICSpecimen) -> float:
        """
        Calculate conditional fracture toughness KQ.

        Parameters
        ----------
        P_Q : float
            Conditional load PQ in kN
        specimen : KICSpecimen
            Specimen geometry object

        Returns
        -------
        float
            KQ in MPa*sqrt(m)
        """
        return specimen.calculate_K(P_Q)

    def check_pmax_pq_ratio(self, P_max: float, P_Q: float) -> Tuple[bool, str]:
        """
        Check if Pmax/PQ ratio meets ASTM E399 requirement.

        Parameters
        ----------
        P_max : float
            Maximum force in kN
        P_Q : float
            Conditional load in kN

        Returns
        -------
        Tuple[bool, str]
            (passes check, description string)

        Notes
        -----
        ASTM E399 requires Pmax/PQ <= 1.10 for valid KIC.
        """
        ratio = P_max / P_Q if P_Q > 0 else float('inf')

        if ratio <= 1.10:
            return True, f"P_max/P_Q = {ratio:.3f} <= 1.10: PASS"
        else:
            return False, f"P_max/P_Q = {ratio:.3f} > 1.10: FAIL"

    def check_geometry(self, specimen: KICSpecimen) -> Tuple[bool, List[str]]:
        """
        Check specimen geometry requirements per ASTM E399.

        Parameters
        ----------
        specimen : KICSpecimen
            Specimen geometry object

        Returns
        -------
        Tuple[bool, List[str]]
            (passes all checks, list of check results)
        """
        checks = []
        is_valid = True

        # a/W ratio check (0.45 to 0.55)
        a_W = specimen.a_W_ratio
        if 0.45 <= a_W <= 0.55:
            checks.append(f"a/W = {a_W:.3f} (0.45-0.55): PASS")
        else:
            checks.append(f"a/W = {a_W:.3f} (0.45-0.55): FAIL")
            is_valid = False

        # S/W ratio for SE(B) (should be ~4.0)
        if specimen.specimen_type == 'SE(B)':
            S_W = specimen.S_W_ratio
            if 3.8 <= S_W <= 4.2:
                checks.append(f"S/W = {S_W:.2f} (~4.0): PASS")
            else:
                checks.append(f"S/W = {S_W:.2f} (~4.0): WARNING")
                # This is a warning, not a failure

        return is_valid, checks

    def calculate_uncertainty_K(self,
                                K: float,
                                specimen: KICSpecimen,
                                force_rel_unc: float = None) -> float:
        """
        Calculate combined uncertainty in K.

        Parameters
        ----------
        K : float
            Stress intensity factor value
        specimen : KICSpecimen
            Specimen geometry object
        force_rel_unc : float, optional
            Relative uncertainty in force (default uses analyzer setting)

        Returns
        -------
        float
            Combined standard uncertainty in K (same units as K)

        Notes
        -----
        Uncertainty sources:
        - Force measurement
        - Specimen dimensions (B, W, a, S)
        - Geometry function f(a/W)
        """
        if force_rel_unc is None:
            force_rel_unc = self.force_uncertainty

        # Relative uncertainties
        u_P = force_rel_unc          # Force
        u_B = self.dim_uncertainty   # Thickness
        u_W = self.dim_uncertainty   # Width
        u_a = self.dim_uncertainty   # Crack length
        u_S = self.dim_uncertainty   # Span (for SE(B))

        # Sensitivity coefficients for K = f(P, B, W, a, S)
        # Approximate using relative uncertainties

        if specimen.specimen_type == 'SE(B)':
            # K = (P*S)/(B*W^1.5) * f(a/W)
            # Relative sensitivities:
            # dK/K = dP/P + dS/S + dB/B + 1.5*dW/W + df/f
            # Assume df/f ~ 2*da/a (approximate)
            u_rel_squared = (u_P**2 + u_S**2 + u_B**2 +
                           (1.5 * u_W)**2 + (2 * u_a)**2)
        else:  # C(T)
            # K = P/(B*W^0.5) * f(a/W)
            u_rel_squared = (u_P**2 + u_B**2 +
                           (0.5 * u_W)**2 + (2 * u_a)**2)

        u_rel = np.sqrt(u_rel_squared)

        # Standard uncertainty
        u_K = K * u_rel

        # Return expanded uncertainty (k=2)
        return u_K * 2

    def run_analysis(self,
                     force: np.ndarray,
                     displacement: np.ndarray,
                     specimen: KICSpecimen,
                     material: KICMaterial) -> KICResult:
        """
        Run complete KIC analysis per ASTM E399.

        Parameters
        ----------
        force : np.ndarray
            Force array in kN
        displacement : np.ndarray
            Displacement array in mm
        specimen : KICSpecimen
            Specimen geometry object
        material : KICMaterial
            Material properties object

        Returns
        -------
        KICResult
            Complete analysis results with validity assessment
        """
        validity_notes = []

        # Step 1: Calculate initial compliance
        compliance, disp_offset, r_squared = self.calculate_compliance(force, displacement)
        validity_notes.append(f"Compliance = {compliance:.5f} mm/kN")

        # Step 2: Find Pmax
        P_max_val = float(np.max(force))
        P_max_unc = P_max_val * self.force_uncertainty * 2  # k=2
        P_max = MeasuredValue(
            value=P_max_val,
            uncertainty=P_max_unc,
            unit="kN"
        )

        # Step 3: Determine PQ using 5% secant offset
        P_Q_val, idx_Q = self.determine_PQ_secant_offset(force, displacement, compliance, disp_offset)
        P_Q_unc = P_Q_val * self.force_uncertainty * 2
        P_Q = MeasuredValue(
            value=P_Q_val,
            uncertainty=P_Q_unc,
            unit="kN"
        )

        # Step 4: Calculate Pmax/PQ ratio
        P_ratio = P_max_val / P_Q_val if P_Q_val > 0 else float('inf')

        # Step 5: Calculate KQ
        K_Q_val = self.calculate_KQ(P_Q_val, specimen)
        K_Q_unc = self.calculate_uncertainty_K(K_Q_val, specimen)
        K_Q = MeasuredValue(
            value=K_Q_val,
            uncertainty=K_Q_unc,
            unit="MPa*sqrt(m)"
        )

        # Step 6: Validity checks
        is_valid = True

        # Check 1: Geometry (a/W ratio)
        geom_valid, geom_checks = self.check_geometry(specimen)
        validity_notes.extend(geom_checks)
        if not geom_valid:
            is_valid = False

        # Check 2: Pmax/PQ ratio
        ratio_valid, ratio_check = self.check_pmax_pq_ratio(P_max_val, P_Q_val)
        validity_notes.append(ratio_check)
        if not ratio_valid:
            is_valid = False

        # Check 3: Plane-strain requirements
        ps_valid, ps_checks = specimen.validate_plane_strain(K_Q_val, material.yield_strength)
        validity_notes.extend(ps_checks)
        if not ps_valid:
            is_valid = False

        # Step 7: Determine final KIC
        K_IC = None
        if is_valid:
            K_IC = MeasuredValue(
                value=K_Q_val,
                uncertainty=K_Q_unc,
                unit="MPa*sqrt(m)"
            )
            validity_notes.append("KIC = KQ (VALID per ASTM E399)")
        else:
            validity_notes.append("KIC is CONDITIONAL (validity requirements not met)")

        return KICResult(
            P_max=P_max,
            P_Q=P_Q,
            K_Q=K_Q,
            K_IC=K_IC,
            P_ratio=P_ratio,
            compliance=compliance,
            r_squared=r_squared,
            is_valid=is_valid,
            validity_notes=validity_notes
        )

    def get_plot_data(self,
                      force: np.ndarray,
                      displacement: np.ndarray,
                      result: KICResult) -> dict:
        """
        Get data for plotting the analysis results.

        Parameters
        ----------
        force : np.ndarray
            Force array in kN
        displacement : np.ndarray
            Displacement array in mm
        result : KICResult
            Analysis results

        Returns
        -------
        dict
            Dictionary with plot data:
            - 'force': original force array
            - 'displacement': zeroed displacement array
            - 'elastic_line_x': x values for elastic compliance line
            - 'elastic_line_y': y values for elastic compliance line
            - 'secant_line_x': x values for 5% secant offset line
            - 'secant_line_y': y values for 5% secant offset line
            - 'P_Q_point': (x, y) for PQ point
            - 'P_max_point': (x, y) for Pmax point
        """
        P_max = result.P_max.value
        compliance = result.compliance

        # Zero the displacement (use stored offset if available)
        disp_offset = getattr(self, '_disp_offset', np.min(displacement))
        disp_zeroed = displacement - disp_offset

        # Get max displacement for line extent
        v_max = np.max(disp_zeroed) * 1.1

        # Elastic compliance line from origin: v = C * P, so P = v / C
        elastic_x = np.array([0, v_max])
        elastic_y = np.array([0, v_max / compliance])

        # 5% secant offset line from origin: v = C_5 * P, so P = v / C_5
        C_5 = compliance * 1.05
        secant_x = np.array([0, v_max])
        secant_y = np.array([0, v_max / C_5])

        # Limit the lines to reasonable force range
        max_line_force = P_max * 1.05
        elastic_y = np.clip(elastic_y, 0, max_line_force)
        elastic_x = compliance * elastic_y  # Recalculate x based on clipped y

        secant_y = np.clip(secant_y, 0, max_line_force)
        secant_x = C_5 * secant_y  # Recalculate x based on clipped y

        # PQ point - find actual displacement at PQ on the zeroed curve
        P_Q_val = result.P_Q.value
        idx_Q = np.argmin(np.abs(force - P_Q_val))
        v_Q = disp_zeroed[idx_Q]

        # Pmax point
        idx_max = np.argmax(force)
        v_max_point = disp_zeroed[idx_max]

        return {
            'force': force,
            'displacement': disp_zeroed,
            'elastic_line_x': elastic_x,
            'elastic_line_y': elastic_y,
            'secant_line_x': secant_x,
            'secant_line_y': secant_y,
            'P_Q_point': (v_Q, P_Q_val),
            'P_max_point': (v_max_point, P_max)
        }
