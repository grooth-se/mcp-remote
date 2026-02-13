"""COMSOL model builder for heat treatment simulation.

Builds and configures COMSOL models for multi-phase heat treatment,
including geometry setup, material assignment, physics configuration,
and boundary conditions for heating, transfer, quenching, and tempering.
"""
import logging
from typing import Optional, Dict, List, Any, TYPE_CHECKING

import numpy as np

from .client import COMSOLClient, COMSOLError

if TYPE_CHECKING:
    from app.models.simulation import Simulation

logger = logging.getLogger(__name__)

# Default boundary condition parameters per phase
DEFAULT_BC_PARAMS = {
    'heating': {
        'htc': 25.0,            # W/m²K furnace convection
        'ambient_temp': 850.0,  # furnace temperature
        'emissivity': 0.85,
        'use_radiation': True,
    },
    'transfer': {
        'htc': 10.0,            # W/m²K natural convection
        'ambient_temp': 25.0,
        'emissivity': 0.85,
        'use_radiation': True,
    },
    'quenching': {
        'htc': 3000.0,          # W/m²K water quench
        'ambient_temp': 25.0,
        'emissivity': 0.3,
        'use_radiation': False,
    },
    'tempering': {
        'htc': 25.0,
        'ambient_temp': 550.0,
        'emissivity': 0.85,
        'use_radiation': True,
    },
}

# Quench media base HTC values
QUENCH_HTC = {
    'water': 3000,
    'oil': 800,
    'polymer': 1200,
    'brine': 4500,
    'air': 25,
}

AGITATION_MULTIPLIER = {
    'none': 1.0,
    'mild': 1.3,
    'moderate': 1.6,
    'strong': 2.0,
    'violent': 2.5,
}


