"""Goldak double-ellipsoid heat source with 2D cross-section FD solver.

Implements the Goldak double-ellipsoid model on a y-z (transverse × depth)
cross-section, integrating the 3D source term over x analytically.

The Goldak 3D heat distribution:
    q_f(x,y,z) = (6√3 f_f Q) / (a_f b c π√π) exp(-3x²/a_f² - 3y²/b² - 3z²/c²)
    q_r(x,y,z) = (6√3 f_r Q) / (a_r b c π√π) exp(-3x²/a_r² - 3y²/b² - 3z²/c²)

where f_f + f_r = 2 and the front/rear ellipsoids share the (y,z) Gaussian.

The 2D cross-section solver integrates over x using erf(), solving the heat
equation in y-z via ADI (Alternating Direction Implicit) finite differences.

References:
- Goldak J., Chakravarti A., Bibby M., "A New Finite Element Model
  for Welding Heat Sources", Metallurgical Transactions B, 1984
- Lindgren L.-E., "Numerical modelling of welding", CMES, 2006
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, List
import time as time_module
import numpy as np
from scipy.special import erf
from scipy.linalg import solve_banded

from .rosenthal_solver import (
    ARC_EFFICIENCIES, DEFAULT_CONDUCTIVITY, DEFAULT_DENSITY, DEFAULT_SPECIFIC_HEAT,
)


# Stefan-Boltzmann constant (W/(m²·K⁴))
STEFAN_BOLTZMANN = 5.67e-8

# Default surface heat transfer
DEFAULT_EMISSIVITY = 0.7
DEFAULT_CONVECTION_HTC = 15.0  # W/(m²·K) — natural convection in air

# Solidus temperature cap
SOLIDUS_TEMP = 1500.0


@dataclass
class GoldakParams:
    """Parameters for Goldak double-ellipsoid heat source.

    Attributes
    ----------
    Q : float
        Net arc power (W) = eta × V × I
    v : float
        Travel speed (m/s)
    a_f : float
        Front semi-axis in weld direction (m)
    a_r : float
        Rear semi-axis in weld direction (m)
    b : float
        Half-width of weld pool (m)
    c : float
        Penetration depth (m)
    f_f : float
        Front energy fraction (default 0.6)
    f_r : float
        Rear energy fraction (default 1.4, f_f + f_r = 2)
    T0 : float
        Initial / preheat temperature (°C)
    k : float
        Thermal conductivity W/(m·K)
    rho : float
        Density kg/m³
    Cp : float
        Specific heat J/(kg·K)
    eta : float
        Arc efficiency (0–1)
    plate_thickness : float
        Plate thickness (m), defines z-domain
    plate_half_width : float
        Half-width of domain in y (m)
    emissivity : float
        Surface emissivity for radiation BC
    h_conv : float
        Convective HTC for surface BC W/(m²·K)
    """
    Q: float = 3000.0
    v: float = 0.005
    a_f: float = 0.004
    a_r: float = 0.008
    b: float = 0.004
    c: float = 0.003
    f_f: float = 0.6
    f_r: float = 1.4
    T0: float = 20.0
    k: float = DEFAULT_CONDUCTIVITY
    rho: float = DEFAULT_DENSITY
    Cp: float = DEFAULT_SPECIFIC_HEAT
    eta: float = 0.80
    plate_thickness: float = 0.020
    plate_half_width: float = 0.030
    emissivity: float = DEFAULT_EMISSIVITY
    h_conv: float = DEFAULT_CONVECTION_HTC

    @property
    def alpha(self) -> float:
        """Thermal diffusivity (m²/s)."""
        return self.k / (self.rho * self.Cp)


@dataclass
class GoldakSolverConfig:
    """2D FD solver configuration.

    Attributes
    ----------
    ny : int
        Grid points in y-direction (transverse), must be odd for center node
    nz : int
        Grid points in z-direction (depth)
    dt : float
        Time step (s)
    total_time : float
        Simulation duration (s)
    theta : float
        Crank-Nicolson parameter (0.5 = CN, 1.0 = fully implicit)
    convergence_tol : float
        Nonlinear iteration tolerance (°C)
    max_iterations : int
        Max nonlinear iterations per time step
    output_interval : int
        Store snapshot every N steps
    """
    ny: int = 41
    nz: int = 31
    dt: float = 0.05
    total_time: float = 120.0
    theta: float = 0.5
    convergence_tol: float = 1.0
    max_iterations: int = 20
    output_interval: int = 20


# Probe point definitions (name -> (y_fraction_of_half_width, z_fraction_of_thickness))
PROBE_POINTS = {
    'center': (0.0, 0.0),
    'surface_2mm': (0.002, 0.0),   # 2mm from weld line, surface
    'surface_5mm': (0.005, 0.0),   # 5mm from weld line
    'surface_10mm': (0.010, 0.0),  # 10mm
    'mid_depth_center': (0.0, 0.5),  # centerline at mid-depth
}


@dataclass
class GoldakResult:
    """Result from Goldak 2D cross-section solver.

    Attributes
    ----------
    y_coords : np.ndarray
        Transverse coordinates (m), shape (ny,)
    z_coords : np.ndarray
        Depth coordinates (m), shape (nz,)
    times : np.ndarray
        Stored snapshot times (s)
    temperature_field : np.ndarray
        Temperature at stored snapshots, shape (n_snapshots, nz, ny)
    peak_temperature_map : np.ndarray
        Max temperature at each (z, y), shape (nz, ny)
    probe_thermal_cycles : dict
        {name: {'times': list, 'temps': list}}
    t8_5_map : np.ndarray
        t8/5 cooling time at each point (s), 0 if not applicable, shape (nz, ny)
    weld_pool_boundary : dict
        {'y_mm': list, 'z_mm': list} solidus isotherm
    fusion_zone_area_mm2 : float
        Area of fusion zone in cross-section
    goldak_params : dict
        Parameters used (for display)
    solver_info : dict
        Timing, grid, convergence stats
    """
    y_coords: np.ndarray
    z_coords: np.ndarray
    times: np.ndarray
    temperature_field: np.ndarray
    peak_temperature_map: np.ndarray
    probe_thermal_cycles: dict
    t8_5_map: np.ndarray
    weld_pool_boundary: dict
    fusion_zone_area_mm2: float
    goldak_params: dict
    solver_info: dict

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            'y_coords': (self.y_coords * 1000).tolist(),  # mm
            'z_coords': (self.z_coords * 1000).tolist(),   # mm
            'times': self.times.tolist(),
            'temperature_field': self.temperature_field.tolist(),
            'peak_temperature_map': self.peak_temperature_map.tolist(),
            'probe_thermal_cycles': self.probe_thermal_cycles,
            't8_5_map': self.t8_5_map.tolist(),
            'weld_pool_boundary': self.weld_pool_boundary,
            'fusion_zone_area_mm2': self.fusion_zone_area_mm2,
            'goldak_params': self.goldak_params,
            'solver_info': self.solver_info,
            # Surface-line summaries for HAZ comparison
            'surface_peak_temps': self.peak_temperature_map[0, :].tolist(),
            'surface_distances_mm': (self.y_coords * 1000).tolist(),
        }

    @property
    def surface_peak_profile(self) -> Tuple[np.ndarray, np.ndarray]:
        """Peak temperature along surface (z=0) vs transverse distance."""
        return self.y_coords * 1000, self.peak_temperature_map[0, :]

    @property
    def center_t8_5(self) -> Optional[float]:
        """t8/5 at weld center (y=0, z=0)."""
        ny_mid = len(self.y_coords) // 2
        val = self.t8_5_map[0, ny_mid]
        return float(val) if val > 0 else None


class GoldakSolver:
    """2D cross-section FD solver with Goldak double-ellipsoid heat source.

    Solves the transient 2D heat equation:
        ρCp ∂T/∂t = ∂/∂y(k ∂T/∂y) + ∂/∂z(k ∂T/∂z) + q(y,z,t)

    where q(y,z,t) is the Goldak source integrated over x.
    Uses ADI (Alternating Direction Implicit) splitting for efficiency.
    """

    def __init__(self, params: GoldakParams,
                 config: Optional[GoldakSolverConfig] = None):
        self.params = params
        self.config = config or GoldakSolverConfig()

        # Ensure ny is odd (so there's a center node at y=0)
        if self.config.ny % 2 == 0:
            self.config.ny += 1

        # Create mesh
        self.y = np.linspace(-params.plate_half_width, params.plate_half_width,
                             self.config.ny)
        self.z = np.linspace(0, params.plate_thickness, self.config.nz)
        self.dy = self.y[1] - self.y[0]
        self.dz = self.z[1] - self.z[0]

        # Precompute Gaussian y-z envelope (does not change with time)
        Y, Z = np.meshgrid(self.y, self.z)  # shapes (nz, ny)
        self._yz_envelope = np.exp(-3.0 * Y**2 / params.b**2
                                   - 3.0 * Z**2 / params.c**2)

        # Front/rear amplitude coefficients (after x-integration)
        # Integration of exp(-3x²/a²) from -inf to +inf = a*sqrt(π/3)
        # But we use partial integrals with erf, so store the per-unit coefficient
        sqrt3 = np.sqrt(3.0)
        pi_sqrt_pi = np.pi * np.sqrt(np.pi)
        self._C_f = (6.0 * sqrt3 * params.f_f * params.Q) / (
            params.a_f * params.b * params.c * pi_sqrt_pi)
        self._C_r = (6.0 * sqrt3 * params.f_r * params.Q) / (
            params.a_r * params.b * params.c * pi_sqrt_pi)

    @classmethod
    def from_weld_project(cls, project, string=None,
                          config: Optional[GoldakSolverConfig] = None,
                          b_override: Optional[float] = None,
                          c_override: Optional[float] = None,
                          a_f_override: Optional[float] = None,
                          a_r_override: Optional[float] = None) -> 'GoldakSolver':
        """Create solver from WeldProject and optional WeldString.

        Auto-estimates pool geometry from heat input if overrides not given.
        """
        process_type = project.process_type or 'mig_mag'
        eta = ARC_EFFICIENCIES.get(process_type, 0.80)

        if string:
            heat_input_kj_mm = string.effective_heat_input
            travel_speed_mm_s = string.effective_travel_speed
        else:
            heat_input_kj_mm = project.default_heat_input
            travel_speed_mm_s = project.default_travel_speed

        v = travel_speed_mm_s / 1000.0
        Q = eta * heat_input_kj_mm * travel_speed_mm_s * 1000.0

        # Material properties
        k = DEFAULT_CONDUCTIVITY
        rho = DEFAULT_DENSITY
        Cp = DEFAULT_SPECIFIC_HEAT

        if project.steel_grade:
            grade = project.steel_grade
            try:
                k_val = grade.get_property('thermal_conductivity')
                if k_val:
                    k = float(k_val)
            except (AttributeError, TypeError):
                pass
            try:
                rho_val = grade.get_property('density')
                if rho_val:
                    rho = float(rho_val)
            except (AttributeError, TypeError):
                pass
            try:
                cp_val = grade.get_property('specific_heat')
                if cp_val:
                    Cp = float(cp_val)
            except (AttributeError, TypeError):
                pass

        # Estimate pool geometry
        pool = estimate_pool_params(heat_input_kj_mm, process_type)
        b = b_override if b_override else pool['b']
        c = c_override if c_override else pool['c']
        a_f = a_f_override if a_f_override else pool['a_f']
        a_r = a_r_override if a_r_override else pool['a_r']

        T0 = project.preheat_temperature or 20.0

        params = GoldakParams(
            Q=Q, v=v, a_f=a_f, a_r=a_r, b=b, c=c,
            T0=T0, k=k, rho=rho, Cp=Cp, eta=eta,
            plate_thickness=0.020,
            plate_half_width=0.030,
        )
        return cls(params, config)

    def _goldak_source_2d(self, t: float) -> np.ndarray:
        """Compute 2D volumetric heat source q(y,z) at time t.

        Integrates the 3D Goldak distribution over x analytically.
        At time t the torch center is at x_torch = v * (t - t_approach).
        The cross-section is at x = 0.

        The x-relative position of the torch: x_rel = v*t - v*t_approach
        For the front (x > torch): integral from torch to +inf
        For the rear  (x < torch): integral from -inf to torch

        After integration, the 2D source is:
            q_2d(y,z,t) = [C_f * I_f(t) + C_r * I_r(t)] * exp(-3y²/b² - 3z²/c²)

        where I_f and I_r involve erf() of the torch position relative to the section.

        Returns shape (nz, ny).
        """
        p = self.params

        # Time when torch center passes through the cross-section
        t_pass = self.config.total_time * 0.15

        # Torch position relative to section (m)
        # Positive = torch has passed the section (is ahead)
        x_torch = p.v * (t - t_pass)

        # Front integral: from max(0, x_torch) to +inf of exp(-3(x-x_torch)²/a_f²)
        # = (a_f/2) * sqrt(π/3) * erfc(sqrt(3)*max(0,-x_torch)/a_f)
        # But with the split at x=0 (the section plane):
        #
        # The section is at x=0. The Goldak front (x > x_torch) and rear (x < x_torch).
        #
        # Contribution at x=0 from the front ellipsoid (applies when 0 > x_torch, i.e. torch behind section):
        #   integral_{x_torch}^{0} C_f * exp(-3*(x-x_torch)²/a_f²) dx  (if x_torch < 0)
        #   = 0 (if x_torch >= 0, the section is in the rear zone)
        #
        # More precisely, for a point at x=0:
        # - If 0 >= x_torch (torch at or behind section), point is in front ellipsoid
        # - If 0 < x_torch  (torch ahead of section), point is in rear ellipsoid
        #
        # The volumetric power density at (0, y, z) is:
        #   If 0 >= x_torch (section is in front or at torch):
        #       q = C_f * exp(-3*(0-x_torch)²/a_f²) * envelope(y,z)
        #   If 0 < x_torch (section is behind torch):
        #       q = C_r * exp(-3*(0-x_torch)²/a_r²) * envelope(y,z)

        # Actually, the correct 2D cross-section approach integrates over the
        # *line* of heat input as it sweeps through. Since the torch moves at
        # speed v, at any instant the point source is at a single x. But the
        # cross-section at x=0 sees a time history of deposited heat.
        #
        # For the FD approach, we simply evaluate the 3D Goldak at x=0 at each t:
        dx = -x_torch  # = 0 - x_torch (distance from torch to section in x)

        if dx >= 0:
            # Section is ahead of or at the torch → front ellipsoid
            q_line = self._C_f * np.exp(-3.0 * dx**2 / p.a_f**2)
        else:
            # Section is behind the torch → rear ellipsoid
            q_line = self._C_r * np.exp(-3.0 * dx**2 / p.a_r**2)

        # Full 2D source = q_line * yz_envelope
        return q_line * self._yz_envelope

    def _solve_tridiag(self, lower: np.ndarray, main: np.ndarray,
                       upper: np.ndarray, rhs: np.ndarray) -> np.ndarray:
        """Solve tridiagonal system using scipy's banded solver.

        Parameters
        ----------
        lower, main, upper : 1D arrays of length n
            lower[0] and upper[-1] are unused
        rhs : 1D array of length n
        """
        n = len(main)
        ab = np.zeros((3, n))
        ab[0, 1:] = upper[:-1]   # superdiagonal
        ab[1, :] = main           # diagonal
        ab[2, :-1] = lower[1:]   # subdiagonal
        return solve_banded((1, 1), ab, rhs)

    def _build_y_system(self, T_row: np.ndarray, T_new_row: np.ndarray,
                        q_row: np.ndarray, k_arr: np.ndarray,
                        alpha_arr: np.ndarray,
                        dt_half: float, theta: float) -> Tuple[np.ndarray, ...]:
        """Build tridiagonal system for one row (fixed z) in y-direction.

        Returns (lower, main, upper, rhs) arrays of length ny.
        """
        ny = len(T_row)
        dy = self.dy
        Fo = alpha_arr * dt_half / dy**2

        lower = np.zeros(ny)
        main = np.zeros(ny)
        upper = np.zeros(ny)
        rhs = np.zeros(ny)

        # Interior nodes
        for i in range(1, ny - 1):
            Fo_i = Fo[i]
            main[i] = 1.0 + 2.0 * theta * Fo_i
            lower[i] = -theta * Fo_i
            upper[i] = -theta * Fo_i
            rhs[i] = (T_row[i]
                       + (1.0 - theta) * Fo_i * (T_row[i-1] - 2*T_row[i] + T_row[i+1])
                       + dt_half * q_row[i] / (self.params.rho * self.params.Cp))

        # Left boundary (y = -y_max): convection + radiation
        h_eff_l = self._linearized_htc(T_new_row[0])
        Bi_l = h_eff_l * dy / k_arr[0]
        Fo_l = Fo[0]
        main[0] = 1.0 + theta * (2.0 * Fo_l + 2.0 * Fo_l * Bi_l)
        upper[0] = -2.0 * theta * Fo_l
        rhs[0] = (T_row[0]
                  + (1.0 - theta) * (2.0 * Fo_l * (T_row[1] - T_row[0])
                                     + 2.0 * Fo_l * Bi_l * (self.params.T0 - T_row[0]))
                  + 2.0 * theta * Fo_l * Bi_l * self.params.T0
                  + dt_half * q_row[0] / (self.params.rho * self.params.Cp))

        # Right boundary (y = +y_max): convection + radiation
        h_eff_r = self._linearized_htc(T_new_row[-1])
        Bi_r = h_eff_r * dy / k_arr[-1]
        Fo_r = Fo[-1]
        main[-1] = 1.0 + theta * (2.0 * Fo_r + 2.0 * Fo_r * Bi_r)
        lower[-1] = -2.0 * theta * Fo_r
        rhs[-1] = (T_row[-1]
                   + (1.0 - theta) * (2.0 * Fo_r * (T_row[-2] - T_row[-1])
                                      + 2.0 * Fo_r * Bi_r * (self.params.T0 - T_row[-1]))
                   + 2.0 * theta * Fo_r * Bi_r * self.params.T0
                   + dt_half * q_row[-1] / (self.params.rho * self.params.Cp))

        return lower, main, upper, rhs

    def _build_z_system(self, T_col: np.ndarray, T_new_col: np.ndarray,
                        q_col: np.ndarray, k_arr: np.ndarray,
                        alpha_arr: np.ndarray,
                        dt_half: float, theta: float) -> Tuple[np.ndarray, ...]:
        """Build tridiagonal system for one column (fixed y) in z-direction.

        Returns (lower, main, upper, rhs) arrays of length nz.
        """
        nz = len(T_col)
        dz = self.dz
        Fo = alpha_arr * dt_half / dz**2

        lower = np.zeros(nz)
        main = np.zeros(nz)
        upper = np.zeros(nz)
        rhs = np.zeros(nz)

        # Interior nodes
        for i in range(1, nz - 1):
            Fo_i = Fo[i]
            main[i] = 1.0 + 2.0 * theta * Fo_i
            lower[i] = -theta * Fo_i
            upper[i] = -theta * Fo_i
            rhs[i] = (T_col[i]
                       + (1.0 - theta) * Fo_i * (T_col[i-1] - 2*T_col[i] + T_col[i+1])
                       + dt_half * q_col[i] / (self.params.rho * self.params.Cp))

        # Top surface (z=0): convection + radiation to air
        h_eff_top = self._linearized_htc(T_new_col[0])
        Bi_top = h_eff_top * dz / k_arr[0]
        Fo_top = Fo[0]
        main[0] = 1.0 + theta * (2.0 * Fo_top + 2.0 * Fo_top * Bi_top)
        upper[0] = -2.0 * theta * Fo_top
        rhs[0] = (T_col[0]
                  + (1.0 - theta) * (2.0 * Fo_top * (T_col[1] - T_col[0])
                                     + 2.0 * Fo_top * Bi_top * (self.params.T0 - T_col[0]))
                  + 2.0 * theta * Fo_top * Bi_top * self.params.T0
                  + dt_half * q_col[0] / (self.params.rho * self.params.Cp))

        # Bottom (z=z_max): adiabatic (symmetry or thick plate)
        Fo_bot = Fo[-1]
        main[-1] = 1.0 + 2.0 * theta * Fo_bot
        lower[-1] = -2.0 * theta * Fo_bot
        rhs[-1] = (T_col[-1]
                   + 2.0 * (1.0 - theta) * Fo_bot * (T_col[-2] - T_col[-1])
                   + dt_half * q_col[-1] / (self.params.rho * self.params.Cp))

        return lower, main, upper, rhs

    def _linearized_htc(self, T_surface: float) -> float:
        """Linearized effective HTC (convection + radiation)."""
        p = self.params
        T_s = T_surface + 273.15  # K
        T_amb = p.T0 + 273.15
        h_rad = 0.0
        if T_s > 0 and T_amb > 0:
            h_rad = p.emissivity * STEFAN_BOLTZMANN * (T_s**2 + T_amb**2) * (T_s + T_amb)
        return p.h_conv + h_rad

    def _time_step_adi(self, T: np.ndarray, q_source: np.ndarray) -> np.ndarray:
        """Advance temperature field by one full time step using ADI.

        Half-step 1: implicit in y, explicit z contribution in source
        Half-step 2: implicit in z, explicit y contribution

        Parameters
        ----------
        T : np.ndarray, shape (nz, ny)
            Current temperature field
        q_source : np.ndarray, shape (nz, ny)
            Volumetric heat source (W/m³)

        Returns
        -------
        np.ndarray, shape (nz, ny)
            Updated temperature field
        """
        p = self.params
        dt = self.config.dt
        theta = self.config.theta
        dt_half = dt / 2.0
        nz, ny = T.shape

        # Use constant properties for stability (temperature-dependent later)
        k_const = p.k
        alpha_const = p.alpha

        # --- Half-step 1: implicit in y ---
        T_half = np.copy(T)
        k_arr_y = np.full(ny, k_const)
        alpha_arr_y = np.full(ny, alpha_const)

        for j in range(nz):
            lower, main, upper, rhs = self._build_y_system(
                T[j, :], T_half[j, :], q_source[j, :],
                k_arr_y, alpha_arr_y, dt_half, theta
            )
            T_half[j, :] = self._solve_tridiag(lower, main, upper, rhs)

        # --- Half-step 2: implicit in z ---
        T_new = np.copy(T_half)
        k_arr_z = np.full(nz, k_const)
        alpha_arr_z = np.full(nz, alpha_const)

        for i in range(ny):
            lower, main, upper, rhs = self._build_z_system(
                T_half[:, i], T_new[:, i], q_source[:, i],
                k_arr_z, alpha_arr_z, dt_half, theta
            )
            T_new[:, i] = self._solve_tridiag(lower, main, upper, rhs)

        # Cap at solidus
        T_new = np.minimum(T_new, SOLIDUS_TEMP)

        return T_new

    def solve(self, initial_field: Optional[np.ndarray] = None,
              progress_callback=None) -> GoldakResult:
        """Run the full 2D transient simulation.

        Parameters
        ----------
        initial_field : np.ndarray, optional
            Initial temperature (nz, ny). If None, uniform T0.
        progress_callback : callable, optional
            Called with (fraction_complete,) at each output step.

        Returns
        -------
        GoldakResult
        """
        cfg = self.config
        p = self.params
        ny = cfg.ny
        nz = cfg.nz
        n_steps = int(cfg.total_time / cfg.dt)

        # Initial temperature field
        if initial_field is not None:
            T = initial_field.copy()
        else:
            T = np.full((nz, ny), p.T0)

        # Storage
        n_snapshots = n_steps // cfg.output_interval + 1
        stored_fields = np.zeros((n_snapshots, nz, ny))
        stored_times = np.zeros(n_snapshots)
        stored_fields[0] = T.copy()
        stored_times[0] = 0.0
        snap_idx = 1

        # Peak temperature tracking
        peak_map = T.copy()

        # Probe thermal cycle tracking
        probe_indices = {}
        for name, (y_abs, z_frac) in PROBE_POINTS.items():
            iy = np.argmin(np.abs(self.y - y_abs))
            if z_frac < 1.0:
                iz = int(z_frac * (nz - 1))
            else:
                iz = nz - 1
            probe_indices[name] = (iz, iy)

        probe_times = {name: [] for name in PROBE_POINTS}
        probe_temps = {name: [] for name in PROBE_POINTS}

        # Record initial probe values
        for name, (iz, iy) in probe_indices.items():
            probe_times[name].append(0.0)
            probe_temps[name].append(float(T[iz, iy]))

        # Time history for t8/5 calculation
        # Store full time series at each grid point (memory: nz*ny*n_steps floats)
        # Too much memory for large grids. Instead, track crossing times.
        t800_map = np.full((nz, ny), -1.0)  # time of 800°C crossing (cooling)
        t500_map = np.full((nz, ny), -1.0)  # time of 500°C crossing (cooling)
        was_above_800 = T > 800  # bool array

        wall_start = time_module.time()

        # Time-stepping loop
        for step in range(1, n_steps + 1):
            t = step * cfg.dt

            # Compute heat source at this time
            q_source = self._goldak_source_2d(t)

            # ADI time step
            T_old = T.copy()
            T = self._time_step_adi(T, q_source)

            # Update peak temperature
            peak_map = np.maximum(peak_map, T)

            # Track t8/5 crossing times
            # Cooling: was above 800 in previous step, now below
            cooling_800 = (T_old >= 800) & (T < 800)
            t800_map = np.where(cooling_800 & (t800_map < 0), t, t800_map)

            cooling_500 = (T_old >= 500) & (T < 500)
            t500_map = np.where(cooling_500 & (t500_map < 0), t, t500_map)

            # Record probe values (every step for thermal cycle accuracy)
            if step % max(1, cfg.output_interval // 4) == 0:
                for name, (iz, iy) in probe_indices.items():
                    probe_times[name].append(float(t))
                    probe_temps[name].append(float(T[iz, iy]))

            # Store snapshot
            if step % cfg.output_interval == 0 and snap_idx < n_snapshots:
                stored_fields[snap_idx] = T.copy()
                stored_times[snap_idx] = t
                snap_idx += 1

                if progress_callback:
                    progress_callback(step / n_steps)

        wall_time = time_module.time() - wall_start

        # Trim stored arrays
        stored_fields = stored_fields[:snap_idx]
        stored_times = stored_times[:snap_idx]

        # Compute t8/5 map
        t8_5_map = np.zeros((nz, ny))
        valid = (t800_map > 0) & (t500_map > 0) & (t500_map > t800_map)
        t8_5_map[valid] = t500_map[valid] - t800_map[valid]

        # Extract weld pool boundary (solidus isotherm from peak temp map)
        pool_boundary = self._extract_pool_boundary(peak_map)

        # Fusion zone area
        cell_area = self.dy * self.dz * 1e6  # mm²
        fz_area = float(np.sum(peak_map >= SOLIDUS_TEMP) * cell_area)

        # Build probe thermal cycles dict
        probe_cycles = {}
        for name in PROBE_POINTS:
            probe_cycles[name] = {
                'times': probe_times[name],
                'temps': probe_temps[name],
            }

        # Goldak params summary
        params_dict = {
            'Q_W': p.Q,
            'v_mm_s': p.v * 1000,
            'a_f_mm': p.a_f * 1000,
            'a_r_mm': p.a_r * 1000,
            'b_mm': p.b * 1000,
            'c_mm': p.c * 1000,
            'f_f': p.f_f,
            'f_r': p.f_r,
            'T0_C': p.T0,
            'k': p.k,
            'rho': p.rho,
            'Cp': p.Cp,
            'eta': p.eta,
        }

        solver_info = {
            'ny': ny,
            'nz': nz,
            'dt': cfg.dt,
            'total_time': cfg.total_time,
            'n_steps': n_steps,
            'n_snapshots': snap_idx,
            'wall_time_s': round(wall_time, 2),
        }

        return GoldakResult(
            y_coords=self.y,
            z_coords=self.z,
            times=stored_times,
            temperature_field=stored_fields,
            peak_temperature_map=peak_map,
            probe_thermal_cycles=probe_cycles,
            t8_5_map=t8_5_map,
            weld_pool_boundary=pool_boundary,
            fusion_zone_area_mm2=fz_area,
            goldak_params=params_dict,
            solver_info=solver_info,
        )

    def _extract_pool_boundary(self, peak_map: np.ndarray) -> dict:
        """Extract the solidus isotherm boundary from peak temperature map.

        Returns dict with 'y_mm' and 'z_mm' lists defining the contour.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            cs = ax.contour(self.y * 1000, self.z * 1000, peak_map,
                           levels=[SOLIDUS_TEMP])
            boundary_y = []
            boundary_z = []
            for seg in cs.allsegs[0]:
                boundary_y.extend(seg[:, 0].tolist())
                boundary_z.extend(seg[:, 1].tolist())
            plt.close(fig)
            return {'y_mm': boundary_y, 'z_mm': boundary_z}
        except Exception:
            return {'y_mm': [], 'z_mm': []}

    def extract_haz_from_field(self) -> dict:
        """Extract HAZ zone data from a solved result's peak temperature map.

        Compatible with HAZResult-style output for comparison with Rosenthal.
        Uses the surface (z=0) peak temperature profile.
        """
        peak_surface = self.solve_result.peak_temperature_map[0, :] if hasattr(self, 'solve_result') else None
        if peak_surface is None:
            return {}

        distances_mm = self.y * 1000
        # Only use positive y (right side)
        ny_mid = len(self.y) // 2
        dist_right = distances_mm[ny_mid:]
        temps_right = peak_surface[ny_mid:]

        # Find zone boundaries by interpolation
        boundaries = {}
        zone_temps = {'fusion': SOLIDUS_TEMP, 'cghaz': 1100.0, 'fghaz': 900.0, 'ichaz': 727.0}
        for zone_name, target_temp in zone_temps.items():
            idx = np.where(temps_right < target_temp)[0]
            if len(idx) > 0 and idx[0] > 0:
                # Linear interpolation
                i = idx[0]
                frac = (target_temp - temps_right[i]) / (temps_right[i-1] - temps_right[i])
                boundaries[zone_name] = float(dist_right[i] - frac * (dist_right[i] - dist_right[i-1]))
            else:
                boundaries[zone_name] = 0.0

        fz_w = boundaries.get('fusion', 0)
        cghaz_b = boundaries.get('cghaz', 0)
        fghaz_b = boundaries.get('fghaz', 0)
        ichaz_b = boundaries.get('ichaz', 0)

        return {
            'fusion_zone_width': fz_w,
            'cghaz_width': max(0, cghaz_b - fz_w),
            'fghaz_width': max(0, fghaz_b - cghaz_b),
            'ichaz_width': max(0, ichaz_b - fghaz_b),
            'total_haz_width': max(0, ichaz_b - fz_w),
            'zone_boundaries': boundaries,
            'distances_mm': dist_right.tolist(),
            'peak_temperatures': temps_right.tolist(),
        }


