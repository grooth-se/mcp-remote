"""COMSOL model builder for heat treatment simulation.

Builds and configures COMSOL models for multi-phase heat treatment,
including geometry setup, material assignment, physics configuration,
and piecewise boundary conditions spanning all phases in a single study.
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
        'htc': 25.0,            # W/m2K furnace convection
        'ambient_temp': 850.0,  # furnace temperature
        'emissivity': 0.85,
        'use_radiation': True,
    },
    'transfer': {
        'htc': 10.0,            # W/m2K natural convection
        'ambient_temp': 25.0,
        'emissivity': 0.85,
        'use_radiation': True,
    },
    'quenching': {
        'htc': 3000.0,          # W/m2K water quench
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

    Uses a single-study piecewise-BC approach: builds time-dependent
    interpolation functions for h_conv(t) and T_amb(t) covering all
    phases, resulting in one continuous transient solution.

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

    def build_complete_model(self) -> Any:
        """Build model with piecewise BCs for all phases in one study.

        This is the recommended approach: a single continuous transient
        solve covering heating -> transfer -> quenching -> tempering.

        Returns
        -------
        Model
            Fully configured COMSOL model ready to solve
        """
        sim = self.simulation
        model_name = f"HeatTreat_{sim.id}_{sim.name.replace(' ', '_')[:30]}"
        model = self.client.create_model(model_name)
        self._model = model

        # 1. Geometry
        self._setup_geometry(model)

        # 2. Mesh
        self._setup_mesh(model)

        # 3. Material
        if sim.steel_grade:
            self._setup_material(model, sim.steel_grade)
        else:
            self._setup_default_material(model)

        # 4. Build piecewise BC timeline
        ht_config = sim.ht_config or {}
        phase_timeline = self._build_phase_timeline(ht_config)
        total_duration = phase_timeline[-1]['end_time'] if phase_timeline else 300.0

        # 5. Create piecewise interpolation functions
        self._create_piecewise_functions(model, phase_timeline)

        # 6. Physics with piecewise BCs
        self._setup_physics_piecewise(model, ht_config)

        # 7. Probe datasets at 4 radial positions
        self._create_probe_datasets(model)

        # 8. Single transient study
        self._setup_transient_study(model, total_duration, phase_timeline)

        logger.info("Built complete HT model for %s (%.0fs total)",
                    sim.name, total_duration)
        return model

    def create_model(self) -> Any:
        """Create base COMSOL model (legacy per-phase approach).

        Kept for backward compatibility. Prefer build_complete_model().
        """
        sim = self.simulation
        model_name = f"HeatTreat_{sim.id}_{sim.name.replace(' ', '_')[:30]}"
        model = self.client.create_model(model_name)
        self._model = model

        self._setup_geometry(model)
        self._setup_mesh(model)

        if sim.steel_grade:
            self._setup_material(model, sim.steel_grade)
        else:
            self._setup_default_material(model)

        self._setup_physics(model)
        self._setup_study(model, 'initial', 300.0)

        logger.info("Created HT base model for simulation: %s", sim.name)
        return model

    # ---- Geometry ----

    def _setup_geometry(self, model: Any) -> None:
        """Import CAD or create parametric geometry."""
        sim = self.simulation
        geo_config = sim.geometry_dict

        if sim.geometry_type == 'cad' and sim.cad_file_path:
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
                    logger.info("Imported CAD geometry: %s", sim.cad_filename)
                    return
            except Exception as e:
                logger.warning("CAD import failed, creating parametric: %s", e)

        geo_type = sim.geometry_type
        if geo_type == 'cad':
            geo_type = sim.cad_equivalent_type or 'cylinder'
            geo_config = sim.cad_equivalent_geometry_dict or geo_config

        try:
            java = model.java
            java.component().create('comp1', True)
            geom = java.component('comp1').geom().create('geom1', 3)

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
                cyl = geom.create('cyl1', 'Cylinder')
                cyl.set('r', '0.05')
                cyl.set('h', '0.1')

            geom.run('fin')
            logger.info("Created parametric geometry: %s", geo_type)
        except Exception as e:
            logger.warning("Geometry setup via Java API failed: %s", e)

    # ---- Mesh ----

    def _setup_mesh(self, model: Any) -> None:
        """Create tetrahedral mesh with surface refinement."""
        try:
            java = model.java
            mesh = java.component('comp1').mesh().create('mesh1')

            # Free tetrahedral meshing
            ftet = mesh.create('ftet1', 'FreeTet')

            # Size settings - finer near surfaces
            size = mesh.create('size1', 'Size')
            size.set('hauto', 4)  # Moderate mesh density (1=coarsest, 9=finest)

            # Boundary layer refinement near surfaces
            bl = mesh.create('bl1', 'BndLayer')
            bl_prop = bl.create('blp1', 'BndLayerProp')
            bl_prop.set('blnlayers', 3)  # 3 boundary layers
            bl_prop.set('blstretch', 1.2)  # Growth ratio
            # Apply to all external boundaries
            bl.selection().allGeom()

            mesh.run()
            logger.info("Mesh created successfully")
        except Exception as e:
            logger.warning("Mesh setup failed: %s", e)

    # ---- Material ----

    def _setup_material(self, model: Any, steel: Any) -> None:
        """Configure material properties from steel grade."""
        try:
            mat = model.java.component('comp1').material().create('mat1', 'Common')
            mat.label(f'Steel - {steel.designation}')
            # Select all domains
            mat.selection().allGeom()
            self._add_thermal_properties(model, mat, steel)
            logger.info("Configured material: %s", steel.designation)
        except Exception as e:
            logger.warning("Material setup via Java API failed: %s", e)
            self._setup_default_material(model)

    def _add_thermal_properties(self, model: Any, mat: Any, steel: Any) -> None:
        """Add T-dependent thermal properties to material."""
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
            logger.warning("Could not create interpolation function %s: %s", name, e)

    def _setup_default_material(self, model: Any) -> None:
        """Setup default steel material properties."""
        try:
            mat = model.java.component('comp1').material().create('mat1', 'Common')
            mat.label('Steel (Default)')
            mat.selection().allGeom()
            mat.propertyGroup('def').set('thermalconductivity', '45')
            mat.propertyGroup('def').set('density', '7850')
            mat.propertyGroup('def').set('heatcapacity', '500')
        except Exception as e:
            logger.warning("Default material setup failed: %s", e)

    # ---- Piecewise BC timeline ----

    def _build_phase_timeline(self, ht_config: dict) -> List[dict]:
        """Build timeline of phases with start/end times and BC params.

        Returns list of dicts with keys:
            phase_name, start_time, end_time, htc, ambient_temp, emissivity
        """
        timeline = []
        t = 0.0

        phase_order = ['heating', 'transfer', 'quenching', 'tempering']
        for phase_name in phase_order:
            phase_config = ht_config.get(phase_name, {})
            if not phase_config.get('enabled', phase_name == 'quenching'):
                continue

            duration = self._get_phase_duration(phase_name, phase_config)
            bc = self._get_bc_params(phase_name, phase_config)

            timeline.append({
                'phase_name': phase_name,
                'start_time': t,
                'end_time': t + duration,
                'htc': bc['htc'],
                'ambient_temp': bc['ambient_temp'],
                'emissivity': bc['emissivity'],
            })
            t += duration

        return timeline

    def _create_piecewise_functions(self, model: Any, timeline: List[dict]) -> None:
        """Create piecewise interpolation functions h_conv(t) and T_amb(t)."""
        if not timeline:
            return

        # Build piecewise data: (time, h_conv) and (time, T_amb)
        h_data = []
        t_data = []
        for phase in timeline:
            t_start = phase['start_time']
            t_end = phase['end_time']
            h_data.append([t_start, phase['htc']])
            h_data.append([t_end, phase['htc']])
            t_data.append([t_start, phase['ambient_temp']])
            t_data.append([t_end, phase['ambient_temp']])

        try:
            # h_conv(t)
            h_func = model.java.func().create('h_conv_pw', 'Interpolation')
            h_func.set('source', 'table')
            h_table = [[str(row[0]), str(row[1])] for row in h_data]
            h_func.setIndex('table', h_table, 0)
            h_func.set('interp', 'piecewiselinear')
            h_func.set('extrap', 'const')
            h_func.set('argunit', 's')
            h_func.set('fununit', 'W/(m^2*K)')

            # T_amb(t)
            t_func = model.java.func().create('T_amb_pw', 'Interpolation')
            t_func.set('source', 'table')
            t_table = [[str(row[0]), str(row[1])] for row in t_data]
            t_func.setIndex('table', t_table, 0)
            t_func.set('interp', 'piecewiselinear')
            t_func.set('extrap', 'const')
            t_func.set('argunit', 's')
            t_func.set('fununit', 'K')

            logger.info("Created piecewise BC functions: %d phases", len(timeline))
        except Exception as e:
            logger.warning("Piecewise function creation failed: %s", e)

    # ---- Physics ----

    def _setup_physics_piecewise(self, model: Any, ht_config: dict) -> None:
        """Configure Heat Transfer physics with piecewise BCs."""
        try:
            java = model.java
            ht = java.component('comp1').physics().create('ht', 'HeatTransfer', 'geom1')
            ht.label('Heat Transfer')

            # Initial temperature
            heating_config = ht_config.get('heating', {})
            if heating_config.get('enabled', False):
                init_temp = heating_config.get('initial_temperature', 25.0)
            else:
                init_temp = heating_config.get('target_temperature', 850.0)

            init = ht.create('init1', 'init', 3)
            init.set('Tinit', f'{init_temp}[degC]')

            # Convective cooling on ALL external boundaries
            conv = ht.create('conv1', 'ConvectiveCooling', 2)
            conv.selection().all()  # All external boundaries
            conv.set('h', 'h_conv_pw(t)')
            conv.set('Text', 'T_amb_pw(t)')

            logger.info("Configured piecewise heat transfer physics")
        except Exception as e:
            logger.warning("Piecewise physics setup failed: %s", e)

    def _setup_physics(self, model: Any) -> None:
        """Configure Heat Transfer physics (legacy per-phase approach)."""
        try:
            ht = model.java.component('comp1').physics().create('ht', 'HeatTransfer', 'geom1')
            ht.label('Heat Transfer')

            init = ht.create('init1', 'init', 3)
            init.set('Tinit', '25[degC]')

            # Convective cooling with parametric h and T_amb
            conv = ht.create('conv1', 'ConvectiveCooling', 2)
            conv.selection().all()
            conv.set('h', 'h_conv')
            conv.set('Text', 'T_amb')

            logger.info("Configured heat transfer physics")
        except Exception as e:
            logger.warning("Physics setup failed: %s", e)

    # ---- Probe datasets ----

    def _create_probe_datasets(self, model: Any) -> None:
        """Create cut-point datasets at 4 radial positions for extraction.

        Positions: center (0), 1/3 R, 2/3 R, surface (R)
        All at mid-height of the geometry.
        """
        sim = self.simulation
        geo_config = sim.geometry_dict
        geo_type = sim.geometry_type

        if geo_type == 'cad':
            geo_type = sim.cad_equivalent_type or 'cylinder'
            geo_config = sim.cad_equivalent_geometry_dict or geo_config

        # Determine probe coordinates based on geometry
        if geo_type == 'cylinder':
            radius = geo_config.get('radius', 0.05)
            length = geo_config.get('length', 0.1)
            mid_z = length / 2
            positions = {
                'center': [0, 0, mid_z],
                'one_third': [radius / 3, 0, mid_z],
                'two_thirds': [2 * radius / 3, 0, mid_z],
                'surface': [radius * 0.99, 0, mid_z],  # Slightly inside to avoid boundary
            }
        elif geo_type == 'plate':
            thickness = geo_config.get('thickness', 0.02)
            width = geo_config.get('width', 0.1)
            length = geo_config.get('length', 0.1)
            mid_x = width / 2
            mid_z = length / 2
            positions = {
                'center': [mid_x, thickness / 2, mid_z],
                'one_third': [mid_x, thickness / 3, mid_z],
                'two_thirds': [mid_x, 2 * thickness / 3, mid_z],
                'surface': [mid_x, thickness * 0.99, mid_z],
            }
        elif geo_type in ('ring', 'hollow_cylinder'):
            outer_r = geo_config.get('outer_radius',
                      geo_config.get('outer_diameter', 0.1) / 2)
            inner_r = geo_config.get('inner_radius',
                      geo_config.get('inner_diameter', 0.05) / 2)
            length = geo_config.get('length', 0.1)
            mid_z = length / 2
            wall = outer_r - inner_r
            mid_r = inner_r + wall / 2
            positions = {
                'center': [mid_r, 0, mid_z],
                'one_third': [inner_r + wall / 3, 0, mid_z],
                'two_thirds': [inner_r + 2 * wall / 3, 0, mid_z],
                'surface': [outer_r * 0.99, 0, mid_z],
            }
        else:
            # Default cylinder
            positions = {
                'center': [0, 0, 0.05],
                'one_third': [0.017, 0, 0.05],
                'two_thirds': [0.033, 0, 0.05],
                'surface': [0.049, 0, 0.05],
            }

        try:
            java = model.java
            for name, coords in positions.items():
                ds_tag = f'probe_{name}'
                ds = java.result().dataset().create(ds_tag, 'CutPoint3D')
                ds.set('pointx', str(coords[0]))
                ds.set('pointy', str(coords[1]))
                ds.set('pointz', str(coords[2]))
                ds.label(f'Probe: {name}')

            logger.info("Created 4 probe datasets")
        except Exception as e:
            logger.warning("Probe dataset creation failed: %s", e)

    # ---- Study ----

    def _setup_transient_study(self, model: Any, total_duration: float,
                                timeline: List[dict]) -> None:
        """Configure single transient study covering all phases."""
        try:
            std = model.java.study().create('std1')
            std.label('Transient Heat Treatment')

            time_step = std.create('time', 'Transient')

            # Build output time list with finer steps during quenching
            time_points = set()
            for phase in timeline:
                t0 = phase['start_time']
                t1 = phase['end_time']
                dur = t1 - t0

                if phase['phase_name'] == 'quenching':
                    # Fine timesteps during quenching (0.5s or dur/200)
                    dt = max(0.5, dur / 200)
                else:
                    # Coarser for heating/transfer/tempering
                    dt = max(1.0, dur / 100)

                for t in np.arange(t0, t1 + dt/2, dt):
                    time_points.add(round(float(t), 2))

            sorted_times = sorted(time_points)
            time_str = ' '.join(str(t) for t in sorted_times)
            time_step.set('tlist', time_str)
            time_step.set('rtol', '0.005')

            logger.info("Configured transient study: %.0fs, %d output times",
                        total_duration, len(sorted_times))
        except Exception as e:
            logger.warning("Study setup failed: %s", e)

    def _setup_study(self, model: Any, phase_name: str, duration: float) -> None:
        """Configure transient study (legacy per-phase approach)."""
        try:
            std = model.java.study().create('std1')
            std.label(f'Transient HT - {phase_name}')
            time_step = std.create('time', 'Transient')
            dt = max(0.1, duration / 200)
            time_range = f'range(0,{dt},{duration})'
            time_step.set('tlist', time_range)
            time_step.set('rtol', '0.01')
            logger.info("Configured study for phase: %s, duration: %ss", phase_name, duration)
        except Exception as e:
            logger.warning("Study setup failed: %s", e)

    # ---- Legacy per-phase interface ----

    def build_phase(self, model: Any, phase_name: str, phase_config: dict) -> None:
        """Configure model for a specific phase (legacy approach)."""
        bc_params = self._get_bc_params(phase_name, phase_config)
        self.client.set_parameter(model, 'h_conv', bc_params['htc'],
                                  f'Convection HTC for {phase_name} [W/(m^2*K)]')
        self.client.set_parameter(model, 'T_amb', bc_params['ambient_temp'],
                                  f'Ambient temperature for {phase_name} [degC]')
        self.client.set_parameter(model, 'emissivity', bc_params['emissivity'],
                                  f'Surface emissivity for {phase_name} [-]')

        duration = self._get_phase_duration(phase_name, phase_config)
        try:
            dt = max(0.1, duration / 200)
            time_range = f'range(0,{dt},{duration})'
            std = model.java.study('std1')
            std.feature('time').set('tlist', time_range)
        except Exception as e:
            logger.warning("Could not update study time for %s: %s", phase_name, e)

        logger.info("Configured phase: %s (h=%.0f, T_amb=%.0f, dur=%.0fs)",
                    phase_name, bc_params['htc'], bc_params['ambient_temp'], duration)

    # ---- Helper methods ----

    def _get_bc_params(self, phase_name: str, phase_config: dict) -> dict:
        """Extract boundary condition parameters for a phase."""
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
            return phase_config.get('hold_time', 60.0) * 60.0
        elif phase_name == 'transfer':
            return phase_config.get('duration', 10.0)
        elif phase_name == 'quenching':
            return phase_config.get('duration', 300.0)
        elif phase_name == 'tempering':
            return phase_config.get('hold_time', 120.0) * 60.0
        return 300.0

    def get_model(self) -> Any:
        """Get the current model object."""
        return self._model
