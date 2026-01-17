"""
FCGR Specimen and Material Data Models for ASTM E647.

Defines dataclasses for fatigue crack growth rate testing specimens,
material properties, and test parameters.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FCGRSpecimen:
    """
    Specimen geometry for FCGR testing per ASTM E647.

    Supports C(T) Compact Tension and M(T) Middle Tension specimens.

    Attributes
    ----------
    specimen_id : str
        Specimen identifier
    specimen_type : str
        'C(T)' for Compact Tension or 'M(T)' for Middle Tension
    W : float
        Width (mm) - distance from load line to back edge for C(T)
    B : float
        Thickness (mm)
    B_n : float
        Net thickness at side grooves (mm), equals B if no grooves
    a_0 : float
        Initial notch length (mm)
    notch_height : float
        Notch height h (mm)
    material : str
        Material designation
    """
    specimen_id: str
    specimen_type: str  # 'C(T)' or 'M(T)'
    W: float            # Width (mm)
    B: float            # Thickness (mm)
    B_n: float          # Net thickness (mm)
    a_0: float          # Initial notch length (mm)
    notch_height: float = 0.0  # Notch height h (mm)
    material: str = ""

    @property
    def B_effective(self) -> float:
        """Effective thickness for side-grooved specimens."""
        if self.B_n and self.B_n < self.B:
            return math.sqrt(self.B * self.B_n)
        return self.B

    @property
    def a_W_ratio(self) -> float:
        """Initial a/W ratio."""
        return self.a_0 / self.W if self.W > 0 else 0.0

    def f_aW_CT(self, a: float) -> float:
        """
        Geometry function f(a/W) for C(T) specimen per E647.

        Parameters
        ----------
        a : float
            Current crack length (mm)

        Returns
        -------
        float
            Geometry function value
        """
        x = a / self.W
        return ((2 + x) / (1 - x)**1.5 *
                (0.886 + 4.64*x - 13.32*x**2 + 14.72*x**3 - 5.6*x**4))

    def f_aW_MT(self, a: float) -> float:
        """
        Geometry function for M(T) specimen per E647.

        Parameters
        ----------
        a : float
            Half crack length (mm)

        Returns
        -------
        float
            Geometry function value (secant correction)
        """
        x = a / self.W
        return 1 / math.sqrt(math.cos(math.pi * x / 2))

    def calculate_delta_K(self, delta_P: float, a: float) -> float:
        """
        Calculate stress intensity factor range Delta-K.

        Parameters
        ----------
        delta_P : float
            Load range (kN)
        a : float
            Current crack length (mm)

        Returns
        -------
        float
            Delta-K in MPa*sqrt(m)
        """
        # Convert units: P in kN, dimensions in mm -> K in MPa*sqrt(m)
        # K = P / (B * sqrt(W)) * f(a/W)
        # With P in N and dimensions in m: K in Pa*sqrt(m)
        # We want MPa*sqrt(m), so: K = P[kN] * 1000 / (B[mm]/1000 * sqrt(W[mm]/1000)) * f(a/W)
        # Simplify: K = P[kN] * 1000 * sqrt(1000) / (B[mm] * sqrt(W[mm])) * f(a/W)
        # K = P * 31.623 / (B * sqrt(W)) * f(a/W)

        if self.specimen_type == 'C(T)':
            f_aW = self.f_aW_CT(a)
        else:  # M(T)
            f_aW = self.f_aW_MT(a)

        delta_K = delta_P * 1000 / (self.B_effective * math.sqrt(self.W)) * f_aW
        # Convert from kPa*sqrt(mm) to MPa*sqrt(m)
        delta_K = delta_K / 1000 * math.sqrt(1000)

        return delta_K

    def validate_geometry(self) -> tuple:
        """
        Validate specimen geometry per E647 requirements.

        Returns
        -------
        tuple
            (is_valid, list of validation messages)
        """
        messages = []
        is_valid = True

        # Check a0 >= 0.2W
        if self.a_0 < 0.2 * self.W:
            messages.append(f"a0/W = {self.a_0/self.W:.3f} < 0.2: FAIL")
            is_valid = False
        else:
            messages.append(f"a0/W = {self.a_0/self.W:.3f} >= 0.2: PASS")

        # Check B_n <= B
        if self.B_n > self.B:
            messages.append(f"Bn ({self.B_n:.2f}) > B ({self.B:.2f}): FAIL")
            is_valid = False

        return is_valid, messages


@dataclass
class FCGRMaterial:
    """
    Material properties for FCGR testing.

    Attributes
    ----------
    yield_strength : float
        0.2% offset yield strength (MPa)
    ultimate_strength : float
        Ultimate tensile strength (MPa)
    youngs_modulus : float
        Young's modulus (GPa)
    poissons_ratio : float
        Poisson's ratio (default 0.3)
    """
    yield_strength: float      # sigma_ys (MPa)
    ultimate_strength: float   # sigma_uts (MPa)
    youngs_modulus: float      # E (GPa)
    poissons_ratio: float = 0.3


@dataclass
class FCGRTestParameters:
    """
    Test parameters for FCGR testing per E647.

    Attributes
    ----------
    control_mode : str
        'Load Control' or 'Delta-K Control'
    load_ratio : float
        R ratio = Pmin/Pmax
    frequency : float
        Test frequency (Hz)
    wave_shape : str
        Waveform type (e.g., 'Sine', 'Triangle')
    environment : str
        Test environment description
    temperature : float
        Test temperature (C)
    """
    control_mode: str = "Load Control"
    load_ratio: float = 0.1
    frequency: float = 10.0
    wave_shape: str = "Sine"
    environment: str = "Laboratory Air"
    temperature: float = 23.0

    # K-decreasing test parameters
    normalized_k_gradient: float = 0.0  # C value (1/mm)
    initial_delta_k: float = 0.0        # Initial Delta-K for K-control

    # Data processing parameters
    upper_fit_percentage: float = 80.0
    lower_fit_percentage: float = 20.0


@dataclass
class FCGRDataPoint:
    """
    Single data point for FCGR analysis.

    Attributes
    ----------
    cycle_count : int
        Number of cycles N
    crack_length : float
        Crack length a (mm)
    delta_K : float
        Stress intensity range (MPa*sqrt(m))
    da_dN : float
        Crack growth rate (mm/cycle)
    P_max : float
        Maximum load (kN)
    P_min : float
        Minimum load (kN)
    compliance : float
        Specimen compliance (mm/kN)
    """
    cycle_count: int
    crack_length: float
    delta_K: float = 0.0
    da_dN: float = 0.0
    P_max: float = 0.0
    P_min: float = 0.0
    compliance: float = 0.0
    is_valid: bool = True
    is_outlier: bool = False


@dataclass
class ParisLawResult:
    """
    Results from Paris law regression.

    da/dN = C * (Delta-K)^m

    Attributes
    ----------
    C : float
        Paris law coefficient C
    m : float
        Paris law exponent m
    r_squared : float
        Coefficient of determination R^2
    n_points : int
        Number of data points used in fit
    delta_K_range : tuple
        (min, max) Delta-K range used for fit
    da_dN_range : tuple
        (min, max) da/dN range used for fit
    """
    C: float
    m: float
    r_squared: float
    n_points: int
    delta_K_range: tuple = (0.0, 0.0)
    da_dN_range: tuple = (0.0, 0.0)
    std_error_C: float = 0.0
    std_error_m: float = 0.0


@dataclass
class FCGRResult:
    """
    Complete results from FCGR analysis.

    Attributes
    ----------
    data_points : List[FCGRDataPoint]
        All processed data points
    paris_law : ParisLawResult
        Paris law fit results (after outlier removal)
    paris_law_initial : ParisLawResult
        Paris law fit results from all data (before outlier removal)
    threshold_delta_K : float
        Threshold Delta-K (if determined)
    final_crack_length : float
        Final crack length (mm)
    total_cycles : int
        Total number of cycles
    is_valid : bool
        Overall validity per E647
    validity_notes : List[str]
        Detailed validity check results
    """
    data_points: List[FCGRDataPoint]
    paris_law: ParisLawResult
    paris_law_initial: Optional[ParisLawResult] = None
    threshold_delta_K: float = 0.0
    final_crack_length: float = 0.0
    total_cycles: int = 0
    is_valid: bool = True
    validity_notes: List[str] = field(default_factory=list)

    @property
    def valid_points(self) -> List[FCGRDataPoint]:
        """Return only valid (non-outlier) data points."""
        return [p for p in self.data_points if p.is_valid and not p.is_outlier]

    @property
    def n_valid_points(self) -> int:
        """Number of valid data points."""
        return len(self.valid_points)

    @property
    def n_outliers(self) -> int:
        """Number of outlier points."""
        return sum(1 for p in self.data_points if p.is_outlier)
