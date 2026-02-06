"""1D Finite Difference Heat Transfer Solver.

Solves the transient heat equation:
    rho * Cp * dT/dt = div(k * grad(T))

For cylindrical coordinates (cylinder, ring):
    rho * Cp * dT/dt = (1/r) * d/dr(r * k * dT/dr)

For Cartesian coordinates (plate):
    rho * Cp * dT/dt = d/dx(k * dT/dx)

Uses implicit Crank-Nicolson scheme for stability with large time steps.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve

from app.services.geometry import GeometryBase, Cylinder, Plate, Ring
from app.services.boundary_conditions import BoundaryCondition, InsulatedBoundary
from app.services.property_evaluator import PropertyEvaluator


@dataclass
class SolverConfig:
    """Configuration for heat transfer solver.

    Parameters
    ----------
    n_nodes : int
        Number of spatial nodes
    dt : float
        Time step in seconds
    max_time : float
        Maximum simulation time in seconds
    theta : float
        Crank-Nicolson parameter (0.5 = CN, 1.0 = fully implicit)
    convergence_tol : float
        Temperature convergence tolerance for nonlinear iterations
    max_iterations : int
        Maximum iterations per time step
    output_interval : int
        Store results every N time steps
    """
    n_nodes: int = 51
    dt: float = 0.1
    max_time: float = 600.0
    theta: float = 0.5
    convergence_tol: float = 1e-4
    max_iterations: int = 50
    output_interval: int = 10

    @classmethod
    def from_dict(cls, d: dict) -> 'SolverConfig':
        """Create config from dictionary."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SolverResult:
    """Results from heat transfer simulation.

    Parameters
    ----------
    time : np.ndarray
        Time points in seconds
    positions : np.ndarray
        Spatial positions in meters
    temperature : np.ndarray
        Temperature field [time, position] in Celsius
    center_temp : np.ndarray
        Temperature at center vs time
    surface_temp : np.ndarray
        Temperature at surface vs time
    quarter_temp : np.ndarray, optional
        Temperature at quarter thickness
    t8_5 : float, optional
        Cooling time from 800°C to 500°C
    """
    time: np.ndarray
    positions: np.ndarray
    temperature: np.ndarray
    center_temp: np.ndarray
    surface_temp: np.ndarray
    quarter_temp: Optional[np.ndarray] = None
    t8_5: Optional[float] = None
    cooling_rates: Optional[np.ndarray] = None


