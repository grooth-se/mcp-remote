"""
CTOD specimen data models for ASTM E1290 testing.

Provides dataclasses for SE(B) and C(T) specimen geometries
with validation and property calculations.
"""

from dataclasses import dataclass
from typing import Optional
import math


@dataclass
class CTODSpecimen:
    """
    CTOD test specimen geometry and properties.

    Supports SE(B) (Single Edge Bend) and C(T) (Compact Tension) specimens
    per ASTM E1290 requirements.

    Parameters
    ----------
    specimen_id : str
        Unique specimen identifier
    specimen_type : str
        'SE(B)' for three-point bend or 'C(T)' for compact tension
    W : float
        Specimen width (mm) - depth for SE(B), width for C(T)
    B : float
        Specimen thickness (mm)
    a_0 : float
        Initial crack length (mm) including notch and fatigue pre-crack
    S : float
        Span for SE(B) specimens (mm), typically S = 4*W
    B_n : float, optional
        Net thickness at side grooves (mm), equals B if no side grooves
    material : str, optional
        Material designation
    """
    specimen_id: str
    specimen_type: str  # 'SE(B)' or 'C(T)'
    W: float           # Width/depth (mm)
    B: float           # Thickness (mm)
    a_0: float         # Initial crack length (mm)
    S: float           # Span for SE(B) (mm)
    B_n: Optional[float] = None  # Net thickness if side-grooved (mm)
    material: str = ""

    def __post_init__(self):
        """Validate specimen type and set defaults."""
        if self.specimen_type not in ['SE(B)', 'C(T)']:
            raise ValueError(f"Invalid specimen type: {self.specimen_type}. "
                           f"Must be 'SE(B)' or 'C(T)'")
        if self.B_n is None:
            self.B_n = self.B

    @property
    def a_W_ratio(self) -> float:
        """
        Calculate a₀/W ratio.

        Returns
        -------
        float
            Crack length to width ratio
        """
        return self.a_0 / self.W

    @property
    def is_valid_geometry(self) -> bool:
        """
        Check if specimen geometry meets ASTM E1290 validity requirements.

        Returns
        -------
        bool
            True if 0.45 ≤ a₀/W ≤ 0.70
        """
        return 0.45 <= self.a_W_ratio <= 0.70

    @property
    def ligament(self) -> float:
        """
        Calculate remaining ligament b = W - a₀.

        Returns
        -------
        float
            Ligament length (mm)
        """
        return self.W - self.a_0

    @property
    def B_effective(self) -> float:
        """
        Calculate effective thickness for side-grooved specimens.

        B_eff = sqrt(B * B_n)

        Returns
        -------
        float
            Effective thickness (mm)
        """
        return math.sqrt(self.B * self.B_n)

    def f_aW(self) -> float:
        """
        Calculate geometry function f(a/W) for stress intensity factor.

        For SE(B) specimens per ASTM E1290:
        f(a/W) = 3*(a/W)^0.5 * [1.99 - (a/W)*(1-a/W)*(2.15-3.93*a/W+2.7*(a/W)^2)]
                 / [2*(1+2*a/W)*(1-a/W)^1.5]

        Returns
        -------
        float
            Geometry function value
        """
        x = self.a_W_ratio

        if self.specimen_type == 'SE(B)':
            numerator = 3 * math.sqrt(x) * (
                1.99 - x * (1 - x) * (2.15 - 3.93 * x + 2.7 * x**2)
            )
            denominator = 2 * (1 + 2 * x) * (1 - x)**1.5
            return numerator / denominator

        elif self.specimen_type == 'C(T)':
            # C(T) geometry function
            return ((2 + x) / (1 - x)**1.5) * (
                0.886 + 4.64 * x - 13.32 * x**2 + 14.72 * x**3 - 5.6 * x**4
            )

        return 0.0

    def rotation_factor(self) -> float:
        """
        Get plastic rotation factor rp for CTOD calculation.

        Returns
        -------
        float
            Rotation factor (dimensionless)
        """
        if self.specimen_type == 'SE(B)':
            # Standard rotation factor for SE(B)
            return 0.44
        elif self.specimen_type == 'C(T)':
            # Rotation factor for C(T) depends on a/W
            # Simplified: use 0.46 as typical value
            return 0.46
        return 0.44

    def validity_summary(self) -> str:
        """
        Generate validity check summary.

        Returns
        -------
        str
            Summary of validity checks
        """
        checks = []

        # a/W ratio check
        a_W = self.a_W_ratio
        if 0.45 <= a_W <= 0.70:
            checks.append(f"✓ a₀/W = {a_W:.3f} (valid: 0.45-0.70)")
        else:
            checks.append(f"✗ a₀/W = {a_W:.3f} (INVALID: must be 0.45-0.70)")

        # Span check for SE(B)
        if self.specimen_type == 'SE(B)':
            S_W = self.S / self.W
            if 3.8 <= S_W <= 4.2:
                checks.append(f"✓ S/W = {S_W:.2f} (valid: ~4.0)")
            else:
                checks.append(f"✗ S/W = {S_W:.2f} (should be ~4.0)")

        # Side groove check
        if self.B_n < self.B:
            groove_pct = (1 - self.B_n / self.B) * 100
            checks.append(f"  Side grooves: {groove_pct:.1f}% reduction")
        else:
            checks.append("  No side grooves")

        return "\n".join(checks)


@dataclass
class CTODMaterial:
    """
    Material properties for CTOD calculations.

    Parameters
    ----------
    yield_strength : float
        0.2% offset yield strength σ_ys (MPa)
    ultimate_strength : float
        Ultimate tensile strength σ_uts (MPa)
    youngs_modulus : float
        Young's modulus E (GPa)
    poissons_ratio : float
        Poisson's ratio ν (dimensionless), default 0.3
    """
    yield_strength: float      # σ_ys (MPa)
    ultimate_strength: float   # σ_uts (MPa)
    youngs_modulus: float      # E (GPa)
    poissons_ratio: float = 0.3  # ν

    @property
    def flow_stress(self) -> float:
        """
        Calculate flow stress σ_f = (σ_ys + σ_uts) / 2.

        Returns
        -------
        float
            Flow stress (MPa)
        """
        return (self.yield_strength + self.ultimate_strength) / 2

    @property
    def E_prime(self) -> float:
        """
        Calculate plane strain modulus E' = E / (1 - ν²).

        Returns
        -------
        float
            Plane strain modulus (GPa)
        """
        return self.youngs_modulus / (1 - self.poissons_ratio**2)
