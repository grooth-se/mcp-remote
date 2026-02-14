"""Rosenthal analytical solution for welding thermal cycles.

Implements the 3D and 2D (thin-plate) Rosenthal solutions for a
moving point heat source in a semi-infinite or thin body.

The 3D solution (thick plate):
    T(ξ,y,z) = T0 + (Q / 2πk) × (1/R) × exp(-v(R+ξ) / (2α))

The 2D solution (thin plate):
    T(ξ,y) = T0 + (Q / 2πkd) × K0(vR / (2α)) × exp(-vξ / (2α))

where:
    ξ = x - v*t  (moving coordinate)
    R = sqrt(ξ² + y² + z²)
    K0 = modified Bessel function of the second kind, order zero

References:
- Rosenthal D., "Mathematical Theory of Heat Distribution during
  Welding and Cutting", Welding Journal, 1941
- Easterling K., "Introduction to the Physical Metallurgy of Welding"
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict
import numpy as np
from scipy.special import k0
from scipy.optimize import brentq


# Default thermal properties for structural steel
DEFAULT_CONDUCTIVITY = 40.0      # W/(m·K)
DEFAULT_DENSITY = 7850.0         # kg/m³
DEFAULT_SPECIFIC_HEAT = 500.0    # J/(kg·K)


@dataclass
class RosenthalParams:
    """Parameters for Rosenthal analytical solution.

    Attributes
    ----------
    Q : float
        Net arc power (W) = eta × V × I  (or eta × heat_input × v × 1000)
    v : float
        Travel speed (m/s)
    T0 : float
        Preheat / initial temperature (°C)
    k : float
        Thermal conductivity (W/(m·K))
    alpha : float
        Thermal diffusivity (m²/s) = k / (rho × Cp)
    rho : float
        Density (kg/m³)
    Cp : float
        Specific heat capacity (J/(kg·K))
    eta : float
        Arc efficiency (0–1)
    plate_thickness : float
        Plate thickness (m), used for 2D thin-plate model
    """
    Q: float = 3000.0
    v: float = 0.005
    T0: float = 20.0
    k: float = DEFAULT_CONDUCTIVITY
    alpha: float = DEFAULT_CONDUCTIVITY / (DEFAULT_DENSITY * DEFAULT_SPECIFIC_HEAT)
    rho: float = DEFAULT_DENSITY
    Cp: float = DEFAULT_SPECIFIC_HEAT
    eta: float = 0.80
    plate_thickness: float = 0.020  # 20 mm


# Arc efficiency values for common welding processes
ARC_EFFICIENCIES = {
    'gtaw': 0.65,
    'mig_mag': 0.80,
    'saw': 0.90,
    'smaw': 0.75,
}


class RosenthalSolver:
    """Rosenthal analytical welding thermal cycle solver.

    Provides physically correct thermal cycles from a moving point
    heat source without needing a numerical (FEM) solver.
    """

    def __init__(self, params: RosenthalParams):
        self.params = params

    @classmethod
    def from_weld_project(cls, project, string=None) -> 'RosenthalSolver':
        """Create solver from a WeldProject and optional WeldString.

        Parameters
        ----------
        project : WeldProject
            Weld project with steel grade, process type, defaults
        string : WeldString, optional
            Specific string for per-string overrides

        Returns
        -------
        RosenthalSolver
        """
        # Get process efficiency
        process_type = project.process_type or 'mig_mag'
        eta = ARC_EFFICIENCIES.get(process_type, 0.80)

        # Get heat input and travel speed
        if string:
            heat_input_kj_mm = string.effective_heat_input
            travel_speed_mm_s = string.effective_travel_speed
        else:
            heat_input_kj_mm = project.default_heat_input
            travel_speed_mm_s = project.default_travel_speed

        # Convert travel speed to m/s
        v = travel_speed_mm_s / 1000.0

        # Net power: Q = eta × heat_input(kJ/mm) × travel_speed(mm/s) × 1000
        Q = eta * heat_input_kj_mm * travel_speed_mm_s * 1000.0

        # Get thermal properties from steel grade
        k = DEFAULT_CONDUCTIVITY
        rho = DEFAULT_DENSITY
        Cp = DEFAULT_SPECIFIC_HEAT

        if project.steel_grade:
            grade = project.steel_grade
            # Try to get properties from the grade
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

        alpha = k / (rho * Cp)
        T0 = project.preheat_temperature or 20.0

        params = RosenthalParams(
            Q=Q, v=v, T0=T0, k=k, alpha=alpha,
            rho=rho, Cp=Cp, eta=eta,
            plate_thickness=0.020,  # Default 20mm, could be from CAD
        )
        return cls(params)

    def temperature_3d(self, xi: float, y: float, z: float) -> float:
        """3D Rosenthal solution for thick plate.

        T = T0 + (Q / 2πk) × (1/R) × exp(-v(R+ξ) / (2α))

        Parameters
        ----------
        xi : float
            Moving coordinate ξ = x - v*t (m), negative = behind source
        y : float
            Transverse distance from weld line (m)
        z : float
            Depth below surface (m)

        Returns
        -------
        float
            Temperature (°C)
        """
        p = self.params
        R = np.sqrt(xi**2 + y**2 + z**2)

        if R < 1e-6:
            # Avoid singularity at source; cap at solidification temp
            return min(p.T0 + p.Q / (2 * np.pi * p.k * 1e-6), 1500.0)

        exponent = -p.v * (R + xi) / (2 * p.alpha)
        # Clamp exponent to avoid overflow
        exponent = max(exponent, -500.0)

        T = p.T0 + (p.Q / (2 * np.pi * p.k)) * (1.0 / R) * np.exp(exponent)
        return float(T)

    def temperature_2d(self, xi: float, y: float) -> float:
        """2D Rosenthal solution for thin plate.

        T = T0 + (Q / 2πkd) × K0(v·R/(2α)) × exp(-v·ξ/(2α))

        Parameters
        ----------
        xi : float
            Moving coordinate (m)
        y : float
            Transverse distance (m)

        Returns
        -------
        float
            Temperature (°C)
        """
        p = self.params
        d = p.plate_thickness
        R = np.sqrt(xi**2 + y**2)

        if R < 1e-6:
            return min(p.T0 + p.Q / (2 * np.pi * p.k * d * 1e-6), 1500.0)

        arg_bessel = p.v * R / (2 * p.alpha)
        # K0 diverges for very large arguments -> temp ~ 0
        if arg_bessel > 500:
            return p.T0

        exponent = -p.v * xi / (2 * p.alpha)
        exponent = max(exponent, -500.0)

        T = p.T0 + (p.Q / (2 * np.pi * p.k * d)) * k0(arg_bessel) * np.exp(exponent)
        return float(T)

    def thermal_cycle_at_point(
        self,
        y: float,
        z: float = 0.0,
        duration: float = 120.0,
        n_points: int = 200,
        use_2d: bool = False
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute thermal cycle T(t) at a fixed point (y, z) as the source passes.

        The source approaches from far away, passes closest at t=t_peak,
        then moves away. We sweep ξ from positive (source approaching)
        to negative (source receding), converting ξ = -v*t_relative.

        Parameters
        ----------
        y : float
            Transverse distance from weld line (m)
        z : float
            Depth below surface (m)
        duration : float
            Total cycle duration (s)
        n_points : int
            Number of time points
        use_2d : bool
            Use thin-plate (2D) model instead of 3D

        Returns
        -------
        tuple of (times, temperatures) as numpy arrays
        """
        p = self.params
        times = np.linspace(0, duration, n_points)

        # The source is at x=0 at t=0; the monitoring point is at (0, y, z)
        # At time t, source is at x_source = v*t
        # ξ = x_point - x_source = 0 - v*t = -v*t
        # But we want the source to approach first (ξ > 0) then recede (ξ < 0)
        # So center time so source passes at t = duration * 0.15 (heat-up shorter than cool-down)
        t_pass = duration * 0.15
        xi_arr = -p.v * (times - t_pass)  # positive when source approaching

        temps = np.zeros(n_points)
        for i, xi in enumerate(xi_arr):
            if use_2d:
                temps[i] = self.temperature_2d(xi, y)
            else:
                temps[i] = self.temperature_3d(xi, y, z)

        return times, temps

    def peak_temperature_at_distance(
        self,
        distances_m: np.ndarray,
        z: float = 0.0,
        use_2d: bool = False
    ) -> np.ndarray:
        """Calculate peak temperature at various transverse distances.

        The peak occurs at ξ=0 for the 3D case, but more precisely
        we search a small range around ξ=0.

        Parameters
        ----------
        distances_m : np.ndarray
            Transverse distances y from weld line (m)
        z : float
            Depth below surface (m)
        use_2d : bool
            Use thin-plate model

        Returns
        -------
        np.ndarray
            Peak temperatures (°C)
        """
        peak_temps = np.zeros(len(distances_m))

        for i, y in enumerate(distances_m):
            if y < 1e-6 and z < 1e-6:
                # At weld center, cap at solidification
                peak_temps[i] = 1500.0
                continue

            # Search for peak by scanning xi around 0
            # Peak is near ξ = -y for 3D solution
            xi_search = np.linspace(-max(0.05, 5 * abs(y)), max(0.001, abs(y)), 500)
            if use_2d:
                T_search = np.array([self.temperature_2d(xi, y) for xi in xi_search])
            else:
                T_search = np.array([self.temperature_3d(xi, y, z) for xi in xi_search])

            peak_temps[i] = float(np.max(T_search))

        return peak_temps

    def haz_boundary_distance(
        self,
        target_temp: float,
        z: float = 0.0,
        use_2d: bool = False
    ) -> float:
        """Find the transverse distance where peak temperature equals target.

        Uses root-finding (Brent's method) to solve T_peak(y) = target_temp.

        Parameters
        ----------
        target_temp : float
            Target peak temperature (°C), e.g. 727 for Ac1
        z : float
            Depth below surface (m)
        use_2d : bool
            Use thin-plate model

        Returns
        -------
        float
            Distance from weld center (m), or 0.0 if target not reached
        """
        p = self.params

        # Check that peak at some close distance exceeds target
        y_close = 0.0005  # 0.5 mm
        T_close = self.peak_temperature_at_distance(np.array([y_close]), z, use_2d)[0]

        if T_close < target_temp:
            return 0.0  # Target temp not reached even close to weld

        # Binary search / brentq for the boundary
        def func(y_val):
            T_peak = self.peak_temperature_at_distance(np.array([y_val]), z, use_2d)[0]
            return T_peak - target_temp

        # Find upper bound where T_peak < target
        y_max = 0.001  # Start at 1mm
        while y_max < 0.2:  # Up to 200mm
            T_far = self.peak_temperature_at_distance(np.array([y_max]), z, use_2d)[0]
            if T_far < target_temp:
                break
            y_max *= 2

        if y_max >= 0.2:
            return 0.2  # Cap

        try:
            y_boundary = brentq(func, y_close, y_max, xtol=1e-6, maxiter=100)
            return float(y_boundary)
        except ValueError:
            return 0.0

    def t8_5_at_point(
        self,
        y: float,
        z: float = 0.0,
        use_2d: bool = False
    ) -> Optional[float]:
        """Calculate t8/5 cooling time at a specific point.

        Parameters
        ----------
        y : float
            Transverse distance from weld line (m)
        z : float
            Depth below surface (m)
        use_2d : bool
            Use thin-plate model

        Returns
        -------
        float or None
            Cooling time 800->500°C in seconds, or None if not applicable
        """
        # Generate a thermal cycle at this point
        times, temps = self.thermal_cycle_at_point(
            y, z, duration=300.0, n_points=500, use_2d=use_2d
        )

        # Check if peak temperature exceeds 800°C
        if np.max(temps) < 800:
            return None

        # Find peak index
        peak_idx = np.argmax(temps)

        # Only look at cooling portion (after peak)
        cool_times = times[peak_idx:]
        cool_temps = temps[peak_idx:]

        # Find time when temperature crosses 800°C (cooling down)
        idx_800 = None
        for i in range(len(cool_temps) - 1):
            if cool_temps[i] >= 800 and cool_temps[i + 1] < 800:
                # Linear interpolation
                frac = (800 - cool_temps[i + 1]) / (cool_temps[i] - cool_temps[i + 1])
                t_800 = cool_times[i + 1] + frac * (cool_times[i] - cool_times[i + 1])
                idx_800 = t_800
                break

        if idx_800 is None:
            # Temperature starts below 800 after peak; use peak time
            if cool_temps[0] >= 800:
                idx_800 = cool_times[0]
            else:
                return None

        # Find time when temperature crosses 500°C
        idx_500 = None
        for i in range(len(cool_temps) - 1):
            if cool_temps[i] >= 500 and cool_temps[i + 1] < 500:
                frac = (500 - cool_temps[i + 1]) / (cool_temps[i] - cool_temps[i + 1])
                t_500 = cool_times[i + 1] + frac * (cool_times[i] - cool_times[i + 1])
                idx_500 = t_500
                break

        if idx_500 is None:
            return None

        t8_5 = idx_500 - idx_800
        return float(t8_5) if t8_5 > 0 else None

    def fusion_zone_width(self, solidus_temp: float = 1500.0, z: float = 0.0) -> float:
        """Estimate the fusion zone half-width.

        Parameters
        ----------
        solidus_temp : float
            Solidus temperature (°C)
        z : float
            Depth (m)

        Returns
        -------
        float
            Fusion zone half-width (m)
        """
        return self.haz_boundary_distance(solidus_temp, z)
