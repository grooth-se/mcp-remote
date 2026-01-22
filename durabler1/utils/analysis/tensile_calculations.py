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

    def calculate_youngs_modulus_displacement(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        area_uncertainty: float,
        reference_length: float,
        Rm: float
    ) -> MeasuredValue:
        """
        Calculate Young's modulus E from displacement/crosshead data.

        Uses stress range 15%-40% of Rm to select the elastic region,
        removing data affected by machine setup mismatch at low loads.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (from displacement)
        area_uncertainty : float
            Uncertainty in cross-sectional area (mm^2)
        reference_length : float
            Reference length (parallel length Lc) in mm
        Rm : float
            Ultimate tensile strength in MPa

        Returns
        -------
        MeasuredValue
            Young's modulus with uncertainty in GPa
        """
        # Use stress range 15%-40% of Rm to avoid machine setup mismatch
        min_stress = 0.15 * Rm
        max_stress = 0.40 * Rm

        # Select elastic region based on stress range
        mask = (stress >= min_stress) & (stress <= max_stress)

        if np.sum(mask) < 10:
            # Try wider range if insufficient points
            min_stress = 0.10 * Rm
            max_stress = 0.50 * Rm
            mask = (stress >= min_stress) & (stress <= max_stress)

        if np.sum(mask) < 5:
            raise ValueError("Insufficient data points in elastic region (15%-40% Rm)")

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
            relative_area_unc = area_uncertainty / (area_mean * reference_length / 1000)
            u_area = abs(E * relative_area_unc * 0.5)
        else:
            u_area = 0

        # 3. Displacement uncertainty (higher than extensometer)
        displacement_uncertainty = 0.01  # 0.01 mm typical for crosshead
        u_displacement = E * displacement_uncertainty / reference_length

        # Combined standard uncertainty
        u_combined = np.sqrt(u_regression**2 + u_area**2 + u_displacement**2)

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

    def calculate_yield_strength_rp02_displacement(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        E_modulus: float,
        Rm: float,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate 0.2% offset yield strength (Rp0.2) for displacement/crosshead data.

        This method uses strain at 30% of Rm as the baseline reference point
        to compensate for initial misalignment in the test equipment. The strain
        baseline is shifted so that strain at 30% Rm becomes the reference zero.

        NOTE: This method should ONLY be used for displacement/crosshead data,
        NOT for extensometer data.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (from displacement)
        E_modulus : float
            Young's modulus in GPa
        Rm : float
            Ultimate tensile strength in MPa
        area : float
            Cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area in mm^2

        Returns
        -------
        MeasuredValue
            Yield strength Rp0.2 with uncertainty in MPa
        """
        offset = self.config.offset_strain  # 0.002 (0.2%)
        E_mpa = E_modulus * 1000  # Convert GPa to MPa

        # Find strain at 30% of Rm (baseline reference point)
        target_stress = 0.30 * Rm

        # Find the index closest to 30% Rm on the ascending part of the curve
        # Use only the portion before max stress to avoid post-necking data
        max_idx = np.argmax(stress)
        ascending_stress = stress[:max_idx + 1]
        ascending_strain = strain[:max_idx + 1]

        # Find index where stress is closest to 30% Rm
        baseline_idx = np.argmin(np.abs(ascending_stress - target_stress))
        strain_baseline = ascending_strain[baseline_idx]

        # Shift strain so that strain at 30% Rm becomes the reference
        strain_corrected = strain - strain_baseline

        # Apply standard offset method with corrected strain
        # Offset line: sigma = E * (epsilon_corrected - offset)
        offset_line = E_mpa * (strain_corrected - offset)
        curve_minus_offset = stress - offset_line

        # Find region after corrected strain exceeds offset
        valid_idx = strain_corrected > offset * 1.5

        if not np.any(valid_idx):
            raise ValueError("Insufficient strain data for yield calculation (displacement method)")

        curve_segment = curve_minus_offset[valid_idx]
        strain_segment = strain_corrected[valid_idx]
        stress_segment = stress[valid_idx]

        # Find sign change (zero crossing)
        sign_changes = np.where(np.diff(np.sign(curve_segment)))[0]

        if len(sign_changes) == 0:
            # If no crossing found, find point closest to zero
            idx = np.argmin(np.abs(curve_segment))
            yield_stress = stress_segment[idx]
        else:
            # Linear interpolation at first crossing
            idx = sign_changes[0]
            s0, s1 = strain_segment[idx], strain_segment[idx + 1]
            c0, c1 = curve_segment[idx], curve_segment[idx + 1]

            if c1 - c0 != 0:
                yield_strain = s0 - c0 * (s1 - s0) / (c1 - c0)
                yield_stress = E_mpa * (yield_strain - offset)
            else:
                yield_stress = stress_segment[idx]

        # Uncertainty calculation
        u_area = yield_stress * (area_uncertainty / area)
        u_force = yield_stress * self.config.force_calibration_uncertainty
        # Additional uncertainty from baseline determination
        u_baseline = yield_stress * 0.01  # ~1% from baseline selection

        if len(sign_changes) > 0 and idx + 1 < len(stress_segment):
            u_interpolation = abs(stress_segment[idx + 1] - stress_segment[idx]) / 4
        else:
            u_interpolation = yield_stress * 0.01

        u_combined = np.sqrt(u_area**2 + u_force**2 + u_interpolation**2 + u_baseline**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(yield_stress, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_yield_strength_rp05_displacement(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        E_modulus: float,
        Rm: float,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate 0.5% offset yield strength (Rp0.5) for displacement/crosshead data.

        This method uses strain at 30% of Rm as the baseline reference point
        to compensate for initial misalignment in the test equipment. The strain
        baseline is shifted so that strain at 30% Rm becomes the reference zero.

        NOTE: This method should ONLY be used for displacement/crosshead data,
        NOT for extensometer data.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (from displacement)
        E_modulus : float
            Young's modulus in GPa
        Rm : float
            Ultimate tensile strength in MPa
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
        E_mpa = E_modulus * 1000  # Convert GPa to MPa

        # Find strain at 30% of Rm (baseline reference point)
        target_stress = 0.30 * Rm

        # Find the index closest to 30% Rm on the ascending part of the curve
        max_idx = np.argmax(stress)
        ascending_stress = stress[:max_idx + 1]
        ascending_strain = strain[:max_idx + 1]

        # Find index where stress is closest to 30% Rm
        baseline_idx = np.argmin(np.abs(ascending_stress - target_stress))
        strain_baseline = ascending_strain[baseline_idx]

        # Shift strain so that strain at 30% Rm becomes the reference
        strain_corrected = strain - strain_baseline

        # Apply standard offset method with corrected strain
        offset_line = E_mpa * (strain_corrected - offset)
        curve_minus_offset = stress - offset_line

        # Find region after corrected strain exceeds offset
        valid_idx = strain_corrected > offset * 1.5

        if not np.any(valid_idx):
            raise ValueError("Insufficient strain data for Rp0.5 calculation (displacement method)")

        curve_segment = curve_minus_offset[valid_idx]
        strain_segment = strain_corrected[valid_idx]
        stress_segment = stress[valid_idx]

        # Find sign change (zero crossing)
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

        # Uncertainty calculation
        u_area = yield_stress * (area_uncertainty / area)
        u_force = yield_stress * self.config.force_calibration_uncertainty
        u_baseline = yield_stress * 0.01  # Baseline determination uncertainty

        if len(sign_changes) > 0 and idx + 1 < len(stress_segment):
            u_interpolation = abs(stress_segment[idx + 1] - stress_segment[idx]) / 4
        else:
            u_interpolation = yield_stress * 0.01

        u_combined = np.sqrt(u_area**2 + u_force**2 + u_interpolation**2 + u_baseline**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(yield_stress, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_upper_yield_strength_reh(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate upper yield strength ReH per ASTM E8 / ISO 6892-1.

        ReH is the maximum stress at the onset of yielding, before the
        stress drops during Lüders band formation (yield point elongation).

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        area : float
            Cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area in mm^2

        Returns
        -------
        MeasuredValue
            Upper yield strength ReH with uncertainty in MPa
        """
        # Find the first local maximum in stress (upper yield point)
        # Look in the early part of the curve (first 5% strain typically)
        max_strain_search = 0.05
        search_idx = strain < max_strain_search

        if not np.any(search_idx):
            search_idx = np.ones(len(strain), dtype=bool)

        stress_search = stress[search_idx]

        # Find local maxima by looking for sign changes in the derivative
        # Use smoothing to avoid noise-induced false peaks
        window = min(5, len(stress_search) // 10)
        if window < 2:
            window = 2

        # Simple smoothing
        stress_smooth = np.convolve(stress_search, np.ones(window)/window, mode='same')

        # Find first significant peak (where derivative changes from + to -)
        diff_stress = np.diff(stress_smooth)

        # Look for first point where stress starts to decrease significantly
        # after an initial rise
        peak_idx = None
        for i in range(len(diff_stress) - 1):
            if diff_stress[i] > 0 and diff_stress[i + 1] < 0:
                # Check if this is a significant peak (not just noise)
                if i > 10:  # Skip very early points
                    peak_idx = i + 1
                    break

        if peak_idx is None:
            # No clear yield point, use maximum in search region
            peak_idx = np.argmax(stress_search)

        ReH = stress_search[peak_idx]

        # Uncertainty calculation
        u_area = ReH * (area_uncertainty / area)
        u_force = ReH * self.config.force_calibration_uncertainty
        u_peak = ReH * 0.005  # Peak detection uncertainty

        u_combined = np.sqrt(u_area**2 + u_force**2 + u_peak**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(ReH, 1),
            uncertainty=round(U, 1),
            unit="MPa",
            coverage_factor=2.0
        )

    def calculate_lower_yield_strength_rel(
        self,
        stress: np.ndarray,
        strain: np.ndarray,
        area: float,
        area_uncertainty: float
    ) -> MeasuredValue:
        """
        Calculate lower yield strength ReL per ASTM E8 / ISO 6892-1.

        ReL is the lowest stress during Lüders band formation (yield point
        elongation), excluding the initial transient effect.

        Parameters
        ----------
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain
        area : float
            Cross-sectional area in mm^2
        area_uncertainty : float
            Uncertainty in area in mm^2

        Returns
        -------
        MeasuredValue
            Lower yield strength ReL with uncertainty in MPa
        """
        # First find ReH to identify the yield point region
        max_strain_search = 0.05
        search_idx = strain < max_strain_search

        if not np.any(search_idx):
            search_idx = np.ones(len(strain), dtype=bool)

        stress_search = stress[search_idx]
        strain_search = strain[search_idx]

        # Find the peak (ReH location)
        window = min(5, len(stress_search) // 10)
        if window < 2:
            window = 2
        stress_smooth = np.convolve(stress_search, np.ones(window)/window, mode='same')
        diff_stress = np.diff(stress_smooth)

        peak_idx = None
        for i in range(len(diff_stress) - 1):
            if diff_stress[i] > 0 and diff_stress[i + 1] < 0:
                if i > 10:
                    peak_idx = i + 1
                    break

        if peak_idx is None:
            peak_idx = np.argmax(stress_search)

        # ReL is the minimum stress in the Lüders region (after ReH)
        # The Lüders region typically extends until strain hardening begins
        # Look for minimum between ReH and where stress starts rising again

        # Search from peak to end of search region
        post_peak_stress = stress_search[peak_idx:]
        post_peak_strain = strain_search[peak_idx:]

        if len(post_peak_stress) < 5:
            # Not enough data, use the value right after peak
            ReL = stress_search[min(peak_idx + 5, len(stress_search) - 1)]
        else:
            # Find the minimum in the Lüders plateau region
            # Exclude initial transient (first ~20% of post-peak region)
            transient_skip = max(1, len(post_peak_stress) // 5)
            luders_region = post_peak_stress[transient_skip:]

            if len(luders_region) > 0:
                min_idx = np.argmin(luders_region)
                ReL = luders_region[min_idx]
            else:
                ReL = post_peak_stress[-1]

        # Uncertainty calculation
        u_area = ReL * (area_uncertainty / area)
        u_force = ReL * self.config.force_calibration_uncertainty
        u_detection = ReL * 0.005  # Detection uncertainty

        u_combined = np.sqrt(u_area**2 + u_force**2 + u_detection**2)
        U = 2 * u_combined

        return MeasuredValue(
            value=round(ReL, 1),
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

    def calculate_rates_at_point(
        self,
        time: np.ndarray,
        stress: np.ndarray,
        strain: np.ndarray,
        displacement: np.ndarray,
        point_index: int,
        window: int = 10
    ) -> Tuple[float, float, float]:
        """
        Calculate stress rate, strain rate, and displacement rate at a specific point.

        Uses a local linear regression around the point for accurate rate calculation.

        Parameters
        ----------
        time : np.ndarray
            Time array in seconds
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (mm/mm)
        displacement : np.ndarray
            Displacement in mm
        point_index : int
            Index of the point at which to calculate rates
        window : int
            Number of points before and after for local regression (default 10)

        Returns
        -------
        Tuple[float, float, float]
            (stress_rate MPa/s, strain_rate 1/s, displacement_rate mm/s)
        """
        # Ensure valid window bounds
        start_idx = max(0, point_index - window)
        end_idx = min(len(time), point_index + window + 1)

        if end_idx - start_idx < 3:
            # Not enough points for regression
            return (0.0, 0.0, 0.0)

        # Extract local data
        t_local = time[start_idx:end_idx]
        stress_local = stress[start_idx:end_idx]
        strain_local = strain[start_idx:end_idx]
        disp_local = displacement[start_idx:end_idx]

        # Calculate rates using linear regression (slope = rate)
        # Stress rate
        if len(t_local) >= 2 and (t_local[-1] - t_local[0]) > 0:
            stress_slope, _, _, _, _ = stats.linregress(t_local, stress_local)
            strain_slope, _, _, _, _ = stats.linregress(t_local, strain_local)
            disp_slope, _, _, _, _ = stats.linregress(t_local, disp_local)
        else:
            stress_slope = 0.0
            strain_slope = 0.0
            disp_slope = 0.0

        return (stress_slope, strain_slope, disp_slope)

    def calculate_rates_at_rp02(
        self,
        time: np.ndarray,
        stress: np.ndarray,
        strain: np.ndarray,
        displacement: np.ndarray,
        E_modulus: float
    ) -> Tuple[MeasuredValue, MeasuredValue, MeasuredValue]:
        """
        Calculate stress rate, strain rate, and displacement rate at Rp0.2.

        Parameters
        ----------
        time : np.ndarray
            Time array in seconds
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (mm/mm)
        displacement : np.ndarray
            Displacement in mm
        E_modulus : float
            Young's modulus in GPa

        Returns
        -------
        Tuple[MeasuredValue, MeasuredValue, MeasuredValue]
            (stress_rate, strain_rate, displacement_rate)
        """
        # Find Rp0.2 point using offset method
        offset = self.config.offset_strain  # 0.002
        E_mpa = E_modulus * 1000

        offset_line = E_mpa * (strain - offset)
        curve_minus_offset = stress - offset_line

        valid_idx = strain > offset * 1.5
        if not np.any(valid_idx):
            return self._create_zero_rates()

        curve_segment = curve_minus_offset[valid_idx]
        indices = np.where(valid_idx)[0]

        sign_changes = np.where(np.diff(np.sign(curve_segment)))[0]

        if len(sign_changes) == 0:
            idx_local = np.argmin(np.abs(curve_segment))
        else:
            idx_local = sign_changes[0]

        rp02_idx = indices[idx_local]

        # Calculate rates at this point
        stress_rate, strain_rate, disp_rate = self.calculate_rates_at_point(
            time, stress, strain, displacement, rp02_idx
        )

        return self._create_rate_results(stress_rate, strain_rate, disp_rate)

    def calculate_rates_at_reh(
        self,
        time: np.ndarray,
        stress: np.ndarray,
        strain: np.ndarray,
        displacement: np.ndarray
    ) -> Tuple[MeasuredValue, MeasuredValue, MeasuredValue]:
        """
        Calculate stress rate, strain rate, and displacement rate at ReH.

        Parameters
        ----------
        time : np.ndarray
            Time array in seconds
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (mm/mm)
        displacement : np.ndarray
            Displacement in mm

        Returns
        -------
        Tuple[MeasuredValue, MeasuredValue, MeasuredValue]
            (stress_rate, strain_rate, displacement_rate)
        """
        # Find ReH point (first local maximum in early part of curve)
        max_strain_search = 0.05
        search_idx = strain < max_strain_search

        if not np.any(search_idx):
            search_idx = np.ones(len(strain), dtype=bool)

        stress_search = stress[search_idx]

        # Smoothing and peak detection
        window = min(5, len(stress_search) // 10)
        if window < 2:
            window = 2

        stress_smooth = np.convolve(stress_search, np.ones(window)/window, mode='same')
        diff_stress = np.diff(stress_smooth)

        peak_idx = None
        for i in range(len(diff_stress) - 1):
            if diff_stress[i] > 0 and diff_stress[i + 1] < 0:
                if i > 10:
                    peak_idx = i + 1
                    break

        if peak_idx is None:
            peak_idx = np.argmax(stress_search)

        # Convert to global index
        indices = np.where(search_idx)[0]
        reh_idx = indices[peak_idx] if peak_idx < len(indices) else indices[-1]

        # Calculate rates at this point
        stress_rate, strain_rate, disp_rate = self.calculate_rates_at_point(
            time, stress, strain, displacement, reh_idx
        )

        return self._create_rate_results(stress_rate, strain_rate, disp_rate)

    def calculate_rates_at_rm(
        self,
        time: np.ndarray,
        stress: np.ndarray,
        strain: np.ndarray,
        displacement: np.ndarray
    ) -> Tuple[MeasuredValue, MeasuredValue, MeasuredValue]:
        """
        Calculate stress rate, strain rate, and displacement rate at Rm.

        Parameters
        ----------
        time : np.ndarray
            Time array in seconds
        stress : np.ndarray
            Engineering stress in MPa
        strain : np.ndarray
            Engineering strain (mm/mm)
        displacement : np.ndarray
            Displacement in mm

        Returns
        -------
        Tuple[MeasuredValue, MeasuredValue, MeasuredValue]
            (stress_rate, strain_rate, displacement_rate)
        """
        # Find Rm point (maximum stress)
        rm_idx = np.argmax(stress)

        # Calculate rates at this point
        stress_rate, strain_rate, disp_rate = self.calculate_rates_at_point(
            time, stress, strain, displacement, rm_idx
        )

        return self._create_rate_results(stress_rate, strain_rate, disp_rate)

    def _create_rate_results(
        self,
        stress_rate: float,
        strain_rate: float,
        disp_rate: float
    ) -> Tuple[MeasuredValue, MeasuredValue, MeasuredValue]:
        """Create MeasuredValue objects for rate results."""
        # Estimate uncertainties (5% typical for rate measurements)
        u_stress = abs(stress_rate) * 0.05
        u_strain = abs(strain_rate) * 0.05
        u_disp = abs(disp_rate) * 0.05

        return (
            MeasuredValue(
                value=round(stress_rate, 2),
                uncertainty=round(2 * u_stress, 2),
                unit="MPa/s",
                coverage_factor=2.0
            ),
            MeasuredValue(
                value=round(strain_rate, 6),
                uncertainty=round(2 * u_strain, 6),
                unit="1/s",
                coverage_factor=2.0
            ),
            MeasuredValue(
                value=round(disp_rate, 4),
                uncertainty=round(2 * u_disp, 4),
                unit="mm/s",
                coverage_factor=2.0
            )
        )

    def _create_zero_rates(self) -> Tuple[MeasuredValue, MeasuredValue, MeasuredValue]:
        """Create zero rate results when calculation is not possible."""
        return (
            MeasuredValue(value=0.0, uncertainty=0.0, unit="MPa/s", coverage_factor=2.0),
            MeasuredValue(value=0.0, uncertainty=0.0, unit="1/s", coverage_factor=2.0),
            MeasuredValue(value=0.0, uncertainty=0.0, unit="mm/s", coverage_factor=2.0)
        )
