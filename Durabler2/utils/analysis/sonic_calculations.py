"""
Sonic Resonance (Ultrasonic) calculation engine.

Calculates elastic modulus (E), shear modulus (G), and Poisson's ratio (ν)
from ultrasonic wave velocities per modified ASTM E1875.

Theory:
- Longitudinal wave velocity: Vl = √(M / ρ) where M = E(1-ν) / ((1+ν)(1-2ν))
- Shear wave velocity: Vs = √(G / ρ)
- Relationships:
  - E = 2G(1 + ν)
  - ν = (Vl² - 2Vs²) / (2(Vl² - Vs²))
  - G = ρ × Vs²
  - E = ρ × Vs² × (3Vl² - 4Vs²) / (Vl² - Vs²)
"""

import math
from dataclasses import dataclass
from typing import Optional

from utils.models.sonic_specimen import SonicSpecimen, UltrasonicMeasurements
from utils.models.test_result import MeasuredValue


@dataclass
class SonicResults:
    """
    Container for sonic/ultrasonic test results.

    All moduli are in GPa, Poisson's ratio is dimensionless.
    Resonant frequencies in Hz per ASTM E1875.
    """
    density: MeasuredValue  # kg/m³
    longitudinal_velocity: MeasuredValue  # m/s
    shear_velocity: MeasuredValue  # m/s
    poissons_ratio: MeasuredValue  # dimensionless
    shear_modulus: MeasuredValue  # GPa
    youngs_modulus: MeasuredValue  # GPa
    flexural_frequency: MeasuredValue  # Hz - fundamental flexural resonant frequency
    torsional_frequency: MeasuredValue  # Hz - fundamental torsional resonant frequency
    is_valid: bool
    validity_notes: str