class HeatSolver:
    """1D transient heat transfer solver using finite differences.

    Supports temperature-dependent material properties through
    PropertyEvaluator integration.
    """

    def __init__(
        self,
        geometry: GeometryBase,
        outer_bc: BoundaryCondition,
        inner_bc: Optional[BoundaryCondition] = None,
        config: Optional[SolverConfig] = None
    ):
        """Initialize solver.

        Parameters
        ----------
        geometry : GeometryBase
            Geometry object (Cylinder, Plate, or Ring)
        outer_bc : BoundaryCondition
            Boundary condition at outer surface
        inner_bc : BoundaryCondition, optional
            Boundary condition at inner surface (for Ring) or center
            None = symmetry (adiabatic)
        config : SolverConfig, optional
            Solver configuration
        """
        self.geometry = geometry
        self.outer_bc = outer_bc
        self.inner_bc = inner_bc or InsulatedBoundary()
        self.config = config or SolverConfig()

        # Material property evaluators
        self._k_evaluator: Optional[PropertyEvaluator] = None
        self._cp_evaluator: Optional[PropertyEvaluator] = None
        self._rho: float = 7850.0
        self._emissivity: float = 0.85

        # Coordinate system
        self._is_cylindrical = isinstance(geometry, (Cylinder, Ring))
        self._has_inner_bc = isinstance(geometry, Ring)

    def set_material(
        self,
        k_property,
        cp_property,
        density: float,
        emissivity: float = 0.85
    ):
        """Set material properties from database models.

        Parameters
        ----------
        k_property : MaterialProperty
            Thermal conductivity property model
        cp_property : MaterialProperty
            Specific heat property model
        density : float
            Density in kg/m³
        emissivity : float
            Surface emissivity
        """
        if k_property:
            self._k_evaluator = PropertyEvaluator(k_property)
        if cp_property:
            self._cp_evaluator = PropertyEvaluator(cp_property)
        self._rho = density
        self._emissivity = emissivity

        # Update boundary condition emissivity
        if hasattr(self.outer_bc, 'emissivity'):
            self.outer_bc.emissivity = emissivity

    def _get_properties_at_temp(self, T: float) -> Tuple[float, float]:
        """Get thermal conductivity and specific heat at temperature.

        Parameters
        ----------
        T : float
            Temperature in Celsius

        Returns
        -------
        tuple
            (k, cp) thermal conductivity and specific heat
        """
        k = 40.0  # Default
        cp = 500.0  # Default

        if self._k_evaluator:
            k_val = self._k_evaluator.evaluate(temperature=T)
            if k_val is not None:
                k = k_val

        if self._cp_evaluator:
            cp_val = self._cp_evaluator.evaluate(temperature=T)
            if cp_val is not None:
                cp = cp_val

        return k, cp

    def solve(
        self,
        initial_temp: float,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> SolverResult:
        """Run the heat transfer simulation.

        Parameters
        ----------
        initial_temp : float
            Initial uniform temperature in Celsius
        progress_callback : callable, optional
            Callback function(progress: float) called with 0-1 progress

        Returns
        -------
        SolverResult
            Simulation results
        """
        cfg = self.config

        # Create spatial mesh
        r = self.geometry.create_mesh(cfg.n_nodes)
        dr = r[1] - r[0] if len(r) > 1 else r[0]
        n = len(r)

        # Initialize temperature field
        T = np.full(n, initial_temp)

        # Time stepping
        t = 0.0
        step = 0

        # Storage for results
        times = [0.0]
        temp_history = [T.copy()]

        # Main time loop
        while t < cfg.max_time:
            # Check for quasi-steady state
            if np.max(np.abs(T - self.outer_bc.ambient_temp)) < 1.0:
                break

            # Advance one time step
            T_new = self._time_step(T, r, dr, cfg.dt)

            T = T_new
            t += cfg.dt
            step += 1

            # Store results at interval
            if step % cfg.output_interval == 0:
                times.append(t)
                temp_history.append(T.copy())

            # Progress callback
            if progress_callback:
                progress_callback(min(t / cfg.max_time, 1.0))

        # Store final state if not at interval
        if step % cfg.output_interval != 0:
            times.append(t)
            temp_history.append(T.copy())

        # Convert to arrays
        times = np.array(times)
        temp_history = np.array(temp_history)

        # Extract cooling curves
        center_temp = temp_history[:, 0]
        surface_temp = temp_history[:, -1]
        quarter_idx = n // 4
        quarter_temp = temp_history[:, quarter_idx] if n > 4 else None

        # Calculate t8/5
        t8_5 = self._calculate_t8_5(times, center_temp)

        return SolverResult(
            time=times,
            positions=r,
            temperature=temp_history,
            center_temp=center_temp,
            surface_temp=surface_temp,
            quarter_temp=quarter_temp,
            t8_5=t8_5
        )

    def _time_step(
        self,
        T: np.ndarray,
        r: np.ndarray,
        dr: float,
        dt: float
    ) -> np.ndarray:
        """Advance solution by one time step using Crank-Nicolson."""
        n = len(T)
        theta = self.config.theta

        T_new = T.copy()

        for iteration in range(self.config.max_iterations):
            T_old_iter = T_new.copy()

            # Average temperature for property evaluation
            T_avg = 0.5 * (T + T_new)

            # Get properties at each node
            k = np.array([self._get_properties_at_temp(Ti)[0] for Ti in T_avg])
            cp = np.array([self._get_properties_at_temp(Ti)[1] for Ti in T_avg])
            rho = self._rho

            # Thermal diffusivity
            alpha = k / (rho * cp)

            # Build system
            if self._is_cylindrical:
                A, b = self._build_cylindrical_system(T, T_new, r, dr, dt, k, alpha, theta)
            else:
                A, b = self._build_cartesian_system(T, T_new, dr, dt, k, alpha, theta)

            # Solve linear system
            T_new = spsolve(A, b)

            # Check convergence
            if np.max(np.abs(T_new - T_old_iter)) < self.config.convergence_tol:
                break

        return T_new

    def _build_cylindrical_system(
        self,
        T: np.ndarray,
        T_new: np.ndarray,
        r: np.ndarray,
        dr: float,
        dt: float,
        k: np.ndarray,
        alpha: np.ndarray,
        theta: float
    ) -> Tuple:
        """Build linear system for cylindrical coordinates."""
        n = len(T)

        # Fourier numbers
        Fo = alpha * dt / dr**2

        # Coefficient arrays
        lower = np.zeros(n)
        main = np.zeros(n)
        upper = np.zeros(n)
        rhs = np.zeros(n)

        # Interior nodes
        for i in range(1, n-1):
            r_i = r[i]
            Fo_i = Fo[i]

            r_plus = r_i + dr/2
            r_minus = r_i - dr/2

            a_w = Fo_i * r_minus / r_i
            a_e = Fo_i * r_plus / r_i
            a_p = 1 + theta * (a_w + a_e)

            lower[i] = -theta * a_w
            main[i] = a_p
            upper[i] = -theta * a_e

            rhs[i] = T[i] + (1-theta) * (
                a_w * (T[i-1] - T[i]) + a_e * (T[i+1] - T[i])
            )

        # Inner boundary (r=0 or inner radius)
        if self._has_inner_bc:
            # Ring: convection at inner surface
            h_eff = self.inner_bc.linearized_htc(T_new[0])
            Bi = h_eff * dr / k[0]
            Fo_0 = Fo[0]
            r_0 = r[0]
            r_plus = r_0 + dr/2

            a_e = Fo_0 * r_plus / r_0

            main[0] = 1 + theta * (a_e + 2 * Fo_0 * Bi)
            upper[0] = -theta * a_e
            rhs[0] = T[0] + (1-theta) * (
                a_e * (T[1] - T[0]) + 2 * Fo_0 * Bi * (self.inner_bc.ambient_temp - T[0])
            ) + 2 * theta * Fo_0 * Bi * self.inner_bc.ambient_temp
        else:
            # Symmetry at r=0: use L'Hopital's rule
            Fo_0 = Fo[0]
            main[0] = 1 + 4 * theta * Fo_0
            upper[0] = -4 * theta * Fo_0
            rhs[0] = T[0] + 4 * (1-theta) * Fo_0 * (T[1] - T[0])

        # Outer boundary: convection
        h_eff = self.outer_bc.linearized_htc(T_new[-1])
        Bi = h_eff * dr / k[-1]
        Fo_n = Fo[-1]

        r_n = r[-1]
        r_minus = r_n - dr/2

        a_w = Fo_n * r_minus / r_n

        main[-1] = 1 + theta * (a_w + 2 * Fo_n * Bi)
        lower[-1] = -theta * a_w
        rhs[-1] = T[-1] + (1-theta) * (
            a_w * (T[-2] - T[-1]) + 2 * Fo_n * Bi * (self.outer_bc.ambient_temp - T[-1])
        ) + 2 * theta * Fo_n * Bi * self.outer_bc.ambient_temp

        # Build sparse matrix
        A = diags([lower[1:], main, upper[:-1]], [-1, 0, 1], format='csr')

        return A, rhs

    def _build_cartesian_system(
        self,
        T: np.ndarray,
        T_new: np.ndarray,
        dx: float,
        dt: float,
        k: np.ndarray,
        alpha: np.ndarray,
        theta: float
    ) -> Tuple:
        """Build linear system for Cartesian coordinates (plate)."""
        n = len(T)
        Fo = alpha * dt / dx**2

        lower = np.zeros(n)
        main = np.zeros(n)
        upper = np.zeros(n)
        rhs = np.zeros(n)

        # Interior nodes
        for i in range(1, n-1):
            Fo_i = Fo[i]

            main[i] = 1 + 2 * theta * Fo_i
            lower[i] = -theta * Fo_i
            upper[i] = -theta * Fo_i

            rhs[i] = T[i] + (1-theta) * Fo_i * (T[i-1] - 2*T[i] + T[i+1])

        # Center (x=0): symmetry
        Fo_0 = Fo[0]
        main[0] = 1 + 2 * theta * Fo_0
        upper[0] = -2 * theta * Fo_0
        rhs[0] = T[0] + 2 * (1-theta) * Fo_0 * (T[1] - T[0])

        # Surface: convection
        h_eff = self.outer_bc.linearized_htc(T_new[-1])
        Bi = h_eff * dx / k[-1]
        Fo_n = Fo[-1]

        main[-1] = 1 + theta * (2 * Fo_n + 2 * Fo_n * Bi)
        lower[-1] = -2 * theta * Fo_n
        rhs[-1] = T[-1] + (1-theta) * (
            2 * Fo_n * (T[-2] - T[-1]) + 2 * Fo_n * Bi * (self.outer_bc.ambient_temp - T[-1])
        ) + 2 * theta * Fo_n * Bi * self.outer_bc.ambient_temp

        A = diags([lower[1:], main, upper[:-1]], [-1, 0, 1], format='csr')

        return A, rhs

    def _calculate_t8_5(self, times: np.ndarray, temps: np.ndarray) -> Optional[float]:
        """Calculate cooling time from 800°C to 500°C."""
        # Find time when temp crosses 800°C
        idx_800 = np.where(temps <= 800)[0]
        if len(idx_800) == 0:
            return None
        t_800 = times[idx_800[0]]

        # Find time when temp crosses 500°C
        idx_500 = np.where(temps <= 500)[0]
        if len(idx_500) == 0:
            return None
        t_500 = times[idx_500[0]]

        return t_500 - t_800
