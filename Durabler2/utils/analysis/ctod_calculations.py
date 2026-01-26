"""
CTOD calculation engine per ASTM E1290.

Implements the plastic hinge model for CTOD (Crack Tip Opening Displacement)
calculation from force-CMOD test data.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
import math

# Import MeasuredValue from models
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.models.test_result import MeasuredValue
from utils.models.ctod_specimen import CTODSpecimen, CTODMaterial


@dataclass
class CTODResult:
    """
    Container for CTOD analysis results.

    Parameters
    ----------
    ctod_type : str
        Type of CTOD: 'δc', 'δu', or 'δm'
    ctod_value : MeasuredValue
        CTOD value with uncertainty (mm)
    force : MeasuredValue
        Force at CTOD point (kN)
    cmod : MeasuredValue
        CMOD at CTOD point (mm)
    K : MeasuredValue
        Stress intensity factor (MPa√m)
    is_valid : bool
        Whether result meets validity criteria
    validity_notes : str
        Notes on validity checks
    """
    ctod_type: str
    ctod_value: MeasuredValue
    force: MeasuredValue
    cmod: MeasuredValue
    K: MeasuredValue
    is_valid: bool
    validity_notes: str


class CTODAnalyzer:
    """
    CTOD calculation engine per ASTM E1290.

    Implements the plastic hinge rotation model for calculating CTOD
    from force-CMOD test data.
    """

    def __init__(self):
        """Initialize CTOD analyzer."""
        pass

    def calculate_stress_intensity_K(
        self,
        force: float,
        specimen: CTODSpecimen
    ) -> MeasuredValue:
        """
        Calculate stress intensity factor K for SE(B) or C(T) specimen.

        For SE(B):
        K = (P × S / (B × W^1.5)) × f(a/W)

        For C(T):
        K = (P / (B × W^0.5)) × f(a/W)

        Parameters
        ----------
        force : float
            Applied force (kN)
        specimen : CTODSpecimen
            Specimen geometry

        Returns
        -------
        MeasuredValue
            Stress intensity factor K (MPa√m) with uncertainty
        """
        P = force * 1000  # Convert kN to N
        W = specimen.W / 1000  # Convert mm to m
        B = specimen.B_effective / 1000  # Convert mm to m
        S = specimen.S / 1000  # Convert mm to m
        f_aW = specimen.f_aW()

        if specimen.specimen_type == 'SE(B)':
            K = (P * S / (B * W**1.5)) * f_aW
        else:  # C(T)
            K = (P / (B * W**0.5)) * f_aW

        # Convert to MPa√m
        K_mpa_sqrtm = K / 1e6

        # Uncertainty estimate (~3% for force, geometry)
        u_K = K_mpa_sqrtm * 0.03

        return MeasuredValue(
            value=round(K_mpa_sqrtm, 2),
            uncertainty=round(2 * u_K, 2),
            unit="MPa√m",
            coverage_factor=2.0
        )

    def calculate_elastic_cmod(
        self,
        force: np.ndarray,
        cmod: np.ndarray,
        specimen: CTODSpecimen,
        material: CTODMaterial
    ) -> Tuple[float, float]:
        """
        Calculate elastic compliance and elastic CMOD component.

        Determines the elastic loading slope from initial linear region
        (10% to 60% of Pmax) and calculates the elastic portion of CMOD.

        Parameters
        ----------
        force : np.ndarray
            Force array (kN)
        cmod : np.ndarray
            CMOD array (mm)
        specimen : CTODSpecimen
            Specimen geometry
        material : CTODMaterial
            Material properties

        Returns
        -------
        Tuple[float, float]
            (compliance in mm/kN, elastic_slope for plotting)
        """
        # Find max force
        max_force_idx = np.argmax(force)
        max_force = force[max_force_idx]

        # Use data from 10% to 60% of max force for elastic fit
        # This avoids initial seating effects and plastic region
        lower_limit = 0.10 * max_force
        upper_limit = 0.60 * max_force
        elastic_mask = (force >= lower_limit) & (force <= upper_limit)

        # Only use data up to max force index (loading portion only)
        loading_mask = np.zeros(len(force), dtype=bool)
        loading_mask[:max_force_idx + 1] = True
        elastic_mask = elastic_mask & loading_mask

        if np.sum(elastic_mask) < 10:
            # Not enough points, use first 50% of loading data
            n_elastic = max(10, max_force_idx // 2)
            elastic_mask = np.zeros(len(force), dtype=bool)
            elastic_mask[:n_elastic] = True

        force_elastic = force[elastic_mask]
        cmod_elastic = cmod[elastic_mask]

        # Linear fit: CMOD = compliance * Force + offset
        # compliance = dCMOD/dForce (mm/kN)
        coeffs = np.polyfit(force_elastic, cmod_elastic, 1)
        compliance = coeffs[0]  # mm/kN (slope)

        return compliance, coeffs

    def calculate_plastic_cmod(
        self,
        force: float,
        cmod: float,
        compliance: float
    ) -> float:
        """
        Calculate plastic component of CMOD.

        Vp = V_total - V_elastic = V_total - (compliance × P)

        Parameters
        ----------
        force : float
            Force at point of interest (kN)
        cmod : float
            Total CMOD at point of interest (mm)
        compliance : float
            Elastic compliance (mm/kN)

        Returns
        -------
        float
            Plastic CMOD component Vp (mm)
        """
        v_elastic = compliance * force
        v_plastic = cmod - v_elastic
        return max(0, v_plastic)  # Plastic component cannot be negative

    def calculate_ctod_plastic_hinge(
        self,
        force: float,
        cmod: float,
        specimen: CTODSpecimen,
        material: CTODMaterial,
        compliance: float
    ) -> float:
        """
        Calculate CTOD using plastic hinge rotation model (ASTM E1290).

        δ = δ_el + δ_pl

        Where:
        δ_el = K² × (1 - ν²) / (2 × σ_ys × E)
        δ_pl = (Vp × rp × (W - a0)) / (rp × (W - a0) + a0 + z)

        z = knife edge thickness (typically 0 for clip gage at crack mouth)

        Parameters
        ----------
        force : float
            Force at point of interest (kN)
        cmod : float
            Total CMOD at point of interest (mm)
        specimen : CTODSpecimen
            Specimen geometry
        material : CTODMaterial
            Material properties
        compliance : float
            Elastic compliance (mm/kN)

        Returns
        -------
        float
            CTOD value δ (mm)
        """
        # Calculate stress intensity factor
        K = self.calculate_stress_intensity_K(force, specimen)
        K_Pa = K.value * 1e6  # Convert MPa√m to Pa√m

        # Elastic CTOD component
        E = material.youngs_modulus * 1e9  # GPa to Pa
        nu = material.poissons_ratio
        sigma_ys = material.yield_strength * 1e6  # MPa to Pa

        delta_el = (K_Pa**2 * (1 - nu**2)) / (2 * sigma_ys * E)
        delta_el_mm = delta_el * 1000  # Convert m to mm

        # Plastic CTOD component
        Vp = self.calculate_plastic_cmod(force, cmod, compliance)

        W = specimen.W
        a0 = specimen.a_0
        rp = specimen.rotation_factor()
        z = 0  # Knife edge thickness (assume clip gage at crack mouth)

        if rp * (W - a0) + a0 + z > 0:
            delta_pl = (Vp * rp * (W - a0)) / (rp * (W - a0) + a0 + z)
        else:
            delta_pl = 0

        return delta_el_mm + delta_pl

    def calculate_ctod_bs7448(
        self,
        force: float,
        cmod: float,
        specimen: CTODSpecimen,
        material: CTODMaterial,
        compliance: float,
        z: float = 0.0
    ) -> float:
        """
        Calculate CTOD using BS 7448 formula.

        BS 7448 uses a similar plastic hinge model but with different rotation factor:
        - rp = 0.4 for SE(B) specimens (vs 0.44 in E1290)
        - rp = 0.46 for C(T) specimens

        δ = δ_el + δ_pl

        Where:
        δ_el = K² × (1 - ν²) / (2 × σ_ys × E)
        δ_pl = (rp × (W - a0) × Vp) / (rp × (W - a0) + a0 + z)

        Parameters
        ----------
        force : float
            Force at point of interest (kN)
        cmod : float
            Total CMOD at point of interest (mm)
        specimen : CTODSpecimen
            Specimen geometry
        material : CTODMaterial
            Material properties
        compliance : float
            Elastic compliance (mm/kN)
        z : float
            Knife edge thickness (mm), default 0

        Returns
        -------
        float
            CTOD value δ (mm) per BS 7448
        """
        # Calculate stress intensity factor
        K = self.calculate_stress_intensity_K(force, specimen)
        K_Pa = K.value * 1e6  # Convert MPa√m to Pa√m

        # Elastic CTOD component (same as E1290)
        E = material.youngs_modulus * 1e9  # GPa to Pa
        nu = material.poissons_ratio
        sigma_ys = material.yield_strength * 1e6  # MPa to Pa

        delta_el = (K_Pa**2 * (1 - nu**2)) / (2 * sigma_ys * E)
        delta_el_mm = delta_el * 1000  # Convert m to mm

        # Plastic CTOD component with BS 7448 rotation factors
        Vp = self.calculate_plastic_cmod(force, cmod, compliance)

        W = specimen.W
        a0 = specimen.a_0

        # BS 7448 rotation factors (different from E1290)
        if specimen.specimen_type == 'SE(B)':
            rp_bs = 0.4  # BS 7448 value for SE(B)
        else:  # C(T)
            rp_bs = 0.46  # BS 7448 value for C(T)

        denominator = rp_bs * (W - a0) + a0 + z
        if denominator > 0:
            delta_pl = (rp_bs * (W - a0) * Vp) / denominator
        else:
            delta_pl = 0

        return delta_el_mm + delta_pl

    def identify_ctod_points(
        self,
        force: np.ndarray,
        cmod: np.ndarray,
        specimen: CTODSpecimen,
        material: CTODMaterial
    ) -> dict:
        """
        Identify critical CTOD points (δc, δu, δm) from test data.

        δc: CTOD at cleavage initiation (sudden load drop, no prior growth)
        δu: CTOD at instability after stable crack growth
        δm: CTOD at maximum force plateau

        Parameters
        ----------
        force : np.ndarray
            Force array (kN)
        cmod : np.ndarray
            CMOD array (mm)
        specimen : CTODSpecimen
            Specimen geometry
        material : CTODMaterial
            Material properties

        Returns
        -------
        dict
            Dictionary with 'delta_c', 'delta_u', 'delta_m' keys
            Each value is tuple (index, force, cmod, ctod) or None
        """
        results = {
            'delta_c': None,
            'delta_u': None,
            'delta_m': None
        }

        # Calculate elastic compliance
        compliance, _ = self.calculate_elastic_cmod(force, cmod, specimen, material)

        # Find maximum force point
        max_force_idx = np.argmax(force)
        max_force = force[max_force_idx]

        # δm: CTOD at maximum force
        cmod_at_max = cmod[max_force_idx]
        delta_m = self.calculate_ctod_plastic_hinge(
            max_force, cmod_at_max, specimen, material, compliance
        )
        results['delta_m'] = (max_force_idx, max_force, cmod_at_max, delta_m)

        # δc: Look for sudden load drop (cleavage)
        # Calculate force derivative to detect sudden drops
        if len(force) > 10:
            # Smooth force signal slightly
            window = min(5, len(force) // 20)
            if window > 1:
                force_smooth = np.convolve(force, np.ones(window)/window, mode='same')
            else:
                force_smooth = force

            # Find points with significant load drop (>20% of max in short span)
            for i in range(max_force_idx, len(force) - 5):
                force_drop = force_smooth[i] - force_smooth[i + 5]
                if force_drop > 0.2 * max_force:
                    # Found potential cleavage point
                    # δc is just before the drop
                    cmod_c = cmod[i]
                    force_c = force[i]
                    delta_c = self.calculate_ctod_plastic_hinge(
                        force_c, cmod_c, specimen, material, compliance
                    )
                    results['delta_c'] = (i, force_c, cmod_c, delta_c)
                    break

        # δu: Look for instability after stable growth
        # This occurs when force drops after max but with prior gradual decrease
        # (indicates some stable crack extension before instability)
        if results['delta_c'] is None and max_force_idx < len(force) - 10:
            # Check if there's gradual force decrease followed by sharp drop
            for i in range(max_force_idx + 5, len(force) - 5):
                # Gradual decrease region before this point
                gradual = force[i] < max_force * 0.95  # Some decrease from max
                # Sharp drop after this point
                if i + 5 < len(force):
                    sharp_drop = (force[i] - force[i + 5]) > 0.15 * force[i]
                else:
                    sharp_drop = False

                if gradual and sharp_drop:
                    cmod_u = cmod[i]
                    force_u = force[i]
                    delta_u = self.calculate_ctod_plastic_hinge(
                        force_u, cmod_u, specimen, material, compliance
                    )
                    results['delta_u'] = (i, force_u, cmod_u, delta_u)
                    break

        return results

    def run_analysis(
        self,
        force: np.ndarray,
        cmod: np.ndarray,
        specimen: CTODSpecimen,
        material: CTODMaterial
    ) -> dict:
        """
        Run complete CTOD analysis on test data.

        Parameters
        ----------
        force : np.ndarray
            Force array (kN)
        cmod : np.ndarray
            CMOD array (mm)
        specimen : CTODSpecimen
            Specimen geometry
        material : CTODMaterial
            Material properties

        Returns
        -------
        dict
            Complete analysis results including:
            - P_max: Maximum force
            - CMOD_max: CMOD at maximum force
            - delta_c, delta_u, delta_m: CTOD values
            - K_max: Stress intensity at max force
            - compliance: Elastic compliance
            - validity: Validity check results
        """
        results = {}

        # Calculate elastic compliance
        compliance, elastic_coeffs = self.calculate_elastic_cmod(
            force, cmod, specimen, material
        )
        results['compliance'] = compliance
        results['elastic_coeffs'] = elastic_coeffs

        # Find maximum force
        max_force_idx = np.argmax(force)
        max_force = force[max_force_idx]
        cmod_at_max = cmod[max_force_idx]

        results['P_max'] = MeasuredValue(
            value=round(max_force, 2),
            uncertainty=round(max_force * 0.01 * 2, 2),  # ~1% uncertainty
            unit="kN",
            coverage_factor=2.0
        )

        results['CMOD_max'] = MeasuredValue(
            value=round(cmod_at_max, 3),
            uncertainty=round(cmod_at_max * 0.02 * 2, 3),  # ~2% uncertainty
            unit="mm",
            coverage_factor=2.0
        )

        # Calculate K at max force
        results['K_max'] = self.calculate_stress_intensity_K(max_force, specimen)

        # Identify CTOD points
        ctod_points = self.identify_ctod_points(force, cmod, specimen, material)

        # Process each CTOD type
        for ctod_type in ['delta_c', 'delta_u', 'delta_m']:
            point_data = ctod_points[ctod_type]
            if point_data is not None:
                idx, P, V, delta = point_data
                # Estimate uncertainty (~5% for CTOD)
                u_delta = delta * 0.05

                results[ctod_type] = CTODResult(
                    ctod_type=ctod_type.replace('_', ''),
                    ctod_value=MeasuredValue(
                        value=round(delta, 4),
                        uncertainty=round(2 * u_delta, 4),
                        unit="mm",
                        coverage_factor=2.0
                    ),
                    force=MeasuredValue(
                        value=round(P, 2),
                        uncertainty=round(P * 0.01 * 2, 2),
                        unit="kN",
                        coverage_factor=2.0
                    ),
                    cmod=MeasuredValue(
                        value=round(V, 3),
                        uncertainty=round(V * 0.02 * 2, 3),
                        unit="mm",
                        coverage_factor=2.0
                    ),
                    K=self.calculate_stress_intensity_K(P, specimen),
                    is_valid=specimen.is_valid_geometry,
                    validity_notes=specimen.validity_summary()
                )
            else:
                results[ctod_type] = None

        # Calculate BS 7448 CTOD at max force (for comparison)
        delta_m_bs7448 = self.calculate_ctod_bs7448(
            max_force, cmod_at_max, specimen, material, compliance
        )
        u_delta_bs = delta_m_bs7448 * 0.05
        results['delta_m_bs7448'] = MeasuredValue(
            value=round(delta_m_bs7448, 4),
            uncertainty=round(2 * u_delta_bs, 4),
            unit="mm",
            coverage_factor=2.0
        )

        # Overall validity
        results['is_valid'] = specimen.is_valid_geometry
        results['validity_summary'] = specimen.validity_summary()
        results['a_W_ratio'] = MeasuredValue(
            value=round(specimen.a_W_ratio, 3),
            uncertainty=0.005,
            unit="-",
            coverage_factor=2.0
        )

        return results

    def calculate_5_percent_secant(
        self,
        force: np.ndarray,
        cmod: np.ndarray,
        compliance: float
    ) -> Tuple[float, float]:
        """
        Calculate 5% secant offset line for Pq determination.

        The 5% secant line has slope = 0.95 × elastic_slope.
        Pq is where this line intersects the Force-CMOD curve.

        Parameters
        ----------
        force : np.ndarray
            Force array (kN)
        cmod : np.ndarray
            CMOD array (mm)
        compliance : float
            Elastic compliance (mm/kN)

        Returns
        -------
        Tuple[float, float]
            (Pq force value, CMOD at Pq)
        """
        # 5% secant slope is 95% of elastic slope
        # Elastic: CMOD = compliance × P
        # 5% secant: CMOD = 1.05 × compliance × P (need more displacement for same force)
        secant_compliance = compliance * 1.05

        # Find intersection of 5% secant with force-CMOD curve
        # Secant line passes through origin
        for i in range(len(force) - 1):
            # Point on curve
            P_curve = force[i]
            V_curve = cmod[i]

            # Point on secant at same force
            V_secant = secant_compliance * P_curve

            # Check if curve is above secant (before intersection)
            # and then below (after intersection)
            if V_curve < V_secant and i > 10:
                # Linear interpolation to find exact intersection
                P_prev = force[i - 1]
                V_prev = cmod[i - 1]
                V_secant_prev = secant_compliance * P_prev

                if V_prev >= V_secant_prev:
                    # Intersection between i-1 and i
                    # Interpolate
                    t = (V_prev - V_secant_prev) / (
                        (V_prev - V_secant_prev) - (V_curve - V_secant)
                    )
                    Pq = P_prev + t * (P_curve - P_prev)
                    Vq = cmod[i - 1] + t * (V_curve - V_prev)
                    return Pq, Vq

        # No intersection found, return max force point
        max_idx = np.argmax(force)
        return force[max_idx], cmod[max_idx]
