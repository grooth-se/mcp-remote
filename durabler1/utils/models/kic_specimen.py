"""
KIC Specimen and Material Models for ASTM E399 Fracture Toughness Testing.

This module provides dataclasses for KIC test specimens following ASTM E399
for plane-strain fracture toughness determination.

Specimen Types:
    - SE(B): Single Edge Bend (three-point bend)
    - C(T): Compact Tension

References:
    ASTM E399 - Standard Test Method for Linear-Elastic Plane-Strain
    Fracture Toughness of Metallic Materials
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import math


@dataclass
class KICMaterial:
    """
    Material properties for KIC calculation.

    Attributes
    ----------
    yield_strength : float
        0.2% offset yield strength sigma_ys (MPa)
    youngs_modulus : float
        Young's modulus E (GPa)
    poissons_ratio : float
        Poisson's ratio nu, default 0.3
    """
    yield_strength: float      # sigma_ys (MPa)
    youngs_modulus: float      # E (GPa)
    poissons_ratio: float = 0.3

    @property
    def E_prime(self) -> float:
        """
        Plane-strain Young's modulus E' = E / (1 - nu^2).

        Returns
        -------
        float
            E' in GPa
        """
        return self.youngs_modulus / (1 - self.poissons_ratio**2)


@dataclass
class KICSpecimen:
    """
    Specimen geometry for KIC fracture toughness testing per ASTM E399.

    Supports SE(B) (Single Edge Bend) and C(T) (Compact Tension) specimens.

    Attributes
    ----------
    specimen_id : str
        Unique specimen identifier
    specimen_type : str
        'SE(B)' for Single Edge Bend or 'C(T)' for Compact Tension
    W : float
        Width (depth for SE(B)) in mm
    B : float
        Thickness in mm
    a_0 : float
        Initial crack length in mm
    S : float
        Span for SE(B) specimen in mm (typically S = 4W)
    B_n : float, optional
        Net thickness for side-grooved specimens in mm
    material : str
        Material designation

    Notes
    -----
    ASTM E399 Geometry Requirements:
    - a/W ratio: 0.45 to 0.55
    - For SE(B): S/W should be approximately 4.0
    - For C(T): W/B ratio typically 2.0
    """
    specimen_id: str
    specimen_type: str          # 'SE(B)' or 'C(T)'
    W: float                    # Width/depth (mm)
    B: float                    # Thickness (mm)
    a_0: float                  # Initial crack length (mm)
    S: float = 0.0              # Span for SE(B) (mm)
    B_n: Optional[float] = None # Net thickness if side-grooved (mm)
    material: str = ""

    @property
    def a_W_ratio(self) -> float:
        """
        Crack length to width ratio a/W.

        Returns
        -------
        float
            a_0 / W ratio
        """
        if self.W == 0:
            return 0.0
        return self.a_0 / self.W

    @property
    def B_effective(self) -> float:
        """
        Effective thickness for side-grooved specimens.

        For side-grooved specimens: B_eff = sqrt(B * B_n)
        For plain specimens: B_eff = B

        Returns
        -------
        float
            Effective thickness in mm
        """
        if self.B_n is not None and self.B_n < self.B:
            return math.sqrt(self.B * self.B_n)
        return self.B

    @property
    def is_side_grooved(self) -> bool:
        """Check if specimen is side-grooved."""
        return self.B_n is not None and self.B_n < self.B

    @property
    def ligament(self) -> float:
        """
        Remaining ligament (W - a_0).

        Returns
        -------
        float
            Ligament length in mm
        """
        return self.W - self.a_0

    @property
    def is_valid_geometry(self) -> bool:
        """
        Check if a/W ratio is within ASTM E399 limits (0.45-0.55).

        Returns
        -------
        bool
            True if geometry is valid
        """
        return 0.45 <= self.a_W_ratio <= 0.55

    @property
    def S_W_ratio(self) -> float:
        """
        Span to width ratio S/W for SE(B) specimens.

        Returns
        -------
        float
            S/W ratio (should be ~4.0 for standard SE(B))
        """
        if self.W == 0:
            return 0.0
        return self.S / self.W

    def f_aW(self) -> float:
        """
        Calculate geometry function f(a/W) based on specimen type.

        Returns
        -------
        float
            Geometry function value

        Raises
        ------
        ValueError
            If specimen type is not recognized
        """
        if self.specimen_type == 'SE(B)':
            return self.f_aW_SEB()
        elif self.specimen_type == 'C(T)':
            return self.f_aW_CT()
        else:
            raise ValueError(f"Unknown specimen type: {self.specimen_type}")

    def f_aW_SEB(self) -> float:
        """
        Geometry function f(a/W) for SE(B) specimen per ASTM E399.

        For SE(B) with S/W = 4:
        f(a/W) = 3*sqrt(x) * [1.99 - x(1-x)(2.15 - 3.93x + 2.7x^2)] /
                 [2(1+2x)(1-x)^1.5]

        where x = a/W

        Returns
        -------
        float
            f(a/W) value for SE(B) specimen
        """
        x = self.a_W_ratio

        if x <= 0 or x >= 1:
            return 0.0

        numerator = 3 * math.sqrt(x) * (1.99 - x * (1 - x) *
                    (2.15 - 3.93 * x + 2.7 * x**2))
        denominator = 2 * (1 + 2 * x) * (1 - x)**1.5

        return numerator / denominator

    def f_aW_CT(self) -> float:
        """
        Geometry function f(a/W) for C(T) specimen per ASTM E399.

        For C(T):
        f(a/W) = (2+x) / (1-x)^1.5 *
                 [0.886 + 4.64x - 13.32x^2 + 14.72x^3 - 5.6x^4]

        where x = a/W

        Returns
        -------
        float
            f(a/W) value for C(T) specimen
        """
        x = self.a_W_ratio

        if x <= 0 or x >= 1:
            return 0.0

        polynomial = 0.886 + 4.64 * x - 13.32 * x**2 + 14.72 * x**3 - 5.6 * x**4
        factor = (2 + x) / (1 - x)**1.5

        return factor * polynomial

    def calculate_K(self, force_kN: float) -> float:
        """
        Calculate stress intensity factor K for given force.

        Parameters
        ----------
        force_kN : float
            Applied force in kN

        Returns
        -------
        float
            Stress intensity factor K in MPa*sqrt(m)

        Notes
        -----
        SE(B): K = (P * S) / (B * W^1.5) * f(a/W)
        C(T):  K = P / (B * W^0.5) * f(a/W)

        Units: P in N, dimensions in m, K in MPa*sqrt(m)
        """
        # Convert to SI units
        P = force_kN * 1000  # N
        B_m = self.B_effective / 1000  # m
        W_m = self.W / 1000  # m
        S_m = self.S / 1000  # m

        f = self.f_aW()

        if self.specimen_type == 'SE(B)':
            # K = (P * S) / (B * W^1.5) * f(a/W)
            K = (P * S_m) / (B_m * W_m**1.5) * f
        elif self.specimen_type == 'C(T)':
            # K = P / (B * W^0.5) * f(a/W)
            K = P / (B_m * W_m**0.5) * f
        else:
            raise ValueError(f"Unknown specimen type: {self.specimen_type}")

        # Convert from Pa*sqrt(m) to MPa*sqrt(m)
        return K / 1e6

    def validate_plane_strain(self, K_Q: float, sigma_ys: float) -> Tuple[bool, List[str]]:
        """
        Validate plane-strain requirements per ASTM E399.

        Parameters
        ----------
        K_Q : float
            Conditional fracture toughness in MPa*sqrt(m)
        sigma_ys : float
            Yield strength in MPa

        Returns
        -------
        Tuple[bool, List[str]]
            (is_valid, list of check results with pass/fail indicators)

        Notes
        -----
        Requirements:
        - B >= 2.5 * (K_Q / sigma_ys)^2
        - a >= 2.5 * (K_Q / sigma_ys)^2
        - (W-a) >= 2.5 * (K_Q / sigma_ys)^2
        """
        checks = []
        is_valid = True

        # Calculate minimum dimension requirement
        # K in MPa*sqrt(m), sigma in MPa -> result in m
        # Convert to mm
        min_dim = 2.5 * (K_Q / sigma_ys)**2 * 1000  # mm

        # Check B (thickness)
        if self.B >= min_dim:
            checks.append(f"B = {self.B:.2f} mm >= {min_dim:.2f} mm (2.5*(K_Q/sigma_ys)^2): PASS")
        else:
            checks.append(f"B = {self.B:.2f} mm < {min_dim:.2f} mm (2.5*(K_Q/sigma_ys)^2): FAIL")
            is_valid = False

        # Check a (crack length)
        if self.a_0 >= min_dim:
            checks.append(f"a = {self.a_0:.2f} mm >= {min_dim:.2f} mm: PASS")
        else:
            checks.append(f"a = {self.a_0:.2f} mm < {min_dim:.2f} mm: FAIL")
            is_valid = False

        # Check ligament (W-a)
        ligament = self.W - self.a_0
        if ligament >= min_dim:
            checks.append(f"(W-a) = {ligament:.2f} mm >= {min_dim:.2f} mm: PASS")
        else:
            checks.append(f"(W-a) = {ligament:.2f} mm < {min_dim:.2f} mm: FAIL")
            is_valid = False

        return is_valid, checks

    def validity_summary(self) -> str:
        """
        Generate formatted validity check summary for geometry.

        Returns
        -------
        str
            Multi-line string with validity check results
        """
        lines = []

        # a/W ratio check
        a_W = self.a_W_ratio
        if 0.45 <= a_W <= 0.55:
            lines.append(f"a_0/W = {a_W:.3f} (valid: 0.45-0.55): PASS")
        else:
            lines.append(f"a_0/W = {a_W:.3f} (valid: 0.45-0.55): FAIL")

        # Span check for SE(B)
        if self.specimen_type == 'SE(B)':
            S_W = self.S_W_ratio
            if 3.8 <= S_W <= 4.2:
                lines.append(f"S/W = {S_W:.2f} (target: 4.0): PASS")
            else:
                lines.append(f"S/W = {S_W:.2f} (target: 4.0): WARNING")

        # Side groove check
        if self.is_side_grooved:
            lines.append(f"Side-grooved: B_n = {self.B_n:.2f} mm, B_eff = {self.B_effective:.2f} mm")

        return "\n".join(lines)

    def __str__(self) -> str:
        """String representation of specimen."""
        return (f"KICSpecimen({self.specimen_id}, {self.specimen_type}, "
                f"W={self.W:.2f}mm, B={self.B:.2f}mm, a={self.a_0:.2f}mm, "
                f"a/W={self.a_W_ratio:.3f})")