class SonicAnalyzer:
    """
    Ultrasonic velocity analysis engine.

    Calculates elastic properties from longitudinal and shear wave velocities.
    """

    def __init__(self):
        """Initialize sonic analyzer."""
        pass

    def calculate_poissons_ratio(
        self,
        vl: float,
        vs: float
    ) -> float:
        """
        Calculate Poisson's ratio from wave velocities.

        ν = (Vl² - 2Vs²) / (2(Vl² - Vs²))

        Parameters
        ----------
        vl : float
            Longitudinal wave velocity (m/s)
        vs : float
            Shear wave velocity (m/s)

        Returns
        -------
        float
            Poisson's ratio (dimensionless)
        """
        vl2 = vl ** 2
        vs2 = vs ** 2

        denominator = 2 * (vl2 - vs2)
        if abs(denominator) < 1e-10:
            return 0.0

        nu = (vl2 - 2 * vs2) / denominator
        return nu

    def calculate_shear_modulus(
        self,
        density: float,
        vs: float
    ) -> float:
        """
        Calculate shear modulus from density and shear velocity.

        G = ρ × Vs²

        Parameters
        ----------
        density : float
            Density (kg/m³)
        vs : float
            Shear wave velocity (m/s)

        Returns
        -------
        float
            Shear modulus G (Pa)
        """
        return density * vs ** 2

    def calculate_youngs_modulus_from_G_nu(
        self,
        G: float,
        nu: float
    ) -> float:
        """
        Calculate Young's modulus from shear modulus and Poisson's ratio.

        E = 2G(1 + ν)

        Parameters
        ----------
        G : float
            Shear modulus (Pa)
        nu : float
            Poisson's ratio

        Returns
        -------
        float
            Young's modulus E (Pa)
        """
        return 2 * G * (1 + nu)

    def calculate_youngs_modulus_direct(
        self,
        density: float,
        vl: float,
        vs: float
    ) -> float:
        """
        Calculate Young's modulus directly from velocities.

        E = ρ × Vs² × (3Vl² - 4Vs²) / (Vl² - Vs²)

        Parameters
        ----------
        density : float
            Density (kg/m³)
        vl : float
            Longitudinal wave velocity (m/s)
        vs : float
            Shear wave velocity (m/s)

        Returns
        -------
        float
            Young's modulus E (Pa)
        """
        vl2 = vl ** 2
        vs2 = vs ** 2

        denominator = vl2 - vs2
        if abs(denominator) < 1e-10:
            return 0.0

        E = density * vs2 * (3 * vl2 - 4 * vs2) / denominator
        return E

    def calculate_flexural_frequency(
        self,
        E_pa: float,
        density: float,
        length_m: float,
        diameter_m: float = 0,
        side_m: float = 0,
        specimen_type: str = 'round'
    ) -> float:
        """
        Calculate fundamental flexural resonant frequency per ASTM E1875.

        For cylindrical specimen (free-free vibration):
        ff = (β₁² / 2π) × √(E × I / (ρ × A × L⁴))

        where β₁ = 4.730 for fundamental mode

        Simplified for round bar:
        ff = 0.9464 × (d / L²) × √(E / ρ)

        For square bar:
        ff = 1.0279 × (t / L²) × √(E / ρ)

        Parameters
        ----------
        E_pa : float
            Young's modulus (Pa)
        density : float
            Density (kg/m³)
        length_m : float
            Specimen length (m)
        diameter_m : float
            Diameter for round specimens (m)
        side_m : float
            Side length for square specimens (m)
        specimen_type : str
            'round' or 'square'

        Returns
        -------
        float
            Fundamental flexural resonant frequency (Hz)
        """
        if E_pa <= 0 or density <= 0 or length_m <= 0:
            return 0.0

        # β₁² / (2π) ≈ 3.5608 for fundamental mode
        # For round: I/A = d²/16, so coefficient = 3.5608 × √(1/16) = 0.8902
        # For square: I/A = t²/12, so coefficient = 3.5608 × √(1/12) = 1.0279

        if specimen_type == 'round' and diameter_m > 0:
            # ff = 0.9464 × (d / L²) × √(E / ρ)
            ff = 0.9464 * (diameter_m / length_m**2) * math.sqrt(E_pa / density)
        elif specimen_type == 'square' and side_m > 0:
            # ff = 1.0279 × (t / L²) × √(E / ρ)
            ff = 1.0279 * (side_m / length_m**2) * math.sqrt(E_pa / density)
        else:
            return 0.0

        return ff

    def calculate_torsional_frequency(
        self,
        G_pa: float,
        density: float,
        length_m: float
    ) -> float:
        """
        Calculate fundamental torsional resonant frequency per ASTM E1875.

        ft = (1 / 2L) × √(G / ρ)

        Parameters
        ----------
        G_pa : float
            Shear modulus (Pa)
        density : float
            Density (kg/m³)
        length_m : float
            Specimen length (m)

        Returns
        -------
        float
            Fundamental torsional resonant frequency (Hz)
        """
        if G_pa <= 0 or density <= 0 or length_m <= 0:
            return 0.0

        ft = (1 / (2 * length_m)) * math.sqrt(G_pa / density)
        return ft

    def check_validity(
        self,
        nu: float,
        specimen: SonicSpecimen,
        measurements: UltrasonicMeasurements
    ) -> tuple:
        """
        Check validity of results.

        Parameters
        ----------
        nu : float
            Calculated Poisson's ratio
        specimen : SonicSpecimen
            Specimen data
        measurements : UltrasonicMeasurements
            Velocity measurements

        Returns
        -------
        tuple
            (is_valid, validity_notes)
        """
        notes = []
        is_valid = True

        # Check Poisson's ratio is physically meaningful
        if nu < 0:
            notes.append("Poisson's ratio is negative (unusual)")
            is_valid = False
        elif nu > 0.5:
            notes.append("Poisson's ratio > 0.5 (physically impossible)")
            is_valid = False

        # Check typical range for metals (0.25-0.35)
        if 0.2 <= nu <= 0.4:
            notes.append("Poisson's ratio within typical range for metals")
        elif 0 <= nu < 0.2:
            notes.append("Low Poisson's ratio (typical for ceramics/composites)")
        elif 0.4 < nu <= 0.5:
            notes.append("High Poisson's ratio (approaching incompressible)")

        # Check velocity ratio (Vl should be > Vs)
        if measurements.longitudinal_avg <= measurements.shear_avg:
            notes.append("Longitudinal velocity should be greater than shear velocity")
            is_valid = False

        # Check measurement consistency (CV < 5%)
        if measurements.longitudinal_avg > 0:
            cv_long = (measurements.longitudinal_std / measurements.longitudinal_avg) * 100
            if cv_long > 5:
                notes.append(f"High variation in longitudinal velocity (CV={cv_long:.1f}%)")

        if measurements.shear_avg > 0:
            cv_shear = (measurements.shear_std / measurements.shear_avg) * 100
            if cv_shear > 5:
                notes.append(f"High variation in shear velocity (CV={cv_shear:.1f}%)")

        # Check specimen dimensions
        if specimen.length < 10 * specimen.diameter if specimen.specimen_type == 'round' else specimen.length < 10 * specimen.side_length:
            notes.append("Specimen length may be short for accurate measurement")

        validity_notes = "; ".join(notes) if notes else "All checks passed"
        return is_valid, validity_notes

    def run_analysis(
        self,
        specimen: SonicSpecimen,
        measurements: UltrasonicMeasurements
    ) -> SonicResults:
        """
        Run complete ultrasonic analysis.

        Parameters
        ----------
        specimen : SonicSpecimen
            Specimen geometry and mass
        measurements : UltrasonicMeasurements
            Velocity measurements

        Returns
        -------
        SonicResults
            Complete analysis results with uncertainties
        """
        # Get average velocities
        vl = measurements.longitudinal_avg
        vs = measurements.shear_avg
        rho = specimen.density

        # Calculate elastic properties
        nu = self.calculate_poissons_ratio(vl, vs)
        G_pa = self.calculate_shear_modulus(rho, vs)
        E_pa = self.calculate_youngs_modulus_from_G_nu(G_pa, nu)

        # Convert to GPa
        G_gpa = G_pa / 1e9
        E_gpa = E_pa / 1e9

        # Calculate uncertainties
        # Density uncertainty (~0.075% standard, ±0.15% expanded k=2)
        u_rho = rho * 0.00075

        # Velocity uncertainties (~0.075% standard, ±0.15% expanded k=2)
        u_vl = vl * 0.00075
        u_vs = vs * 0.00075

        # Propagate uncertainties (simplified)
        # For G = ρ × Vs², relative uncertainty: u_G/G = √((u_ρ/ρ)² + 4(u_Vs/Vs)²)
        if G_gpa > 0 and vs > 0:
            rel_u_G = math.sqrt((u_rho/rho)**2 + 4*(u_vs/vs)**2)
            u_G = G_gpa * rel_u_G
        else:
            u_G = 0

        # For E, similar propagation
        if E_gpa > 0:
            u_E = E_gpa * 0.03  # ~3% typical
        else:
            u_E = 0

        # For ν, uncertainty depends on velocity ratio
        if vl > 0 and vs > 0:
            u_nu = 0.01  # Typical uncertainty ~0.01
        else:
            u_nu = 0

        # Calculate resonant frequencies per ASTM E1875
        # Convert dimensions to meters
        length_m = specimen.length / 1000  # mm to m
        diameter_m = specimen.diameter / 1000 if specimen.specimen_type == 'round' else 0
        side_m = specimen.side_length / 1000 if specimen.specimen_type == 'square' else 0

        # Fundamental flexural resonant frequency
        ff = self.calculate_flexural_frequency(
            E_pa, rho, length_m, diameter_m, side_m, specimen.specimen_type
        )

        # Fundamental torsional resonant frequency
        ft = self.calculate_torsional_frequency(G_pa, rho, length_m)

        # Uncertainty for frequencies (~2% typical)
        u_ff = ff * 0.02 if ff > 0 else 0
        u_ft = ft * 0.02 if ft > 0 else 0

        # Validity check
        is_valid, validity_notes = self.check_validity(nu, specimen, measurements)

        return SonicResults(
            density=MeasuredValue(
                value=round(rho, 1),
                uncertainty=round(2 * u_rho, 1),
                unit="kg/m³",
                coverage_factor=2.0
            ),
            longitudinal_velocity=MeasuredValue(
                value=round(vl, 1),
                uncertainty=round(2 * u_vl, 1),
                unit="m/s",
                coverage_factor=2.0
            ),
            shear_velocity=MeasuredValue(
                value=round(vs, 1),
                uncertainty=round(2 * u_vs, 1),
                unit="m/s",
                coverage_factor=2.0
            ),
            poissons_ratio=MeasuredValue(
                value=round(nu, 4),
                uncertainty=round(2 * u_nu, 4),
                unit="-",
                coverage_factor=2.0
            ),
            shear_modulus=MeasuredValue(
                value=round(G_gpa, 2),
                uncertainty=round(2 * u_G, 2),
                unit="GPa",
                coverage_factor=2.0
            ),
            youngs_modulus=MeasuredValue(
                value=round(E_gpa, 2),
                uncertainty=round(2 * u_E, 2),
                unit="GPa",
                coverage_factor=2.0
            ),
            flexural_frequency=MeasuredValue(
                value=round(ff, 1),
                uncertainty=round(2 * u_ff, 1),
                unit="Hz",
                coverage_factor=2.0
            ),
            torsional_frequency=MeasuredValue(
                value=round(ft, 1),
                uncertainty=round(2 * u_ft, 1),
                unit="Hz",
                coverage_factor=2.0
            ),
            is_valid=is_valid,
            validity_notes=validity_notes
        )
