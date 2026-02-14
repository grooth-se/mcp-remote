"""Process optimization for heat treatment simulations.

Uses scipy.optimize to find optimal heat treatment parameters
that achieve target metallurgical outcomes (hardness, t8/5,
phase fractions). Evaluates objective using fast reduced-resolution
simulations (31 nodes) following the SensitivityAnalyzer pattern.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, TYPE_CHECKING
import copy
import logging
import time

import numpy as np
from scipy.optimize import minimize, differential_evolution

from app.services.heat_solver import MultiPhaseHeatSolver, SolverConfig
from app.services.geometry import create_geometry

if TYPE_CHECKING:
    from app.models.simulation import Simulation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter and output definitions
# ---------------------------------------------------------------------------

PARAMETER_DEFINITIONS = {
    'heating.target_temperature': {
        'label': 'Austenitizing Temperature', 'unit': '°C',
        'default_min': 750, 'default_max': 1100,
    },
    'heating.hold_time': {
        'label': 'Austenitizing Hold Time', 'unit': 'min',
        'default_min': 10, 'default_max': 480,
    },
    'quenching.media_temperature': {
        'label': 'Quench Media Temperature', 'unit': '°C',
        'default_min': 0, 'default_max': 200,
    },
    'quenching.duration': {
        'label': 'Quench Duration', 'unit': 's',
        'default_min': 30, 'default_max': 7200,
    },
    'tempering.temperature': {
        'label': 'Tempering Temperature', 'unit': '°C',
        'default_min': 100, 'default_max': 700,
    },
    'tempering.hold_time': {
        'label': 'Tempering Hold Time', 'unit': 'min',
        'default_min': 30, 'default_max': 480,
    },
}

OUTPUT_DEFINITIONS = {
    'hardness_hv_center': {'label': 'Center Hardness (HV)', 'unit': 'HV'},
    'hardness_hv_surface': {'label': 'Surface Hardness (HV)', 'unit': 'HV'},
    't8_5': {'label': 't₈/₅ Cooling Time', 'unit': 's'},
    'martensite': {'label': 'Martensite Fraction', 'unit': '%'},
    'bainite': {'label': 'Bainite Fraction', 'unit': '%'},
    'core_cooling_rate': {'label': 'Core Cooling Rate', 'unit': '°C/s'},
    'surface_cooling_rate': {'label': 'Surface Cooling Rate', 'unit': '°C/s'},
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OptimizationParameter:
    """One parameter to optimize."""
    key: str
    label: str
    unit: str
    min_value: float
    max_value: float


@dataclass
class OptimizationObjective:
    """Optimization target."""
    output_key: str
    direction: str      # 'minimize', 'maximize', 'target'
    target_value: float = 0.0


@dataclass
class OptimizationConstraint:
    """Optional output constraint."""
    output_key: str
    operator: str       # 'gte' or 'lte'
    value: float


@dataclass
class OptimizationIteration:
    """One evaluation in the optimization loop."""
    iteration: int
    parameters: Dict[str, float]
    outputs: Dict[str, float]
    objective_value: float
    is_feasible: bool


@dataclass
class OptimizationResult:
    """Complete optimization results."""
    status: str
    best_parameters: Dict[str, float]
    best_outputs: Dict[str, float]
    best_objective: float
    iterations: List[OptimizationIteration]
    total_evaluations: int
    elapsed_seconds: float
    objective: OptimizationObjective
    parameters: List[OptimizationParameter]
    constraints: List[OptimizationConstraint] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'status': self.status,
            'best_parameters': self.best_parameters,
            'best_outputs': self.best_outputs,
            'best_objective': self.best_objective,
            'iterations': [
                {
                    'iteration': it.iteration,
                    'parameters': it.parameters,
                    'outputs': it.outputs,
                    'objective_value': it.objective_value,
                    'is_feasible': it.is_feasible,
                }
                for it in self.iterations
            ],
            'total_evaluations': self.total_evaluations,
            'elapsed_seconds': round(self.elapsed_seconds, 1),
            'objective': {
                'output_key': self.objective.output_key,
                'direction': self.objective.direction,
                'target_value': self.objective.target_value,
            },
            'parameters': [
                {
                    'key': p.key, 'label': p.label, 'unit': p.unit,
                    'min_value': p.min_value, 'max_value': p.max_value,
                }
                for p in self.parameters
            ],
            'constraints': [
                {
                    'output_key': c.output_key,
                    'operator': c.operator,
                    'value': c.value,
                }
                for c in self.constraints
            ],
        }


# ---------------------------------------------------------------------------
# OptimizationService
# ---------------------------------------------------------------------------

class OptimizationService:
    """Runs process optimization using scipy.optimize.

    Parameters
    ----------
    simulation : Simulation
        Completed simulation to optimize from.
    """

    PENALTY_WEIGHT = 1000.0

    def __init__(self, simulation: 'Simulation'):
        self.sim = simulation
        self._eval_count = 0
        self._history: List[OptimizationIteration] = []
        self._best_obj = float('inf')
        self._best_params: Dict[str, float] = {}
        self._best_outputs: Dict[str, float] = {}

    def optimize(
        self,
        objective: OptimizationObjective,
        parameters: List[OptimizationParameter],
        constraints: Optional[List[OptimizationConstraint]] = None,
        method: str = 'nelder-mead',
        max_iterations: int = 30,
    ) -> OptimizationResult:
        """Run optimization.

        Parameters
        ----------
        objective : OptimizationObjective
            What to optimize.
        parameters : list of OptimizationParameter
            Parameters to vary with bounds.
        constraints : list of OptimizationConstraint, optional
            Output constraints.
        method : str
            'nelder-mead' or 'differential_evolution'.
        max_iterations : int
            Maximum optimizer iterations.

        Returns
        -------
        OptimizationResult
        """
        constraints = constraints or []
        self._eval_count = 0
        self._history = []
        self._best_obj = float('inf')
        self._best_params = {}
        self._best_outputs = {}

        t_start = time.time()

        # Bounds for scipy
        bounds = [(p.min_value, p.max_value) for p in parameters]

        # Initial guess: current simulation values (midpoint of bounds as fallback)
        x0 = []
        for p in parameters:
            current = self._get_current_value(p.key)
            if current is not None:
                x0.append(np.clip(current, p.min_value, p.max_value))
            else:
                x0.append((p.min_value + p.max_value) / 2)
        x0 = np.array(x0)

        try:
            if method == 'differential_evolution':
                result = differential_evolution(
                    self._objective_function,
                    bounds=bounds,
                    args=(parameters, objective, constraints),
                    maxiter=max_iterations,
                    seed=42,
                    tol=1e-3,
                    polish=False,
                    init='sobol',
                )
                status = 'completed' if result.success else 'max_iterations'
            else:
                # Nelder-Mead with bounds
                result = minimize(
                    self._objective_function,
                    x0,
                    args=(parameters, objective, constraints),
                    method='Nelder-Mead',
                    options={
                        'maxiter': max_iterations,
                        'maxfev': max_iterations * 3,
                        'xatol': 1e-2,
                        'fatol': 1e-3,
                        'adaptive': True,
                    },
                )
                status = 'completed' if result.success else 'max_iterations'
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            status = 'failed'

        elapsed = time.time() - t_start

        return OptimizationResult(
            status=status,
            best_parameters=self._best_params,
            best_outputs=self._best_outputs,
            best_objective=self._best_obj if self._best_obj < float('inf') else 0.0,
            iterations=self._history,
            total_evaluations=self._eval_count,
            elapsed_seconds=elapsed,
            objective=objective,
            parameters=parameters,
            constraints=constraints,
        )

    def _objective_function(
        self,
        x: np.ndarray,
        parameters: List[OptimizationParameter],
        objective: OptimizationObjective,
        constraints: List[OptimizationConstraint],
    ) -> float:
        """Evaluate objective for a parameter vector."""
        # Map vector to named parameters
        param_values = {}
        for i, p in enumerate(parameters):
            param_values[p.key] = float(x[i])

        # Run evaluation
        outputs = self._run_evaluation(param_values)
        self._eval_count += 1

        # Get objective output value
        obj_value = outputs.get(objective.output_key, 0.0)

        # Compute raw objective
        if objective.direction == 'target':
            raw_obj = abs(obj_value - objective.target_value)
        elif objective.direction == 'maximize':
            raw_obj = -obj_value
        else:  # minimize
            raw_obj = obj_value

        # Apply constraint penalties
        penalty = 0.0
        is_feasible = True
        for c in constraints:
            c_value = outputs.get(c.output_key, 0.0)
            if c.operator == 'gte' and c_value < c.value:
                violation = c.value - c_value
                penalty += self.PENALTY_WEIGHT * violation ** 2
                is_feasible = False
            elif c.operator == 'lte' and c_value > c.value:
                violation = c_value - c.value
                penalty += self.PENALTY_WEIGHT * violation ** 2
                is_feasible = False

        total_obj = raw_obj + penalty

        # Record iteration
        iteration = OptimizationIteration(
            iteration=self._eval_count,
            parameters={k: round(v, 2) for k, v in param_values.items()},
            outputs={k: round(v, 3) for k, v in outputs.items()},
            objective_value=round(total_obj, 4),
            is_feasible=is_feasible,
        )
        self._history.append(iteration)

        # Track best feasible solution
        if is_feasible and total_obj < self._best_obj:
            self._best_obj = total_obj
            self._best_params = dict(iteration.parameters)
            self._best_outputs = dict(iteration.outputs)

        # Also track best overall if no feasible yet
        if not self._best_params and total_obj < self._best_obj:
            self._best_obj = total_obj
            self._best_params = dict(iteration.parameters)
            self._best_outputs = dict(iteration.outputs)

        logger.debug(f"Eval #{self._eval_count}: obj={total_obj:.4f}, "
                     f"feasible={is_feasible}, params={param_values}")

        return total_obj

    def _run_evaluation(self, param_values: Dict[str, float]) -> Dict[str, float]:
        """Run a single reduced-resolution simulation with given parameters.

        Follows the SensitivityAnalyzer._run_with_modified_param() pattern.
        """
        try:
            ht_config = copy.deepcopy(self.sim.ht_config or {})
            geom_config = copy.deepcopy(self.sim.geometry_dict or {})

            # Apply parameter changes
            for key, value in param_values.items():
                self._apply_params_to_config(key, value, ht_config, geom_config)

            # Build geometry (use equivalent for CAD)
            geom_type = self.sim.geometry_type
            if geom_type == 'cad':
                geom_type = self.sim.cad_equivalent_type or 'cylinder'
                geom_config = copy.deepcopy(
                    self.sim.cad_equivalent_geometry_dict or geom_config
                )
                # Re-apply geometry params if any were optimized
                for key, value in param_values.items():
                    if key.startswith('geometry.'):
                        self._apply_params_to_config(key, value, ht_config, geom_config)

            geometry = create_geometry(geom_type, geom_config)

            # Reduced resolution solver (31 nodes for speed)
            solver_dict = copy.deepcopy(self.sim.solver_dict or {})
            solver_dict['n_nodes'] = min(solver_dict.get('n_nodes', 31), 31)
            solver_config = SolverConfig.from_dict(solver_dict)

            # Material properties
            grade = self.sim.steel_grade
            k_prop = grade.get_property('thermal_conductivity')
            cp_prop = grade.get_property('specific_heat')
            rho_prop = grade.get_property('density')
            emiss_prop = grade.get_property('emissivity')
            density = rho_prop.data_dict.get('value', 7850) if rho_prop else 7850
            emissivity = emiss_prop.data_dict.get('value', 0.85) if emiss_prop else 0.85

            # Build and configure solver
            solver = MultiPhaseHeatSolver(geometry, config=solver_config)
            solver.set_material(k_prop, cp_prop, density, emissivity)
            solver.configure_from_ht_config(ht_config)

            # Initial temperature
            heating_cfg = ht_config.get('heating', {})
            if heating_cfg.get('enabled', False):
                initial_temp = heating_cfg.get('initial_temperature', 25.0)
            else:
                initial_temp = heating_cfg.get('target_temperature', 850.0)

            # Run solver
            result = solver.solve(initial_temperature=initial_temp)

            # Extract outputs
            outputs = {
                't8_5': round(result.t8_5 or 0.0, 2),
                'core_cooling_rate': round(
                    300.0 / max(result.t8_5 or 0.1, 0.1), 1
                ),
                'surface_cooling_rate': 0.0,
                'hardness_hv_center': 0.0,
                'hardness_hv_surface': 0.0,
                'martensite': 0.0,
                'bainite': 0.0,
            }

            # Surface cooling rate
            n_pos = (result.temperature.shape[1]
                     if result.temperature.ndim > 1 else 1)
            if n_pos > 1:
                surface_temp = result.temperature[:, -1]
                dtdt = np.gradient(surface_temp, result.time)
                outputs['surface_cooling_rate'] = round(
                    abs(float(np.min(dtdt))), 1
                )

            # Hardness and phase prediction
            diagram = grade.phase_diagrams.first()
            if diagram and grade.composition:
                from app.services.phase_tracker import PhaseTracker
                from app.services.hardness_predictor import predict_hardness_profile
                tracker = PhaseTracker(diagram)
                try:
                    hr = predict_hardness_profile(
                        grade.composition, result.temperature,
                        result.time, tracker
                    )
                    outputs['hardness_hv_center'] = hr.hardness_hv.get('center', 0)
                    outputs['hardness_hv_surface'] = hr.hardness_hv.get('surface', 0)

                    # Phase fractions at center
                    center_phases = hr.phase_fractions.get('center', {})
                    outputs['martensite'] = round(
                        center_phases.get('martensite', 0) * 100, 1
                    )
                    outputs['bainite'] = round(
                        center_phases.get('bainite', 0) * 100, 1
                    )
                except Exception:
                    pass

            return outputs

        except Exception as e:
            logger.error(f"Optimization evaluation failed: {e}")
            return {k: 0.0 for k in OUTPUT_DEFINITIONS}

    def _apply_params_to_config(
        self, key: str, value: float,
        ht_config: dict, geom_config: dict
    ) -> None:
        """Apply a dotted-key parameter value to the appropriate config dict."""
        if key == 'heating.target_temperature':
            ht_config.setdefault('heating', {})['target_temperature'] = value
        elif key == 'heating.hold_time':
            ht_config.setdefault('heating', {})['hold_time'] = value
        elif key == 'quenching.media_temperature':
            ht_config.setdefault('quenching', {})['media_temperature'] = value
        elif key == 'quenching.duration':
            ht_config.setdefault('quenching', {})['duration'] = max(value, 10)
        elif key == 'tempering.temperature':
            ht_config.setdefault('tempering', {})['temperature'] = value
        elif key == 'tempering.hold_time':
            ht_config.setdefault('tempering', {})['hold_time'] = value
        elif key == 'geometry.radius':
            geom_config['radius'] = value / 1000  # mm → m
        elif key == 'geometry.thickness':
            geom_config['thickness'] = value / 1000  # mm → m
        elif key == 'geometry.outer_diameter':
            geom_config['outer_diameter'] = value / 1000  # mm → m

    def _get_current_value(self, key: str) -> Optional[float]:
        """Get the current parameter value from the simulation config."""
        ht = self.sim.ht_config or {}
        geom = self.sim.geometry_dict or {}

        if key == 'heating.target_temperature':
            return ht.get('heating', {}).get('target_temperature')
        elif key == 'heating.hold_time':
            return ht.get('heating', {}).get('hold_time')
        elif key == 'quenching.media_temperature':
            return ht.get('quenching', {}).get('media_temperature')
        elif key == 'quenching.duration':
            return ht.get('quenching', {}).get('duration')
        elif key == 'tempering.temperature':
            return ht.get('tempering', {}).get('temperature')
        elif key == 'tempering.hold_time':
            return ht.get('tempering', {}).get('hold_time')
        elif key == 'geometry.radius':
            r = geom.get('radius')
            return r * 1000 if r else None  # m → mm
        elif key == 'geometry.thickness':
            t = geom.get('thickness')
            return t * 1000 if t else None
        elif key == 'geometry.outer_diameter':
            od = geom.get('outer_diameter')
            return od * 1000 if od else None
        return None
