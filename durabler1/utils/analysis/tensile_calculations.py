"""
ASTM E8/E8M tensile test calculations with uncertainty propagation.

This module implements all calculations specified in ASTM E8/E8M-22
with full uncertainty analysis following GUM guidelines.
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Tuple, Optional
from ..models.test_result import MeasuredValue


@dataclass
class TensileAnalysisConfig:
    """
    Configuration for tensile analysis.

    Parameters
    ----------
    offset_strain : float
        Strain offset for yield strength calculation (default 0.002 = 0.2%)
    elastic_strain_range : tuple
        (min, max) strain range for modulus determination
    preload_threshold : float
        Force threshold in kN below which data is ignored
    smoothing_window : int
        Number of points for data smoothing
    force_calibration_uncertainty : float
        Relative uncertainty of force measurement (fraction)
    extensometer_uncertainty : float
        Uncertainty of extensometer in mm
    """
    offset_strain: float = 0.002
    elastic_strain_range: Tuple[float, float] = (0.0005, 0.0025)
    preload_threshold: float = 0.1
    smoothing_window: int = 5
    force_calibration_uncertainty: float = 0.005  # 0.5%
    extensometer_uncertainty: float = 0.001  # 0.001 mm


class TensileAnalyzer:
    """
    ASTM E8/E8M tensile test analyzer with uncertainty propagation.

    This class implements the calculation methods specified in ASTM E8/E8M-22
    with full uncertainty analysis following GUM guidelines.

    Parameters
    ----------
    config : TensileAnalysisConfig, optional
        Configuration options for analysis

    Examples
    --------
    >>> analyzer = TensileAnalyzer()
    >>> stress, strain = analyzer.calculate_stress_strain(force, extension, area, gauge_length)
    >>> E = analyzer.calculate_youngs_modulus(stress, strain, area_unc, gauge_length)
    """

    def __init__(self, config: Optional[TensileAnalysisConfig] = None):
        self.config = config or TensileAnalysisConfig()

    def calculate_stress_strain(
        self,
        force: np.ndarray,
        extension: np.ndarray,
        area: float,
        gauge_length: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert force-extension to engineering stress-strain.

        Parameters
        ----------
        force : np.ndarray
            Force in kN
        extension : np.ndarray
            Extensometer extension in mm
        area : float
            Original cross-sectional area in mm^2
        gauge_length : float
            Original gauge length in mm

        Returns
        -------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (dimensionless)
        """
        # Stress: sigma = F/A0, convert kN to N (x1000), result in N/mm^2 = MPa
        stress = (force * 1000) / area

        # Strain: epsilon = delta_L / L0
        strain = extension / gauge_length

        return stress, strain

    def calculate_youngs_modulus(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        area_uncertainty: float,
        gauge_length: float
    ) -> MeasuredValue:
        """
        Calculate Young's modulus E from linear portion of stress-strain curve.

        Uses linear regression on the elastic region defined by
        config.elastic_strain_range.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        area_uncertainty : float
            Uncertainty in cross-sectional area (mm^2)
        gauge_length : float
            Gauge length in mm

        Returns
        -------
        MeasuredValue
            Young's modulus with uncertainty in GPa
        """
        min_strain, max_strain = self.config.elastic_strain_range

        # Select elastic region
        mask = (strain >= min_strain) & (strain <= max_strain) & (stress > 0)

        if np.sum(mask) < 10:
            # Try wider range
            mask = (strain >= 0) & (strain <= max_strain * 2) & (stress > 0)

        if np.sum(mask) < 5:
            raise ValueError("Insufficient data points in elastic region")

        elastic_strain = strain[mask]
        elastic_stress = stress[mask]

        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            elastic_strain, elastic_stress
        )

        # E in GPa (slope is MPa/strain = MPa, divide by 1000 for GPa)
        E = slope / 1000

        # Uncertainty components:
        # 1. Regression uncertainty (from fit)
        u_regression = std_err / 1000

        # 2. Area contribution
        area_mean = np.mean(elastic_stress)
        if area_mean > 0:
            relative_area_unc = area_uncertainty / (area_mean * gauge_length / 1000)
            u_area = abs(E * relative_area_unc * 0.5)
        else:
            u_area = 0

        # 3. Extensometer uncertainty
        u_extensometer = E * self.config.extensometer_uncertainty / gauge_length

        # Combined standard uncertainty
        u_combined = np.sqrt(u_regression**2 + u_area**2 + u_extensometer**2)

        # Expanded uncertainty (k=2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(E, 1),
            uncertainty=round(U, 1),
            unit="GPa",
            coverage_factor=2.0
        )

    def calculate_yield_strength_rp02(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        E_modulus: float,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate 0.2% offset yield strength (Rp0.2) per ASTM E8.

        The offset method draws a line parallel to the elastic modulus
        line, offset by 0.2% strain. The intersection with the stress-strain
        curve defines Rp0.2.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        E_modulus : float
            Young's modulus in GPa
        area : float
            Cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area in mm^2

        Returns
        -------
        MeasuredValue
            Yield strength with uncertainty in MPa
        """
        offset = self.config.offset_strain
        E_mpa = E_modulus * 1000  # Convert GPa to MPa

        # Offset line: sigma = E * (epsilon - offset)
        # Find intersection with stress-strain curve
        offset_line = E_mpa * (strain - offset)
        curve_minus_offset = stress - offset_line

        # Find region after strain exceeds offset
        valid_idx = strain > offset * 1.5

        if not np.any(valid_idx):
            raise ValueError("Insufficient strain data for yield calculation")

        curve_segment = curve_minus_offset[valid_idx]
        strain_segment = strain[valid_idx]
        stress_segment = stress[valid_idx]

        # Find sign change (zero crossing)
        sign_changes = np.where(np.diff(np.sign(curve_segment)))[0]

        if len(sign_changes) == 0:
            # If no crossing found, use alternative method
            # Find point closest to zero
            idx = np.argmin(np.abs(curve_segment))
            yield_stress = stress_segment[idx]
        else:
            # Linear interpolation at first crossing
            idx = sign_changes[0]
            s0, s1 = strain_segment[idx], strain_segment[idx + 1]
            c0, c1 = curve_segment[idx], curve_segment[idx + 1]

            # Interpolate strain at zero crossing
            if c1 - c0 != 0:
                yield_strain = s0 - c0 * (s1 - s0) / (c1 - c0)
                yield_stress = E_mpa * (yield_strain - offset)
            else:
                yield_stress = stress_segment[idx]

        # Uncertainty calculation
        # Main contributors: area uncertainty, force uncertainty, interpolation
        u_area = yield_stress * (area_uncertainty / area)
        u_force = yield_stress * self.config.force_calibration_uncertainty

        # Interpolation uncertainty estimate
        if len(sign_changes) > 0 and idx + 1 < len(stress_segment):
            u_interpolation = abs(stress_segment[idx + 1] - stress_segment[idx]) / 4
        else:
            u_interpolation = yield_stress * 0.01

        u_combined = np.sqrt(u_area**2 + u_force**2 + u_interpolation**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(yield_stress, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_ultimate_tensile_strength(
        self,
        force: np.ndarray,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate ultimate tensile strength Rm (maximum stress).

        Rm = Fmax / A0

        Parameters
        ----------
        force : np.ndarray
            Force array in kN
        area : float
            Original cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area

        Returns
        -------
        MeasuredValue
            Ultimate tensile strength with uncertainty in MPa
        """
        F_max = np.max(force)  # kN

        # Rm in MPa (F in kN * 1000 = N, A in mm^2, N/mm^2 = MPa)
        Rm = (F_max * 1000) / area

        # Uncertainty contributors:
        # 1. Force measurement
        u_force = Rm * self.config.force_calibration_uncertainty

        # 2. Area uncertainty
        u_area = Rm * (area_uncertainty / area)

        # Combined uncertainty
        u_combined = np.sqrt(u_force**2 + u_area**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(Rm, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_elongation_at_fracture(
        self,
        extension: np.ndarray,
        force: np.ndarray,
        gauge_length: float,
        gauge_length_uncertainty: float = 0.1
    ) -> MeasuredValue:
        """
        Calculate elongation at fracture A%.

        A% = (Lf - L0) / L0 * 100

        Determined from extensometer reading at fracture point.
        Uses maximum extension as the fracture point (most reliable method
        when extensometer may be removed before complete fracture).

        Parameters
        ----------
        extension : np.ndarray
            Extensometer extension in mm
        force : np.ndarray
            Force in kN
        gauge_length : float
            Original gauge length L0 in mm
        gauge_length_uncertainty : float
            Uncertainty in gauge length

        Returns
        -------
        MeasuredValue
            Elongation at fracture with uncertainty in %
        """
        # Find maximum force position
        max_force_idx = np.argmax(force)
        max_force = force[max_force_idx]

        # Method 1: Find maximum extension (most reliable)
        # This works even if extensometer is removed before complete fracture
        max_extension_idx = np.argmax(extension)
        max_extension = extension[max_extension_idx]

        # Method 2: Find fracture by force drop (use as alternative)
        # Look for significant force drop after max force
        force_after_max = force[max_force_idx:]
        fracture_threshold = max_force * 0.3  # 30% threshold

        # Find first point where force drops below threshold AND extension is still positive
        fracture_idx = None
        for i, f in enumerate(force_after_max):
            idx = max_force_idx + i
            if f < fracture_threshold and extension[idx] > max_extension * 0.5:
                fracture_idx = idx
                break

        # Use maximum extension if no clear fracture detected
        # or if the detected fracture has lower extension
        if fracture_idx is None:
            delta_L = max_extension
        else:
            # Compare: use the larger extension value
            delta_L = max(extension[fracture_idx], max_extension)

        # Elongation percentage
        A_percent = (delta_L / gauge_length) * 100

        # Uncertainty:
        # u(A) = A * sqrt((u(dL)/dL)^2 + (u(L0)/L0)^2)
        u_extension = self.config.extensometer_uncertainty
        if abs(delta_L) > 0.001:  # Avoid division by very small numbers
            u_combined = abs(A_percent) * np.sqrt(
                (u_extension / abs(delta_L))**2 +
                (gauge_length_uncertainty / gauge_length)**2
            )
        else:
            u_combined = 0.5  # Default uncertainty

        U = 2 * u_combined

        return MeasuredValue(
            value=round(A_percent, 2),
            uncertainty=round(U, 2),
            unit="%",
            coverage_factor=2.0
        )

    def calculate_uniform_elongation(
        self,
        extension: np.ndarray,
        force: np.ndarray,
        gauge_length: float,
        gauge_length_uncertainty: float = 0.1
    ) -> MeasuredValue:
        """
        Calculate uniform elongation Ag (elongation at maximum force).

        Ag = (Lu - L0) / L0 * 100, where Lu is gauge length at Fmax.

        Parameters
        ----------
        extension : np.ndarray
            Extensometer extension in mm
        force : np.ndarray
            Force in kN
        gauge_length : float
            Original gauge length in mm
        gauge_length_uncertainty : float
            Uncertainty in gauge length

        Returns
        -------
        MeasuredValue
            Uniform elongation with uncertainty in %
        """
        max_force_idx = np.argmax(force)
        delta_L_uniform = extension[max_force_idx]

        Ag_percent = (delta_L_uniform / gauge_length) * 100

        # Uncertainty similar to A%
        u_extension = self.config.extensometer_uncertainty
        if abs(delta_L_uniform) > 0:
            u_combined = Ag_percent * np.sqrt(
                (u_extension / abs(delta_L_uniform))**2 +
                (gauge_length_uncertainty / gauge_length)**2
            )
        else:
            u_combined = 0.1

        U = 2 * u_combined

        return MeasuredValue(
            value=round(Ag_percent, 2),
            uncertainty=round(U, 2),
            unit="%",
            coverage_factor=2.0
        )

    def calculate_reduction_of_area(
        self,
        original_diameter: float,
        final_diameter: float,
        diameter_uncertainty: float = 0.01
    ) -> MeasuredValue:
        """
        Calculate reduction of area Z% (for round specimens only).

        Z% = (A0 - Af) / A0 * 100

        Parameters
        ----------
        original_diameter : float
            Original specimen diameter in mm
        final_diameter : float
            Final diameter at fracture surface in mm
        diameter_uncertainty : float
            Measurement uncertainty in diameter (mm)

        Returns
        -------
        MeasuredValue
            Reduction of area with uncertainty in %
        """
        A0 = np.pi * (original_diameter / 2)**2
        Af = np.pi * (final_diameter / 2)**2

        Z_percent = ((A0 - Af) / A0) * 100

        # Uncertainty propagation
        # Z = 100 * (1 - (df/d0)^2)
        # dZ/ddf = -200 * df / d0^2
        # dZ/dd0 = 200 * df^2 / d0^3
        ratio = final_diameter / original_diameter
        dZ_ddf = -200 * final_diameter / original_diameter**2
        dZ_dd0 = 200 * final_diameter**2 / original_diameter**3

        u_combined = np.sqrt(
            (dZ_ddf * diameter_uncertainty)**2 +
            (dZ_dd0 * diameter_uncertainty)**2
        )
        U = 2 * u_combined

        return MeasuredValue(
            value=round(Z_percent, 1),
            uncertainty=round(U, 1),
            unit="%",
            coverage_factor=2.0
        )

    def calculate_yield_strength_rp05(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        E_modulus: float,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate 0.5% offset yield strength (Rp0.5) per ASTM E8.

        Same method as Rp0.2 but with 0.5% strain offset.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        E_modulus : float
            Young's modulus in GPa
        area : float
            Cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area in mm^2

        Returns
        -------
        MeasuredValue
            Yield strength Rp0.5 with uncertainty in MPa
        """
        offset = 0.005  # 0.5%
        E_mpa = E_modulus * 1000

        offset_line = E_mpa * (strain - offset)
        curve_minus_offset = stress - offset_line

        valid_idx = strain > offset * 1.5

        if not np.any(valid_idx):
            raise ValueError("Insufficient strain data for Rp0.5 calculation")

        curve_segment = curve_minus_offset[valid_idx]
        strain_segment = strain[valid_idx]
        stress_segment = stress[valid_idx]

        sign_changes = np.where(np.diff(np.sign(curve_segment)))[0]

        if len(sign_changes) == 0:
            idx = np.argmin(np.abs(curve_segment))
            yield_stress = stress_segment[idx]
        else:
            idx = sign_changes[0]
            s0, s1 = strain_segment[idx], strain_segment[idx + 1]
            c0, c1 = curve_segment[idx], curve_segment[idx + 1]

            if c1 - c0 != 0:
                yield_strain = s0 - c0 * (s1 - s0) / (c1 - c0)
                yield_stress = E_mpa * (yield_strain - offset)
            else:
                yield_stress = stress_segment[idx]

        u_area = yield_stress * (area_uncertainty / area)
        u_force = yield_stress * self.config.force_calibration_uncertainty

        if len(sign_changes) > 0 and idx + 1 < len(stress_segment):
            u_interpolation = abs(stress_segment[idx + 1] - stress_segment[idx]) / 4
        else:
            u_interpolation = yield_stress * 0.01

        u_combined = np.sqrt(u_area**2 + u_force**2 + u_interpolation**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(yield_stress, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_true_stress_at_break(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        force: np.ndarray,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate true stress at the point of maximum force (before necking).

        True stress = Engineering stress * (1 + Engineering strain)
        σ_true = σ_eng * (1 + ε_eng)

        This is valid up to the onset of necking (uniform elongation).

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        force : np.ndarray
            Force in kN
        area : float
            Original cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area

        Returns
        -------
        MeasuredValue
            True stress at maximum force with uncertainty in MPa
        """
        max_force_idx = np.argmax(force)
        eng_stress = stress[max_force_idx]
        eng_strain = strain[max_force_idx]

        # True stress at uniform elongation (before necking)
        true_stress = eng_stress * (1 + eng_strain)

        # Uncertainty propagation
        u_stress = eng_stress * self.config.force_calibration_uncertainty
        u_strain = self.config.extensometer_uncertainty / 50.0  # Approximate

        # d(true_stress)/d(eng_stress) = (1 + eng_strain)
        # d(true_stress)/d(eng_strain) = eng_stress
        u_combined = np.sqrt(
            (u_stress * (1 + eng_strain))**2 +
            (u_strain * eng_stress)**2
        )
        U = 2 * u_combined

        return MeasuredValue(
            value=round(true_stress, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_true_stress_at_fracture(
        self,
        force: np.ndarray,
        stress: np.ndarray,
        final_diameter: float,
        final_diameter_std: float = 0.01
    ) -> MeasuredValue:
        """
        Calculate true stress at fracture for round specimens.

        True stress at fracture = F_break / A_final

        Where F_break is the force at the significant stress drop point,
        and A_final is the cross-section area calculated from final diameter df.

        Parameters
        ----------
        force : np.ndarray
            Force array in kN
        stress : np.ndarray
            Engineering stress in MPa (used to find break point)
        final_diameter : float
            Final diameter df after fracture in mm
        final_diameter_std : float
            Standard deviation of final diameter measurement in mm

        Returns
        -------
        MeasuredValue
            True stress at fracture with uncertainty in MPa
        """
        # Find break point: significant stress drop (>50% from max)
        max_stress_idx = np.argmax(stress)
        max_stress = stress[max_stress_idx]

        # Find first point after max where stress drops significantly
        break_idx = len(stress) - 1  # Default to last point
        for i in range(max_stress_idx, len(stress)):
            if stress[i] < max_stress * 0.5:
                break_idx = i
                break

        # Force at break (convert kN to N)
        force_break = force[break_idx] * 1000  # N

        # Final cross-section area from final diameter
        area_final = np.pi * (final_diameter ** 2) / 4  # mm²

        # True stress at fracture
        true_stress = force_break / area_final  # MPa (N/mm² = MPa)

        # Uncertainty propagation
        # u(σ) = σ * sqrt((u_F/F)² + (2*u_d/d)²)
        u_force = force_break * self.config.force_calibration_uncertainty
        u_diameter = final_diameter_std

        u_relative = np.sqrt(
            (u_force / force_break) ** 2 +
            (2 * u_diameter / final_diameter) ** 2
        )
        u_combined = true_stress * u_relative
        U = 2 * u_combined

        return MeasuredValue(
            value=round(true_stress, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_ludwik_parameters(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        E_modulus: float,
        Rp02: float
    ) -> Tuple[MeasuredValue, MeasuredValue]:
        """
        Calculate Ludwik's law parameters (strain hardening).

        Ludwik's equation: σ = K * ε_p^n

        Where:
        - σ is true stress
        - ε_p is true plastic strain = ε_true - σ/E
        - K is strength coefficient
        - n is strain hardening exponent

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        E_modulus : float
            Young's modulus in GPa
        Rp02 : float
            Yield strength Rp0.2 in MPa

        Returns
        -------
        tuple[MeasuredValue, MeasuredValue]
            (K, n) - strength coefficient (MPa) and strain hardening exponent
        """
        E_mpa = E_modulus * 1000

        # Convert to true stress and true strain
        true_stress = stress * (1 + strain)
        true_strain = np.log(1 + strain)

        # Plastic strain = total strain - elastic strain
        plastic_strain = true_strain - true_stress / E_mpa

        # Select plastic region: from yield to max stress
        # Use points where stress > Rp02 and plastic strain > 0
        mask = (stress > Rp02 * 1.05) & (plastic_strain > 0.001) & (plastic_strain < 0.5)

        if np.sum(mask) < 10:
            # Not enough data for reliable fit
            return (
                MeasuredValue(value=0, uncertainty=0, unit="MPa", coverage_factor=2.0),
                MeasuredValue(value=0, uncertainty=0, unit="-", coverage_factor=2.0)
            )

        # Fit log(σ) = log(K) + n * log(ε_p)
        log_stress = np.log(true_stress[mask])
        log_strain = np.log(plastic_strain[mask])

        # Remove any infinities or NaNs
        valid = np.isfinite(log_stress) & np.isfinite(log_strain)
        if np.sum(valid) < 5:
            return (
                MeasuredValue(value=0, uncertainty=0, unit="MPa", coverage_factor=2.0),
                MeasuredValue(value=0, uncertainty=0, unit="-", coverage_factor=2.0)
            )

        log_stress = log_stress[valid]
        log_strain = log_strain[valid]

        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            log_strain, log_stress
        )

        n = slope
        K = np.exp(intercept)

        # Uncertainty from regression
        u_n = std_err
        u_K = K * std_err  # Approximate

        return (
            MeasuredValue(
                value=round(K, 1),
                uncertainty=round(2 * u_K, 1),
                unit="MPa",
                coverage_factor=2.0
            ),
            MeasuredValue(
                value=round(n, 3),
                uncertainty=round(2 * u_n, 3),
                unit="-",
                coverage_factor=2.0
            )
        )
