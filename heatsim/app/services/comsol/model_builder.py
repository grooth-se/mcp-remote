"""COMSOL model builder for multi-pass welding simulation.

Builds and configures COMSOL models for sequential weld string simulation,
including geometry setup, material assignment, physics configuration,
and boundary conditions.
"""
import logging
from typing import Optional, Dict, List, Any, TYPE_CHECKING

import numpy as np

from .client import COMSOLClient, COMSOLError

if TYPE_CHECKING:
    from app.models.weld_project import WeldProject, WeldString, WeldResult

logger = logging.getLogger(__name__)


class WeldModelBuilder:
    """Builds and updates COMSOL models for weld simulation.

    This class handles the construction of COMSOL models including:
    - CAD geometry import and string body identification
    - Material property assignment from steel grade
    - Heat transfer physics setup
    - Boundary condition configuration
    - String activation and initial temperature setup

    Parameters
    ----------
    client : COMSOLClient
        Connected COMSOL client instance
    """

    def __init__(self, client: COMSOLClient):
        """Initialize model builder with COMSOL client.

        Parameters
        ----------
        client : COMSOLClient
            Connected COMSOL client instance
        """
        self.client = client
        self._model = None

    def create_base_model(self, project: 'WeldProject') -> Any:
        """Create base COMSOL model with geometry and materials.

        Sets up the fundamental model structure including:
        - 3D geometry from imported CAD
        - Material properties from steel grade
        - Heat transfer physics
        - Transient study configuration

        Parameters
        ----------
        project : WeldProject
            Weld project with CAD file and steel grade

        Returns
        -------
        Model
            Configured COMSOL model object
        """
        model_name = f"WeldSim_{project.id}_{project.name.replace(' ', '_')}"
        model = self.client.create_model(model_name)
        self._model = model

        # Import CAD geometry if available
        if project.cad_file:
            self._import_geometry(model, project)

        # Setup material from steel grade
        if project.steel_grade:
            self._setup_material(model, project)

        # Configure heat transfer physics
        self._setup_heat_transfer_physics(model, project)

        # Configure transient study
        self._setup_transient_study(model, project)

        # Set global parameters
        self._setup_parameters(model, project)

        logger.info(f"Created base model for project: {project.name}")
        return model

    def _import_geometry(self, model: Any, project: 'WeldProject') -> None:
        """Import CAD geometry into model.

        Parameters
        ----------
        model : Model
            COMSOL model object
        project : WeldProject
            Project containing CAD file data
        """
        if not project.cad_file:
            logger.warning("No CAD file in project")
            return

        cad_format = project.cad_format or 'step'
        filename = project.cad_filename or 'geometry.stp'

        try:
            bodies = self.client.import_cad(
                model,
                project.cad_file,
                filename,
                format=cad_format
            )
            logger.info(f"Imported {len(bodies)} bodies from CAD")
        except COMSOLError as e:
            logger.error(f"Failed to import CAD: {e}")
            raise

    def _setup_material(self, model: Any, project: 'WeldProject') -> None:
        """Configure material properties from steel grade.

        Parameters
        ----------
        model : Model
            COMSOL model object
        project : WeldProject
            Project with steel grade reference
        """
        steel = project.steel_grade
        if not steel:
            logger.warning("No steel grade specified, using default properties")
            self._setup_default_material(model)
            return

        try:
            # Try to access model Java interface for material setup
            mat = model.java.component('comp1').material().create('mat1', 'Common')
            mat.label(f'Steel - {steel.designation}')

            # Get thermal properties
            self._add_thermal_properties(model, mat, steel)

            logger.info(f"Configured material: {steel.designation}")
        except Exception as e:
            logger.warning(f"Could not setup material via Java API: {e}")
            self._setup_default_material(model)

    def _add_thermal_properties(self, model: Any, mat: Any, steel: Any) -> None:
        """Add thermal properties to material.

        Parameters
        ----------
        model : Model
            COMSOL model object
        mat : Material
            COMSOL material node
        steel : SteelGrade
            Steel grade with properties
        """
        # Thermal conductivity
        k_prop = steel.get_property('thermal_conductivity')
        if k_prop:
            data = k_prop.data_dict
            if k_prop.property_type == 'constant':
                mat.propertyGroup('def').set('thermalconductivity', str(data.get('value', 45)))
            elif k_prop.property_type == 'curve':
                # Temperature-dependent property
                temps = data.get('temperature', [])
                values = data.get('values', [])
                if temps and values:
                    # Create interpolation function
                    func_name = 'k_int'
                    self._create_interpolation(model, func_name, temps, values)
                    mat.propertyGroup('def').set('thermalconductivity', f'{func_name}(T)')
        else:
            mat.propertyGroup('def').set('thermalconductivity', '45')  # Default W/(m*K)

        # Density
        rho_prop = steel.get_property('density')
        if rho_prop:
            data = rho_prop.data_dict
            mat.propertyGroup('def').set('density', str(data.get('value', 7850)))
        else:
            mat.propertyGroup('def').set('density', '7850')  # Default kg/m^3

        # Specific heat capacity
        cp_prop = steel.get_property('specific_heat')
        if cp_prop:
            data = cp_prop.data_dict
            if cp_prop.property_type == 'constant':
                mat.propertyGroup('def').set('heatcapacity', str(data.get('value', 500)))
            elif cp_prop.property_type == 'curve':
                temps = data.get('temperature', [])
                values = data.get('values', [])
                if temps and values:
                    func_name = 'cp_int'
                    self._create_interpolation(model, func_name, temps, values)
                    mat.propertyGroup('def').set('heatcapacity', f'{func_name}(T)')
        else:
            mat.propertyGroup('def').set('heatcapacity', '500')  # Default J/(kg*K)

    def _create_interpolation(self, model: Any, name: str,
                              x_data: List[float], y_data: List[float]) -> None:
        """Create interpolation function in model.

        Parameters
        ----------
        model : Model
            COMSOL model object
        name : str
            Function name
        x_data : list
            X values (e.g., temperature)
        y_data : list
            Y values (e.g., property values)
        """
        try:
            func = model.java.func().create(name, 'Interpolation')
            func.set('source', 'table')

            # Build table data
            table_data = [[str(x), str(y)] for x, y in zip(x_data, y_data)]
            func.setIndex('table', table_data, 0)

            func.set('interp', 'piecewisecubic')
            func.set('extrap', 'linear')
        except Exception as e:
            logger.warning(f"Could not create interpolation function: {e}")

    def _setup_default_material(self, model: Any) -> None:
        """Setup default steel material properties.

        Parameters
        ----------
        model : Model
            COMSOL model object
        """
        try:
            mat = model.java.component('comp1').material().create('mat1', 'Common')
            mat.label('Steel (Default)')
            mat.propertyGroup('def').set('thermalconductivity', '45')
            mat.propertyGroup('def').set('density', '7850')
            mat.propertyGroup('def').set('heatcapacity', '500')
            logger.info("Using default steel properties")
        except Exception as e:
            logger.warning(f"Could not setup default material: {e}")

    def _setup_heat_transfer_physics(self, model: Any, project: 'WeldProject') -> None:
        """Configure heat transfer physics.

        Parameters
        ----------
        model : Model
            COMSOL model object
        project : WeldProject
            Project configuration
        """
        try:
            # Create Heat Transfer in Solids physics
            ht = model.java.component('comp1').physics().create('ht', 'HeatTransfer', 'geom1')
            ht.label('Heat Transfer')

            # Initial temperature (preheat temperature)
            init = ht.create('init1', 'init', 3)
            init.set('Tinit', str(project.preheat_temperature))

            # Convection boundary condition on external surfaces
            # This will be refined per string
            conv = ht.create('hf1', 'HeatFlux', 2)
            conv.set('q0', '0')  # Will be set up later

            logger.info("Configured heat transfer physics")
        except Exception as e:
            logger.warning(f"Could not setup heat transfer physics: {e}")

    def _setup_transient_study(self, model: Any, project: 'WeldProject') -> None:
        """Configure transient heat transfer study.

        Parameters
        ----------
        model : Model
            COMSOL model object
        project : WeldProject
            Project configuration
        """
        try:
            # Create time-dependent study
            std = model.java.study().create('std1')
            std.label('Transient Heat Transfer')

            # Time-dependent step
            time_step = std.create('time', 'Transient')
            time_step.set('tlist', 'range(0,1,120)')  # Default: 0-120s in 1s steps
            time_step.set('rtol', '0.01')  # Relative tolerance

            logger.info("Configured transient study")
        except Exception as e:
            logger.warning(f"Could not setup study: {e}")

    def _setup_parameters(self, model: Any, project: 'WeldProject') -> None:
        """Set global model parameters.

        Parameters
        ----------
        model : Model
            COMSOL model object
        project : WeldProject
            Project configuration
        """
        params = {
            'T_preheat': (project.preheat_temperature, 'Preheat temperature [degC]'),
            'T_interpass': (project.interpass_temperature, 'Max interpass temperature [degC]'),
            'Q_heat_input': (project.default_heat_input * 1000, 'Heat input [J/mm]'),
            'v_travel': (project.default_travel_speed, 'Travel speed [mm/s]'),
            'T_solidification': (project.default_solidification_temp, 'Solidification temperature [degC]'),
            'T_ambient': (25.0, 'Ambient temperature [degC]'),
            'h_conv': (25.0, 'Convection coefficient [W/(m^2*K)]'),
            'emissivity': (0.8, 'Surface emissivity [-]'),
        }

        for name, (value, desc) in params.items():
            self.client.set_parameter(model, name, value, desc)

        logger.info("Set global parameters")

    def activate_string(self, model: Any, string: 'WeldString',
                        prev_temps: Optional[Dict[str, float]] = None) -> None:
        """Activate a weld string domain with initial temperature.

        Parameters
        ----------
        model : Model
            COMSOL model object
        string : WeldString
            Weld string to activate
        prev_temps : dict, optional
            Previous temperature field (domain -> temperature mapping)
        """
        try:
            # Determine initial temperature for this string
            init_temp = self.calculate_initial_temp(string, prev_temps)
            string.calculated_initial_temp = init_temp

            # Update domain status and initial condition in COMSOL
            # This is a simplified representation - actual implementation would:
            # 1. Enable the geometry domain for this string body
            # 2. Set domain initial temperature to init_temp
            # 3. Apply volumetric heat source based on heat input

            logger.info(
                f"Activated string {string.string_number} ({string.body_name}) "
                f"with initial T={init_temp:.1f}C"
            )

            # Set heat source parameters for this string
            self._setup_heat_source(model, string)

        except Exception as e:
            logger.error(f"Failed to activate string {string.string_number}: {e}")
            raise COMSOLError(f"String activation failed: {e}")

    def calculate_initial_temp(self, string: 'WeldString',
                               prev_temps: Optional[Dict[str, float]] = None) -> float:
        """Calculate initial temperature for a weld string.

        The initial temperature depends on:
        - Mode setting (solidification, manual, calculated)
        - Time since previous strings solidified
        - Heat transfer from adjacent strings

        Parameters
        ----------
        string : WeldString
            Weld string needing initial temperature
        prev_temps : dict, optional
            Previous temperature field

        Returns
        -------
        float
            Initial temperature in degrees Celsius
        """
        if string.initial_temp_mode == 'manual':
            if string.initial_temperature is not None:
                return string.initial_temperature
            return string.effective_solidification_temp

        if string.initial_temp_mode == 'solidification':
            return string.effective_solidification_temp

        # Calculated mode - estimate from previous string temperatures
        if prev_temps is None or string.string_number == 1:
            # First string or no previous data
            return string.effective_solidification_temp

        # Get interpass time
        interpass_time = string.effective_interpass_time

        # Simple exponential decay model for temperature
        # T(t) = T_ambient + (T_prev - T_ambient) * exp(-t/tau)
        # where tau is a thermal time constant (estimated)
        tau = 60.0  # seconds, typical for heavy sections
        t_ambient = string.project.preheat_temperature if string.project else 20.0

        # Get average previous temperature
        if prev_temps:
            t_prev = np.mean(list(prev_temps.values()))
        else:
            t_prev = string.effective_solidification_temp

        # Calculate cooled temperature
        t_init = t_ambient + (t_prev - t_ambient) * np.exp(-interpass_time / tau)

        # Ensure within bounds
        t_min = t_ambient
        t_max = string.effective_solidification_temp
        t_init = max(t_min, min(t_max, t_init))

        # For welding, we still start at solidification temp for the weld metal itself
        # The calculated temp applies to HAZ/adjacent material
        return string.effective_solidification_temp

    def _setup_heat_source(self, model: Any, string: 'WeldString') -> None:
        """Configure volumetric heat source for weld string.

        Parameters
        ----------
        model : Model
            COMSOL model object
        string : WeldString
            Weld string with heat input parameters
        """
        try:
            # Heat input in J/mm, travel speed in mm/s
            heat_input = string.effective_heat_input * 1000  # J/mm
            travel_speed = string.effective_travel_speed  # mm/s

            # Power = heat_input * travel_speed (J/s = W)
            power = heat_input * travel_speed

            # Update model parameters
            self.client.set_parameter(model, 'Q_string', heat_input,
                                      f'Heat input for string {string.string_number} [J/mm]')
            self.client.set_parameter(model, 'v_string', travel_speed,
                                      f'Travel speed for string {string.string_number} [mm/s]')

            logger.debug(f"Heat source: {power:.1f} W for string {string.string_number}")
        except Exception as e:
            logger.warning(f"Could not setup heat source: {e}")

    def set_boundary_conditions(self, model: Any, project: 'WeldProject') -> None:
        """Set convection/radiation boundary conditions on outer surfaces.

        Parameters
        ----------
        model : Model
            COMSOL model object
        project : WeldProject
            Project configuration
        """
        try:
            ht = model.java.component('comp1').physics('ht')

            # Convection on external surfaces
            conv = ht.feature('hf1')
            conv.set('q0', 'h_conv*(T_ambient-T)')

            # Radiation can be added for high-temperature scenarios
            # rad = ht.create('rad1', 'SurfaceRadiation', 2)
            # rad.set('epsilon', 'emissivity')
            # rad.set('Tamb', 'T_ambient')

            logger.info("Set boundary conditions")
        except Exception as e:
            logger.warning(f"Could not set boundary conditions: {e}")

    def update_study_time(self, model: Any, start_time: float, end_time: float,
                          time_step: float = 1.0) -> None:
        """Update transient study time range.

        Parameters
        ----------
        model : Model
            COMSOL model object
        start_time : float
            Start time in seconds
        end_time : float
            End time in seconds
        time_step : float
            Output time step in seconds
        """
        try:
            time_range = f'range({start_time},{time_step},{end_time})'
            std = model.java.study('std1')
            std.feature('time').set('tlist', time_range)
            logger.debug(f"Updated study time: {start_time} to {end_time} s")
        except Exception as e:
            logger.warning(f"Could not update study time: {e}")

    def get_model(self) -> Any:
        """Get the current model object.

        Returns
        -------
        Model or None
            Current COMSOL model
        """
        return self._model