def estimate_pool_params(heat_input_kj_mm: float, process_type: str) -> dict:
    """Estimate Goldak ellipsoid parameters from heat input and process.

    Uses empirical correlations based on published data:
    - Weld pool width scales with sqrt(heat_input)
    - Penetration depends on process type
    - Front/rear aspect ratios are typical defaults

    Parameters
    ----------
    heat_input_kj_mm : float
        Heat input (kJ/mm)
    process_type : str
        Welding process (gtaw, mig_mag, saw, smaw)

    Returns
    -------
    dict with keys 'a_f', 'a_r', 'b', 'c' in meters
    """
    hi = max(0.5, heat_input_kj_mm)

    # Base pool half-width (mm): empirical ~3-6mm for 1-2 kJ/mm
    b_mm = 2.0 + 2.5 * np.sqrt(hi)

    # Penetration depends on process
    penetration_factors = {
        'gtaw': 0.6,    # Shallow for TIG
        'mig_mag': 0.8,
        'saw': 1.2,     # Deep penetration
        'smaw': 0.7,
    }
    pen_factor = penetration_factors.get(process_type, 0.8)
    c_mm = b_mm * pen_factor

    # Front/rear semi-axes
    a_f_mm = b_mm * 0.8   # Front shorter
    a_r_mm = b_mm * 1.6   # Rear elongated

    return {
        'b': b_mm / 1000.0,
        'c': c_mm / 1000.0,
        'a_f': a_f_mm / 1000.0,
        'a_r': a_r_mm / 1000.0,
        'b_mm': b_mm,
        'c_mm': c_mm,
        'a_f_mm': a_f_mm,
        'a_r_mm': a_r_mm,
    }