class HeatTreatmentModelBuilder:
    """Builds COMSOL models for heat treatment simulation.

    Mirrors WeldModelBuilder pattern but configured for multi-phase
    heat treatment: heating, transfer, quenching, tempering.

    Parameters
    ----------
    client : COMSOLClient
        Connected COMSOL client instance
    simulation : Simulation
        Simulation ORM object with geometry and HT configuration
    """

    def __init__(self, client: COMSOLClient, simulation: 'Simulation'):
        self.client = client
        self.simulation = simulation
        self._model = None

    def create_model(self) -> Any:
        """Create base COMSOL model with geometry and materials.

        Returns
        -------
        Model
            Configured COMSOL model object
        """
        sim = self.simulation
        model_name = f"HeatTreat_{sim.id}_{sim.name.replace(' ', '_')[:30]}"
        model = self.client.create_model(model_name)
        self._model = model

        # Setup geometry
        self._setup_geometry(model)

        # Setup material from steel grade
        if sim.steel_grade:
            self._setup_material(model, sim.steel_grade)
        else:
            self._setup_default_material(model)

        # Setup initial physics (will be reconfigured per phase)
        self._setup_physics(model)

        # Setup initial study
        self._setup_study(model, 'initial', 300.0)

        logger.info(f"Created HT base model for simulation: {sim.name}")
        return model

    def _setup_geometry(self, model: Any) -> None:
        """Import CAD or create parametric geometry."""
        sim = self.simulation
        geo_config = sim.geometry_dict

        if sim.geometry_type == 'cad' and sim.cad_file_path:
            # Import CAD STEP file
            try:
                import os
                if os.path.exists(sim.cad_file_path):
                    with open(sim.cad_file_path, 'rb') as f:
                        cad_data = f.read()
                    self.client.import_cad(
                        model, cad_data,
                        sim.cad_filename or 'geometry.stp',
                        format='step'
                    )
                    logger.info(f"Imported CAD geometry: {sim.cad_filename}")
                    return
            except Exception as e:
                logger.warning(f"CAD import failed, creating parametric: {e}")

        # Create parametric geometry via COMSOL Java API
        geo_type = sim.geometry_type
        if geo_type == 'cad':
            # Fallback to equivalent geometry
            geo_type = sim.cad_equivalent_type or 'cylinder'
            geo_config = sim.cad_equivalent_geometry_dict or geo_config

        try:
            geom = model.java.component('comp1').geom().create('geom1', 3)

            if geo_type == 'cylinder':
                radius = geo_config.get('radius', 0.05)
                length = geo_config.get('length', 0.1)
                cyl = geom.create('cyl1', 'Cylinder')
                cyl.set('r', str(radius))
                cyl.set('h', str(length))

            elif geo_type == 'plate':
                thickness = geo_config.get('thickness', 0.02)
                width = geo_config.get('width', 0.1)
                length = geo_config.get('length', 0.1)
                blk = geom.create('blk1', 'Block')
                blk.set('size', [str(width), str(thickness), str(length)])

            elif geo_type in ('ring', 'hollow_cylinder'):
                outer_r = geo_config.get('outer_radius',
                          geo_config.get('outer_diameter', 0.1) / 2)
                inner_r = geo_config.get('inner_radius',
                          geo_config.get('inner_diameter', 0.05) / 2)
                length = geo_config.get('length', 0.1)
                # Outer cylinder minus inner
                cyl_out = geom.create('cyl1', 'Cylinder')
                cyl_out.set('r', str(outer_r))
                cyl_out.set('h', str(length))
                cyl_in = geom.create('cyl2', 'Cylinder')
                cyl_in.set('r', str(inner_r))
                cyl_in.set('h', str(length))
                diff = geom.create('dif1', 'Difference')
                diff.selection('input').set('cyl1')
                diff.selection('input2').set('cyl2')

            else:
                # Default: cylinder
                cyl = geom.create('cyl1', 'Cylinder')
                cyl.set('r', '0.05')
                cyl.set('h', '0.1')

            model.build()
            logger.info(f"Created parametric geometry: {geo_type}")

        except Exception as e:
            logger.warning(f"Geometry setup via Java API failed: {e}")

    def _setup_material(self, model: Any, steel: Any) -> None:
        """Configure material properties from steel grade."""
        try:
            mat = model.java.component('comp1').material().create('mat1', 'Common')
            mat.label(f'Steel - {steel.designation}')
            self._add_thermal_properties(model, mat, steel)
            logger.info(f"Configured material: {steel.designation}")
        except Exception as e:
            logger.warning(f"Material setup via Java API failed: {e}")
            self._setup_default_material(model)

    def _add_thermal_properties(self, model: Any, mat: Any, steel: Any) -> None:
        """Add T-dependent thermal properties to material."""
        # Thermal conductivity
        k_prop = steel.get_property('thermal_conductivity')
        if k_prop:
            data = k_prop.data_dict
            if k_prop.property_type == 'constant':
                mat.propertyGroup('def').set('thermalconductivity', str(data.get('value', 45)))
            elif k_prop.property_type == 'curve':
                temps = data.get('temperature', [])
                values = data.get('values', [])
                if temps and values:
                    self._create_interpolation(model, 'k_int', temps, values)
                    mat.propertyGroup('def').set('thermalconductivity', 'k_int(T)')
        else:
            mat.propertyGroup('def').set('thermalconductivity', '45')

        # Density
        rho_prop = steel.get_property('density')
        if rho_prop:
            data = rho_prop.data_dict
            if rho_prop.property_type == 'constant':
                mat.propertyGroup('def').set('density', str(data.get('value', 7850)))
            elif rho_prop.property_type == 'curve':
                temps = data.get('temperature', [])
                values = data.get('values', [])
                if temps and values:
                    self._create_interpolation(model, 'rho_int', temps, values)
                    mat.propertyGroup('def').set('density', 'rho_int(T)')
        else:
            mat.propertyGroup('def').set('density', '7850')

        # Specific heat
        cp_prop = steel.get_property('specific_heat')
        if cp_prop:
            data = cp_prop.data_dict
            if cp_prop.property_type == 'constant':
                mat.propertyGroup('def').set('heatcapacity', str(data.get('value', 500)))
            elif cp_prop.property_type == 'curve':
                temps = data.get('temperature', [])
                values = data.get('values', [])
                if temps and values:
                    self._create_interpolation(model, 'cp_int', temps, values)
                    mat.propertyGroup('def').set('heatcapacity', 'cp_int(T)')
        else:
            mat.propertyGroup('def').set('heatcapacity', '500')

    def _create_interpolation(self, model: Any, name: str,
                              x_data: List[float], y_data: List[float]) -> None:
        """Create interpolation function in COMSOL model."""
        try:
            func = model.java.func().create(name, 'Interpolation')
            func.set('source', 'table')
            table_data = [[str(x), str(y)] for x, y in zip(x_data, y_data)]
            func.setIndex('table', table_data, 0)
            func.set('interp', 'piecewisecubic')
            func.set('extrap', 'linear')
        except Exception as e:
            logger.warning(f"Could not create interpolation function {name}: {e}")

    def _setup_default_material(self, model: Any) -> None:
        """Setup default steel material properties."""
        try:
            mat = model.java.component('comp1').material().create('mat1', 'Common')
            mat.label('Steel (Default)')
            mat.propertyGroup('def').set('thermalconductivity', '45')
            mat.propertyGroup('def').set('density', '7850')
            mat.propertyGroup('def').set('heatcapacity', '500')
        except Exception as e:
            logger.warning(f"Default material setup failed: {e}")

    def _setup_physics(self, model: Any) -> None:
        """Configure Heat Transfer in Solids physics."""
        try:
            ht = model.java.component('comp1').physics().create('ht', 'HeatTransfer', 'geom1')
            ht.label('Heat Transfer')

            # Initial temperature (room temp, will be set per phase)
            init = ht.create('init1', 'init', 3)
            init.set('Tinit', '25[degC]')

            # Convection boundary on external surfaces
            conv = ht.create('hf1', 'HeatFlux', 2)
            conv.set('q0', 'h_conv*(T_amb-T)')

            logger.info("Configured heat transfer physics")
        except Exception as e:
            logger.warning(f"Physics setup failed: {e}")

    def _setup_study(self, model: Any, phase_name: str, duration: float) -> None:
        """Configure transient study for a heat treatment phase."""
        try:
            std = model.java.study().create('std1')
            std.label(f'Transient HT - {phase_name}')

            time_step = std.create('time', 'Transient')
            # Adaptive time stepping
            dt = max(0.1, duration / 200)
            time_range = f'range(0,{dt},{duration})'
            time_step.set('tlist', time_range)
            time_step.set('rtol', '0.01')

            logger.info(f"Configured study for phase: {phase_name}, duration: {duration}s")
        except Exception as e:
            logger.warning(f"Study setup failed: {e}")

    def build_phase(self, model: Any, phase_name: str, phase_config: dict) -> None:
        """Configure model for a specific heat treatment phase.

        Updates boundary conditions and study time range for the phase.

        Parameters
        ----------
        model : Any
            COMSOL model object
        phase_name : str
            Phase name: 'heating', 'transfer', 'quenching', 'tempering'
        phase_config : dict
            Phase configuration from simulation HT config
        """
        bc_params = self._get_bc_params(phase_name, phase_config)

        # Set global parameters for this phase
        self.client.set_parameter(model, 'h_conv', bc_params['htc'],
                                  f'Convection HTC for {phase_name} [W/(m^2*K)]')
        self.client.set_parameter(model, 'T_amb', bc_params['ambient_temp'],
                                  f'Ambient temperature for {phase_name} [degC]')
        self.client.set_parameter(model, 'emissivity', bc_params['emissivity'],
                                  f'Surface emissivity for {phase_name} [-]')

        # Update study time range
        duration = self._get_phase_duration(phase_name, phase_config)
        try:
            dt = max(0.1, duration / 200)
            time_range = f'range(0,{dt},{duration})'
            std = model.java.study('std1')
            std.feature('time').set('tlist', time_range)
        except Exception as e:
            logger.warning(f"Could not update study time for {phase_name}: {e}")

        # Add radiation if enabled
        if bc_params.get('use_radiation', False) and bc_params['emissivity'] > 0:
            try:
                ht = model.java.component('comp1').physics('ht')
                rad = ht.create('rad1', 'SurfaceRadiation', 2)
                rad.set('epsilon', str(bc_params['emissivity']))
                rad.set('Tamb', str(bc_params['ambient_temp'] + 273.15))
            except Exception:
                pass  # Radiation node may already exist

        logger.info(f"Configured phase: {phase_name} (h={bc_params['htc']}, "
                    f"T_amb={bc_params['ambient_temp']}, dur={duration}s)")

    def _get_bc_params(self, phase_name: str, phase_config: dict) -> dict:
        """Extract boundary condition parameters for a phase.

        Parameters
        ----------
        phase_name : str
            Phase name
        phase_config : dict
            Phase configuration dict

        Returns
        -------
        dict
            Keys: htc, ambient_temp, emissivity, use_radiation
        """
        defaults = DEFAULT_BC_PARAMS.get(phase_name, DEFAULT_BC_PARAMS['quenching'])

        if phase_name == 'heating':
            return {
                'htc': phase_config.get('furnace_htc', defaults['htc']),
                'ambient_temp': phase_config.get('target_temperature', defaults['ambient_temp']),
                'emissivity': phase_config.get('furnace_emissivity', defaults['emissivity']),
                'use_radiation': phase_config.get('use_radiation', defaults['use_radiation']),
            }

        elif phase_name == 'transfer':
            return {
                'htc': phase_config.get('htc', defaults['htc']),
                'ambient_temp': phase_config.get('ambient_temperature', defaults['ambient_temp']),
                'emissivity': phase_config.get('emissivity', defaults['emissivity']),
                'use_radiation': phase_config.get('use_radiation', defaults['use_radiation']),
            }

        elif phase_name == 'quenching':
            # Calculate HTC from media and agitation
            media = phase_config.get('media', 'water')
            agitation = phase_config.get('agitation', 'none')
            htc_override = phase_config.get('htc_override')

            if htc_override:
                htc = float(htc_override)
            else:
                base_htc = QUENCH_HTC.get(media, 3000)
                multiplier = AGITATION_MULTIPLIER.get(agitation, 1.0)
                htc = base_htc * multiplier

            return {
                'htc': htc,
                'ambient_temp': phase_config.get('media_temperature', 25.0),
                'emissivity': phase_config.get('emissivity', defaults['emissivity']),
                'use_radiation': phase_config.get('use_radiation', defaults['use_radiation']),
            }

        elif phase_name == 'tempering':
            return {
                'htc': phase_config.get('htc', defaults['htc']),
                'ambient_temp': phase_config.get('temperature', defaults['ambient_temp']),
                'emissivity': phase_config.get('emissivity', defaults['emissivity']),
                'use_radiation': phase_config.get('use_radiation', defaults.get('use_radiation', True)),
            }

        return defaults

    def _get_phase_duration(self, phase_name: str, phase_config: dict) -> float:
        """Get simulation duration for a phase in seconds."""
        if phase_name == 'heating':
            # Heating: hold_time in minutes + estimated ramp time
            hold_min = phase_config.get('hold_time', 60.0)
            return hold_min * 60.0  # Convert to seconds

        elif phase_name == 'transfer':
            return phase_config.get('duration', 10.0)

        elif phase_name == 'quenching':
            return phase_config.get('duration', 300.0)

        elif phase_name == 'tempering':
            hold_min = phase_config.get('hold_time', 120.0)
            return hold_min * 60.0

        return 300.0  # Default 5 minutes

    def get_model(self) -> Any:
        """Get the current model object."""
        return self._model
