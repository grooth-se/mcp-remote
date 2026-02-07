"""1D Finite Difference Heat Transfer Solver.

Solves the transient heat equation:
    rho * Cp * dT/dt = div(k * grad(T))

For cylindrical coordinates (cylinder, ring):
    rho * Cp * dT/dt = (1/r) * d/dr(r * k * dT/dr)

For Cartesian coordinates (plate):
    rho * Cp * dT/dt = d/dx(k * dT/dx)

Uses implicit Crank-Nicolson scheme for stability with large time steps.

Supports multi-phase heat treatment:
- Heating: Heat up to austenitizing temperature
- Transfer: Cool during transfer from furnace to quench
- Quenching: Rapid cooling in quench media
- Tempering: Reheat to tempering temperature and cool
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve

from app.services.geometry import GeometryBase, Cylinder, Plate, Ring
from app.services.boundary_conditions import (
    BoundaryCondition, InsulatedBoundary,
    create_heating_bc, create_ramping_heating_bc, create_transfer_bc, create_quench_bc,
    RampingBoundaryCondition,
    create_tempering_bc, create_cooling_bc
)
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
class PhaseConfig:
    """Configuration for a single heat treatment phase.

    Parameters
    ----------
    name : str
        Phase name (heating, transfer, quenching, tempering, cooling)
    enabled : bool
        Whether phase is enabled
    duration : float
        Phase duration in seconds
    target_temperature : float
        Target/ambient temperature for this phase
    boundary_condition : BoundaryCondition
        Boundary condition for this phase
    end_condition : str
        How to end phase: 'time', 'temperature', 'equilibrium', 'rate_threshold', 'center_offset'
    end_temperature : float
        Temperature threshold for 'temperature' or 'center_offset' end condition
    rate_threshold : float
        dT/dt threshold in °C/hr for 'rate_threshold' end condition
    hold_time_after_trigger : float
        Hold time in seconds after end condition is triggered (for 'rate_threshold')
    center_offset : float
        Offset from target for 'center_offset' end condition (°C)
    """
    name: str
    enabled: bool = True
    duration: float = 600.0
    target_temperature: float = 25.0
    boundary_condition: Optional[BoundaryCondition] = None
    end_condition: str = 'time'  # 'time', 'temperature', 'equilibrium', 'rate_threshold', 'center_offset'
    end_temperature: Optional[float] = None
    rate_threshold: float = 1.0  # °C/hr for rate_threshold end condition
    hold_time_after_trigger: float = 0.0  # seconds
    center_offset: float = 3.0  # °C below target for center_offset condition

    @classmethod
    def from_heating_config(cls, config: dict) -> 'PhaseConfig':
        """Create heating phase config from dict."""
        if not config.get('enabled', True):
            return cls(name='heating', enabled=False)

        target_temp = config.get('target_temperature', 850.0)
        hold_time = config.get('hold_time', 60.0)  # minutes
        initial_temp = config.get('initial_temperature', 25.0)

        # Check if using cold furnace start with ramp
        cold_furnace = config.get('cold_furnace', False)
        furnace_start_temp = config.get('furnace_start_temperature', initial_temp)
        ramp_rate = config.get('furnace_ramp_rate', 0.0)  # °C/min

        # Determine end condition
        end_condition = config.get('end_condition', 'equilibrium')
        rate_threshold = config.get('rate_threshold', 1.0)  # °C/hr
        hold_time_after_trigger = config.get('hold_time_after_trigger', 0.0) * 60  # min to sec
        center_offset = config.get('center_offset', 3.0)  # °C

        # Create appropriate boundary condition
        if cold_furnace and ramp_rate > 0:
            bc = create_ramping_heating_bc(
                target_temperature=target_temp,
                start_temperature=furnace_start_temp,
                ramp_rate=ramp_rate,
                htc=config.get('furnace_htc', 25.0),
                emissivity=config.get('furnace_emissivity', 0.85),
                use_radiation=config.get('use_radiation', True)
            )
        else:
            bc = create_heating_bc(
                target_temperature=target_temp,
                htc=config.get('furnace_htc', 25.0),
                emissivity=config.get('furnace_emissivity', 0.85),
                use_radiation=config.get('use_radiation', True)
            )

        # Calculate maximum duration based on ramp time + generous heat-up time + hold
        max_duration = hold_time * 60  # Base hold time in seconds
        if cold_furnace and ramp_rate > 0:
            ramp_time = (target_temp - furnace_start_temp) / ramp_rate * 60
            max_duration += ramp_time + 7200  # Add ramp time + 2hr buffer for part heating

        # Set end temperature based on condition
        if end_condition == 'center_offset':
            end_temp = target_temp - center_offset
        else:
            end_temp = target_temp - 5  # Default: within 5°C of target

        return cls(
            name='heating',
            enabled=True,
            duration=max_duration,
            target_temperature=target_temp,
            boundary_condition=bc,
            end_condition=end_condition,
            end_temperature=end_temp,
            rate_threshold=rate_threshold,
            hold_time_after_trigger=hold_time_after_trigger,
            center_offset=center_offset
        )

    @classmethod
    def from_transfer_config(cls, config: dict) -> 'PhaseConfig':
        """Create transfer phase config from dict."""
        if not config.get('enabled', True):
            return cls(name='transfer', enabled=False)

        ambient_temp = config.get('ambient_temperature', 25.0)
        duration = config.get('duration', 10.0)  # seconds

        bc = create_transfer_bc(
            ambient_temperature=ambient_temp,
            htc=config.get('htc', 10.0),
            emissivity=config.get('emissivity', 0.85),
            use_radiation=config.get('use_radiation', True)
        )

        return cls(
            name='transfer',
            enabled=True,
            duration=duration,
            target_temperature=ambient_temp,
            boundary_condition=bc,
            end_condition='time'
        )

    @classmethod
    def from_quenching_config(cls, config: dict) -> 'PhaseConfig':
        """Create quenching phase config from dict."""
        media = config.get('media', 'water')
        media_temp = config.get('media_temperature', 25.0)
        duration = config.get('duration', 300.0)  # seconds

        bc = create_quench_bc(
            media=media,
            media_temperature=media_temp,
            agitation=config.get('agitation', 'moderate'),
            htc_override=config.get('htc_override'),
            emissivity=config.get('emissivity', 0.3),
            use_radiation=config.get('use_radiation', False)
        )

        return cls(
            name='quenching',
            enabled=True,
            duration=duration,
            target_temperature=media_temp,
            boundary_condition=bc,
            end_condition='time'
        )

    @classmethod
    def from_tempering_config(cls, config: dict) -> 'PhaseConfig':
        """Create tempering phase config from dict."""
        if not config.get('enabled', False):
            return cls(name='tempering', enabled=False)

        temp = config.get('temperature', 550.0)
        hold_time = config.get('hold_time', 120.0)  # minutes

        # End condition settings (same as heating phase)
        end_condition = config.get('end_condition', 'equilibrium')
        rate_threshold = config.get('rate_threshold', 1.0)  # °C/hr
        hold_time_after_trigger = config.get('hold_time_after_trigger', 0.0) * 60  # min to sec
        center_offset = config.get('center_offset', 3.0)  # °C

        bc = create_tempering_bc(
            temperature=temp,
            htc=config.get('htc', 25.0),
            emissivity=config.get('emissivity', 0.85),
            cooling_method=config.get('cooling_method', 'air')
        )

        # Set end temperature based on condition
        if end_condition == 'center_offset':
            end_temp = temp - center_offset
        else:
            end_temp = temp - 5  # Default: within 5°C of target

        return cls(
            name='tempering',
            enabled=True,
            duration=hold_time * 60,  # Convert to seconds
            target_temperature=temp,
            boundary_condition=bc,
            end_condition=end_condition,
            end_temperature=end_temp,
            rate_threshold=rate_threshold,
            hold_time_after_trigger=hold_time_after_trigger,
            center_offset=center_offset
        )


@dataclass
class PhaseResult:
    """Results from a single heat treatment phase.

    Parameters
    ----------
    phase_name : str
        Name of the phase
    time : np.ndarray
        Time points in seconds (relative to phase start)
    absolute_time : np.ndarray
        Absolute time from simulation start
    temperature : np.ndarray
        Temperature field [time, position] in Celsius
    center_temp : np.ndarray
        Temperature at center vs time
    surface_temp : np.ndarray
        Temperature at surface vs time
    t8_5 : float, optional
        Cooling time 800-500°C (if applicable)
    """
    phase_name: str
    time: np.ndarray
    absolute_time: np.ndarray
    temperature: np.ndarray
    center_temp: np.ndarray
    surface_temp: np.ndarray
    t8_5: Optional[float] = None
    start_time: float = 0.0
    end_time: float = 0.0


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
    phase_results: Optional[List[PhaseResult]] = None


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

    def set_boundary_condition(self, bc: BoundaryCondition):
        """Update the outer boundary condition.

        Parameters
        ----------
        bc : BoundaryCondition
            New boundary condition
        """
        self.outer_bc = bc

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

    def solve_phase(
        self,
        initial_field: np.ndarray,
        mesh: np.ndarray,
        phase_config: PhaseConfig,
        start_time: float = 0.0,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> PhaseResult:
        """Run simulation for a single phase.

        Parameters
        ----------
        initial_field : np.ndarray
            Initial temperature field
        mesh : np.ndarray
            Spatial mesh
        phase_config : PhaseConfig
            Phase configuration
        start_time : float
            Absolute start time
        progress_callback : callable, optional
            Callback(progress, phase_name)

        Returns
        -------
        PhaseResult
            Phase simulation results
        """
        cfg = self.config

        if not phase_config.enabled:
            return PhaseResult(
                phase_name=phase_config.name,
                time=np.array([0.0]),
                absolute_time=np.array([start_time]),
                temperature=initial_field.reshape(1, -1),
                center_temp=np.array([initial_field[0]]),
                surface_temp=np.array([initial_field[-1]]),
                start_time=start_time,
                end_time=start_time
            )

        # Update boundary condition for this phase
        if phase_config.boundary_condition:
            self.outer_bc = phase_config.boundary_condition

        dr = mesh[1] - mesh[0] if len(mesh) > 1 else mesh[0]
        n = len(mesh)

        T = initial_field.copy()
        t = 0.0
        step = 0

        times = [0.0]
        temp_history = [T.copy()]

        # Phase-specific termination
        max_phase_time = phase_config.duration

        # Track state for rate_threshold condition
        rate_trigger_time = None
        prev_surface_temp = T[-1]
        rate_check_interval = 60.0  # Check rate every 60 seconds
        last_rate_check_time = 0.0

        while t < max_phase_time:
            # Update time on ramping boundary condition
            if isinstance(self.outer_bc, RampingBoundaryCondition):
                self.outer_bc.set_time(t)

            # Check end conditions
            if phase_config.end_condition == 'equilibrium':
                # Check if center has reached target
                if phase_config.end_temperature is not None:
                    if phase_config.name in ('heating', 'tempering'):
                        # Heating: end when center reaches target
                        if T[0] >= phase_config.end_temperature:
                            # Now we're at temperature, run hold time
                            break
                    else:
                        # Cooling: end when center drops below threshold
                        if T[0] <= phase_config.end_temperature:
                            break

            elif phase_config.end_condition == 'temperature':
                if phase_config.end_temperature is not None:
                    if T[0] <= phase_config.end_temperature:
                        break

            elif phase_config.end_condition == 'rate_threshold':
                # End when surface temperature change rate < threshold
                # Check periodically to avoid noise
                if t - last_rate_check_time >= rate_check_interval:
                    surface_rate = abs(T[-1] - prev_surface_temp) / rate_check_interval * 3600  # °C/hr
                    prev_surface_temp = T[-1]
                    last_rate_check_time = t

                    if surface_rate < phase_config.rate_threshold:
                        if rate_trigger_time is None:
                            rate_trigger_time = t
                        # Check if hold time has elapsed
                        if t - rate_trigger_time >= phase_config.hold_time_after_trigger:
                            break
                    else:
                        rate_trigger_time = None  # Reset if rate goes back up

            elif phase_config.end_condition == 'center_offset':
                # End when center reaches target - offset
                if T[0] >= phase_config.target_temperature - phase_config.center_offset:
                    break

            # Advance one time step
            T_new = self._time_step(T, mesh, dr, cfg.dt)
            T = T_new
            t += cfg.dt
            step += 1

            # Store at interval
            if step % cfg.output_interval == 0:
                times.append(t)
                temp_history.append(T.copy())

            # Progress callback
            if progress_callback:
                progress_callback(min(t / max_phase_time, 1.0), phase_config.name)

        # Store final state
        if step % cfg.output_interval != 0:
            times.append(t)
            temp_history.append(T.copy())

        times = np.array(times)
        temp_history = np.array(temp_history)
        absolute_times = times + start_time

        # Calculate t8/5 for this phase
        t8_5 = self._calculate_t8_5(times, temp_history[:, 0])

        return PhaseResult(
            phase_name=phase_config.name,
            time=times,
            absolute_time=absolute_times,
            temperature=temp_history,
            center_temp=temp_history[:, 0],
            surface_temp=temp_history[:, -1],
            t8_5=t8_5,
            start_time=start_time,
            end_time=start_time + times[-1]
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


class MultiPhaseHeatSolver:
    """Multi-phase heat treatment solver.

    Orchestrates sequential phases: heating, transfer, quenching, tempering.
    Each phase has different boundary conditions.
    """

    def __init__(
        self,
        geometry: GeometryBase,
        config: Optional[SolverConfig] = None
    ):
        """Initialize multi-phase solver.

        Parameters
        ----------
        geometry : GeometryBase
            Geometry object (Cylinder, Plate, or Ring)
        config : SolverConfig, optional
            Solver configuration
        """
        self.geometry = geometry
        self.config = config or SolverConfig()

        # Create base solver with dummy BC (will be replaced per phase)
        dummy_bc = BoundaryCondition(htc=100, ambient_temp=25)
        self.solver = HeatSolver(geometry, dummy_bc, config=self.config)

        # Phase configurations
        self.phases: List[PhaseConfig] = []

    def set_material(self, k_property, cp_property, density: float, emissivity: float = 0.85):
        """Set material properties."""
        self.solver.set_material(k_property, cp_property, density, emissivity)

    def configure_from_ht_config(self, ht_config: dict):
        """Configure phases from heat treatment config dict.

        Parameters
        ----------
        ht_config : dict
            Heat treatment configuration from Simulation model
        """
        self.phases = []

        # Heating phase
        heating = ht_config.get('heating', {})
        if heating.get('enabled', False):
            self.phases.append(PhaseConfig.from_heating_config(heating))

        # Transfer phase
        transfer = ht_config.get('transfer', {})
        if transfer.get('enabled', False):
            self.phases.append(PhaseConfig.from_transfer_config(transfer))

        # Quenching phase (always enabled)
        quenching = ht_config.get('quenching', {})
        self.phases.append(PhaseConfig.from_quenching_config(quenching))

        # Tempering phase
        tempering = ht_config.get('tempering', {})
        if tempering.get('enabled', False):
            self.phases.append(PhaseConfig.from_tempering_config(tempering))

            # Add cooling after tempering
            cooling_bc = create_cooling_bc(
                ambient_temperature=25.0,
                htc=tempering.get('htc', 25.0),
                emissivity=tempering.get('emissivity', 0.85),
                cooling_method=tempering.get('cooling_method', 'air')
            )
            cooling_phase = PhaseConfig(
                name='cooling',
                enabled=True,
                duration=600.0,  # 10 minutes default
                target_temperature=25.0,
                boundary_condition=cooling_bc,
                end_condition='equilibrium',
                end_temperature=50.0  # Stop when center < 50°C
            )
            self.phases.append(cooling_phase)

    def solve(
        self,
        initial_temperature: float = 25.0,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> SolverResult:
        """Run multi-phase heat treatment simulation.

        Parameters
        ----------
        initial_temperature : float
            Initial uniform temperature in Celsius
        progress_callback : callable, optional
            Callback(progress: 0-1, phase_name: str)

        Returns
        -------
        SolverResult
            Combined results from all phases
        """
        cfg = self.config

        # Create spatial mesh
        mesh = self.geometry.create_mesh(cfg.n_nodes)

        # Initialize temperature field
        T = np.full(len(mesh), initial_temperature)

        # Storage for combined results
        all_times = []
        all_temps = []
        phase_results = []

        current_time = 0.0
        total_phases = len(self.phases)

        for i, phase in enumerate(self.phases):
            if not phase.enabled:
                continue

            # Calculate phase progress contribution
            def phase_progress(p, name):
                overall = (i + p) / total_phases
                if progress_callback:
                    progress_callback(overall, name)

            # Run phase simulation
            result = self.solver.solve_phase(
                initial_field=T,
                mesh=mesh,
                phase_config=phase,
                start_time=current_time,
                progress_callback=phase_progress
            )

            phase_results.append(result)

            # Update state for next phase
            T = result.temperature[-1, :]
            current_time = result.end_time

            # Append results (skip first point to avoid duplicates)
            if len(all_times) == 0:
                all_times.extend(result.absolute_time.tolist())
                all_temps.extend(result.temperature.tolist())
            else:
                all_times.extend(result.absolute_time[1:].tolist())
                all_temps.extend(result.temperature[1:].tolist())

        # Convert to arrays
        times = np.array(all_times)
        temp_history = np.array(all_temps)

        # Extract curves
        n = len(mesh)
        center_temp = temp_history[:, 0]
        surface_temp = temp_history[:, -1]
        quarter_idx = n // 4
        quarter_temp = temp_history[:, quarter_idx] if n > 4 else None

        # Calculate overall t8/5 (from quenching phase if present)
        t8_5 = None
        for pr in phase_results:
            if pr.phase_name == 'quenching' and pr.t8_5 is not None:
                t8_5 = pr.t8_5
                break

        # Calculate cooling rates
        cooling_rates = self._calculate_cooling_rates(times, center_temp)

        return SolverResult(
            time=times,
            positions=mesh,
            temperature=temp_history,
            center_temp=center_temp,
            surface_temp=surface_temp,
            quarter_temp=quarter_temp,
            t8_5=t8_5,
            cooling_rates=cooling_rates,
            phase_results=phase_results
        )

    def _calculate_cooling_rates(self, times: np.ndarray, temps: np.ndarray) -> np.ndarray:
        """Calculate cooling rate (dT/dt) at each time point.

        Parameters
        ----------
        times : np.ndarray
            Time array in seconds
        temps : np.ndarray
            Temperature array in Celsius

        Returns
        -------
        np.ndarray
            Cooling rate in °C/s (negative = cooling)
        """
        if len(times) < 2:
            return np.zeros_like(times)

        # Use central differences for interior, forward/backward for ends
        dt = np.gradient(times)
        dT = np.gradient(temps)

        # Avoid division by zero
        dt = np.where(dt == 0, 1e-6, dt)

        return dT / dt
