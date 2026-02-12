"""Sensitivity analysis for heat treatment simulation parameters.

Varies one parameter at a time (OAT) and measures impact on key outputs:
t8/5, core cooling rate, surface cooling rate, predicted hardness.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import copy
import logging
import numpy as np

from app.services.heat_solver import MultiPhaseHeatSolver, SolverConfig
from app.services.geometry import create_geometry

logger = logging.getLogger(__name__)


# Parameter definitions
SENSITIVITY_PARAMETERS = {
    'austenitizing_temp': {
        'label': 'Austenitizing Temperature',
        'unit': '°C',
        'variations': [-0.10, -0.05, 0.05, 0.10],
    },
    'quench_htc': {
        'label': 'Quench HTC',
        'unit': 'W/m²K',
        'variations': [-0.50, -0.25, 0.25, 0.50],
    },
    'transfer_time': {
        'label': 'Transfer Time',
        'unit': 's',
        'variations': [-0.50, -0.25, 0.25, 0.50],
    },
    'tempering_temp': {
        'label': 'Tempering Temperature',
        'unit': '°C',
        'variations': [-0.10, -0.05, 0.05, 0.10],
    },
    'part_size': {
        'label': 'Part Size',
        'unit': 'mm',
        'variations': [-0.25, -0.10, 0.10, 0.25],
    },
}


@dataclass
class SensitivityResult:
    """Result from sensitivity analysis of one parameter."""
    parameter: str
    label: str
    unit: str
    base_value: float
    variations: List[float]
    actual_values: List[float] = field(default_factory=list)
    outputs: Dict[str, List[float]] = field(default_factory=dict)
    base_outputs: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'parameter': self.parameter,
            'label': self.label,
            'unit': self.unit,
            'base_value': self.base_value,
            'variations': self.variations,
            'actual_values': self.actual_values,
            'outputs': self.outputs,
            'base_outputs': self.base_outputs,
        }


@dataclass
class SensitivityAnalysisResult:
    """Complete sensitivity analysis results."""
    parameters: List[SensitivityResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {'parameters': [p.to_dict() for p in self.parameters]}


OUTPUT_KEYS = ['t8_5', 'core_cooling_rate', 'surface_cooling_rate',
               'hardness_hv_center', 'hardness_hv_surface']


class SensitivityAnalyzer:
    """Performs one-at-a-time sensitivity analysis on a simulation."""

    def __init__(self, simulation):
        self.sim = simulation

    def analyze(self, parameters: Optional[List[str]] = None) -> SensitivityAnalysisResult:
        """Run OAT sensitivity analysis.

        Parameters
        ----------
        parameters : list of str, optional
            Which parameters to analyze. Defaults to all applicable.

        Returns
        -------
        SensitivityAnalysisResult
        """
        if parameters is None:
            parameters = self._get_applicable_parameters()

        base_outputs = self._get_base_outputs()
        result = SensitivityAnalysisResult()

        for param_key in parameters:
            if param_key not in SENSITIVITY_PARAMETERS:
                continue

            param_def = SENSITIVITY_PARAMETERS[param_key]
            base_value = self._get_parameter_value(param_key)
            if base_value is None or base_value == 0:
                continue

            param_result = SensitivityResult(
                parameter=param_key,
                label=param_def['label'],
                unit=param_def['unit'],
                base_value=round(base_value, 2),
                variations=param_def['variations'],
                base_outputs=base_outputs,
            )

            for var in param_def['variations']:
                new_value = base_value * (1 + var)
                param_result.actual_values.append(round(new_value, 2))

                outputs = self._run_with_modified_param(param_key, new_value)
                for key in OUTPUT_KEYS:
                    if key not in param_result.outputs:
                        param_result.outputs[key] = []
                    param_result.outputs[key].append(outputs.get(key, 0.0))

            result.parameters.append(param_result)

        return result

    def _get_applicable_parameters(self) -> List[str]:
        """Determine which parameters are applicable to this simulation."""
        params = ['austenitizing_temp', 'quench_htc', 'transfer_time', 'part_size']
        ht_config = self.sim.ht_config or {}
        tempering = ht_config.get('tempering', {})
        if tempering.get('enabled', False):
            params.append('tempering_temp')
        return params

    def _get_parameter_value(self, param_key: str) -> Optional[float]:
        """Get current value of a parameter from the simulation config."""
        ht = self.sim.ht_config or {}
        geom = self.sim.geometry_dict or {}

        if param_key == 'austenitizing_temp':
            return ht.get('heating', {}).get('target_temperature')
        elif param_key == 'quench_htc':
            q = ht.get('quenching', {})
            htc = q.get('htc_effective') or q.get('htc_override')
            if htc:
                return htc
            from app.models.simulation import calculate_quench_htc
            return calculate_quench_htc(
                q.get('media', 'water'),
                q.get('agitation', 'moderate'),
                q.get('media_temperature', 25)
            )
        elif param_key == 'transfer_time':
            return ht.get('transfer', {}).get('duration', 30.0)
        elif param_key == 'tempering_temp':
            return ht.get('tempering', {}).get('temperature')
        elif param_key == 'part_size':
            if self.sim.geometry_type == 'cylinder':
                return geom.get('radius', 0.05) * 2000  # m radius -> mm diameter
            elif self.sim.geometry_type == 'plate':
                return geom.get('thickness', 0.02) * 1000  # m -> mm
            elif self.sim.geometry_type == 'hollow_cylinder':
                od = geom.get('outer_radius', geom.get('outer_diameter', 0.1) / 2) * 2000
                return od
            elif self.sim.geometry_type == 'ring':
                return geom.get('outer_radius', 0.05) * 2000
        return None

    def _get_base_outputs(self) -> Dict[str, float]:
        """Extract base outputs from existing simulation results."""
        outputs = {}
        full_result = self.sim.results.filter_by(result_type='full_cycle').first()
        if full_result:
            t8_5 = full_result.t_800_500 or 0.0
            outputs['t8_5'] = round(t8_5, 2)
            outputs['core_cooling_rate'] = round(300.0 / max(t8_5, 0.1), 1)

        # Surface cooling rate from multi-position data
        if full_result:
            data = full_result.data_dict
            if data and 'surface' in data:
                times = np.array(full_result.time_array)
                surface_temps = np.array(data['surface'])
                if len(times) > 2:
                    dtdt = np.gradient(surface_temps, times)
                    outputs['surface_cooling_rate'] = round(abs(float(np.min(dtdt))), 1)

        hardness_result = self.sim.results.filter_by(result_type='hardness_prediction').first()
        if hardness_result:
            hdata = hardness_result.data_dict
            outputs['hardness_hv_center'] = hdata.get('hardness_hv', {}).get('center', 0)
            outputs['hardness_hv_surface'] = hdata.get('hardness_hv', {}).get('surface', 0)

        return outputs

    def _run_with_modified_param(self, param_key: str, new_value: float) -> Dict[str, float]:
        """Run a single solver with one parameter modified."""
        try:
            ht_config = copy.deepcopy(self.sim.ht_config or {})
            geom_config = copy.deepcopy(self.sim.geometry_dict or {})

            # Apply modification
            self._apply_parameter_change(param_key, new_value, ht_config, geom_config)

            # Build geometry
            geom_type = self.sim.cad_equivalent_type or self.sim.geometry_type
            if self.sim.geometry_type == 'cad':
                geom_config = copy.deepcopy(self.sim.cad_equivalent_geometry_dict or geom_config)
                if param_key == 'part_size':
                    self._apply_parameter_change(param_key, new_value, ht_config, geom_config)

            geometry = create_geometry(geom_type, geom_config)

            # Reduced resolution for speed
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

            # Solver
            solver = MultiPhaseHeatSolver(geometry, config=solver_config)
            solver.set_material(k_prop, cp_prop, density, emissivity)
            solver.configure_from_ht_config(ht_config)

            heating_cfg = ht_config.get('heating', {})
            if heating_cfg.get('enabled', False):
                initial_temp = heating_cfg.get('initial_temperature', 25.0)
            else:
                initial_temp = heating_cfg.get('target_temperature', 850.0)

            result = solver.solve(initial_temperature=initial_temp)

            # Extract outputs
            outputs = {
                't8_5': round(result.t8_5 or 0.0, 2),
                'core_cooling_rate': round(300.0 / max(result.t8_5 or 0.1, 0.1), 1),
                'surface_cooling_rate': 0.0,
                'hardness_hv_center': 0.0,
                'hardness_hv_surface': 0.0,
            }

            # Surface cooling rate
            n_pos = result.temperature.shape[1] if result.temperature.ndim > 1 else 1
            if n_pos > 1:
                surface_temp = result.temperature[:, -1]
                dtdt = np.gradient(surface_temp, result.time)
                outputs['surface_cooling_rate'] = round(abs(float(np.min(dtdt))), 1)

            # Hardness prediction
            diagram = grade.phase_diagrams.first()
            if diagram and grade.composition:
                from app.services.phase_tracker import PhaseTracker
                from app.services.hardness_predictor import predict_hardness_profile
                tracker = PhaseTracker(diagram)
                try:
                    hr = predict_hardness_profile(
                        grade.composition, result.temperature, result.time, tracker
                    )
                    outputs['hardness_hv_center'] = hr.hardness_hv.get('center', 0)
                    outputs['hardness_hv_surface'] = hr.hardness_hv.get('surface', 0)
                except Exception:
                    pass

            return outputs

        except Exception as e:
            logger.error(f"Sensitivity run failed for {param_key}={new_value}: {e}")
            return {k: 0.0 for k in OUTPUT_KEYS}

    def _apply_parameter_change(self, param_key, new_value, ht_config, geom_config):
        """Apply parameter change to configs in-place."""
        if param_key == 'austenitizing_temp':
            if 'heating' in ht_config:
                ht_config['heating']['target_temperature'] = new_value
        elif param_key == 'quench_htc':
            if 'quenching' in ht_config:
                ht_config['quenching']['htc_override'] = new_value
        elif param_key == 'transfer_time':
            if 'transfer' in ht_config:
                ht_config['transfer']['duration'] = max(new_value, 1.0)
        elif param_key == 'tempering_temp':
            if 'tempering' in ht_config:
                ht_config['tempering']['temperature'] = new_value
        elif param_key == 'part_size':
            # Convert mm back to meters
            if 'radius' in geom_config:
                geom_config['radius'] = new_value / 2000  # mm diameter -> m radius
            elif 'thickness' in geom_config:
                geom_config['thickness'] = new_value / 1000
            elif 'outer_radius' in geom_config:
                ratio = new_value / 2000 / geom_config['outer_radius']
                geom_config['outer_radius'] = new_value / 2000
                if 'inner_radius' in geom_config:
                    geom_config['inner_radius'] *= ratio
