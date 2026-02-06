"""Boundary condition handlers for heat transfer simulation.

Supports:
- Convection: q = h * (T_surface - T_ambient)
- Radiation: q = epsilon * sigma * (T_surface^4 - T_ambient^4)
- Combined convection + radiation
- Insulated (adiabatic) boundaries
- Multi-phase heat treatment boundary conditions
"""
from dataclasses import dataclass
from typing import Optional

# Stefan-Boltzmann constant
STEFAN_BOLTZMANN = 5.67e-8  # W/(m²·K⁴)


@dataclass
class BoundaryCondition:
    """Boundary condition with convection and optional radiation.

    Parameters
    ----------
    htc : float
        Heat transfer coefficient W/(m²·K)
    ambient_temp : float
        Ambient/quench medium temperature (°C)
    emissivity : float
        Surface emissivity for radiation (0-1, 0 = no radiation)
    radiation_ambient : float, optional
        Radiation sink temperature (default = ambient_temp)
    """
    htc: float
    ambient_temp: float
    emissivity: float = 0.0
    radiation_ambient: Optional[float] = None

    def heat_flux(self, surface_temp: float) -> float:
        """Calculate total heat flux from surface (W/m²).

        Parameters
        ----------
        surface_temp : float
            Surface temperature in Celsius

        Returns
        -------
        float
            Heat flux in W/m² (positive = heat leaving surface)
        """
        # Convective heat flux
        q_conv = self.htc * (surface_temp - self.ambient_temp)

        # Radiative heat flux (if emissivity > 0)
        q_rad = 0.0
        if self.emissivity > 0:
            T_surf_K = surface_temp + 273.15
            T_amb_K = (self.radiation_ambient or self.ambient_temp) + 273.15
            q_rad = self.emissivity * STEFAN_BOLTZMANN * (T_surf_K**4 - T_amb_K**4)

        return q_conv + q_rad

    def linearized_htc(self, surface_temp: float) -> float:
        """Get linearized effective HTC including radiation.

        For implicit schemes, linearize radiation as:
        h_rad = epsilon * sigma * (T_s^2 + T_amb^2) * (T_s + T_amb)

        Parameters
        ----------
        surface_temp : float
            Surface temperature in Celsius

        Returns
        -------
        float
            Effective heat transfer coefficient including radiation
        """
        h_eff = self.htc

        if self.emissivity > 0:
            T_surf_K = surface_temp + 273.15
            T_amb_K = (self.radiation_ambient or self.ambient_temp) + 273.15
            h_rad = self.emissivity * STEFAN_BOLTZMANN * (
                T_surf_K**2 + T_amb_K**2
            ) * (T_surf_K + T_amb_K)
            h_eff += h_rad

        return h_eff

    def update_ambient(self, new_ambient: float, new_radiation_ambient: Optional[float] = None):
        """Update ambient temperature (for phase transitions).

        Parameters
        ----------
        new_ambient : float
            New ambient temperature in Celsius
        new_radiation_ambient : float, optional
            New radiation sink temperature
        """
        self.ambient_temp = new_ambient
        if new_radiation_ambient is not None:
            self.radiation_ambient = new_radiation_ambient


@dataclass
class InsulatedBoundary:
    """Adiabatic (insulated) boundary condition.

    Used for symmetry boundaries (center of cylinder/plate).
    """
    ambient_temp: float = 25.0  # Not used, but kept for interface consistency

    def heat_flux(self, surface_temp: float) -> float:
        """Zero heat flux for insulated boundary."""
        return 0.0

    def linearized_htc(self, surface_temp: float) -> float:
        """Zero HTC for insulated boundary."""
        return 0.0


def create_heating_bc(
    target_temperature: float,
    htc: float = 25.0,
    emissivity: float = 0.85,
    use_radiation: bool = True
) -> BoundaryCondition:
    """Create boundary condition for furnace heating phase.

    Parameters
    ----------
    target_temperature : float
        Furnace/target temperature in Celsius
    htc : float
        Convection coefficient in furnace (W/m²K)
    emissivity : float
        Surface emissivity for radiation
    use_radiation : bool
        Whether to include radiation heat transfer

    Returns
    -------
    BoundaryCondition
        Configured boundary condition for heating
    """
    return BoundaryCondition(
        htc=htc,
        ambient_temp=target_temperature,
        emissivity=emissivity if use_radiation else 0.0,
        radiation_ambient=target_temperature
    )


def create_transfer_bc(
    ambient_temperature: float = 25.0,
    htc: float = 10.0,
    emissivity: float = 0.85,
    use_radiation: bool = True
) -> BoundaryCondition:
    """Create boundary condition for transfer phase (furnace to quench).

    Parameters
    ----------
    ambient_temperature : float
        Ambient air temperature in Celsius
    htc : float
        Natural convection coefficient (W/m²K)
    emissivity : float
        Surface emissivity for radiation
    use_radiation : bool
        Whether to include radiation (significant at high temps)

    Returns
    -------
    BoundaryCondition
        Configured boundary condition for transfer
    """
    return BoundaryCondition(
        htc=htc,
        ambient_temp=ambient_temperature,
        emissivity=emissivity if use_radiation else 0.0,
        radiation_ambient=ambient_temperature
    )


def create_quench_bc(
    media: str = 'water',
    media_temperature: float = 25.0,
    agitation: str = 'moderate',
    htc_override: Optional[float] = None,
    emissivity: float = 0.3,
    use_radiation: bool = False
) -> BoundaryCondition:
    """Create boundary condition for quenching phase.

    Parameters
    ----------
    media : str
        Quench media type (water, oil, polymer, brine, air)
    media_temperature : float
        Quench bath temperature in Celsius
    agitation : str
        Agitation level (none, mild, moderate, strong, violent)
    htc_override : float, optional
        Custom HTC override (ignores media/agitation calculation)
    emissivity : float
        Surface emissivity (usually lower due to vapor/film)
    use_radiation : bool
        Whether to include radiation (usually negligible in liquid)

    Returns
    -------
    BoundaryCondition
        Configured boundary condition for quenching
    """
    from app.models.simulation import calculate_quench_htc

    if htc_override is not None:
        htc = htc_override
    else:
        htc = calculate_quench_htc(media, agitation, media_temperature)

    return BoundaryCondition(
        htc=htc,
        ambient_temp=media_temperature,
        emissivity=emissivity if use_radiation else 0.0,
        radiation_ambient=media_temperature
    )


def create_tempering_bc(
    temperature: float = 550.0,
    htc: float = 25.0,
    emissivity: float = 0.85,
    cooling_method: str = 'air'
) -> BoundaryCondition:
    """Create boundary condition for tempering phase.

    Parameters
    ----------
    temperature : float
        Tempering furnace temperature in Celsius
    htc : float
        Convection coefficient (W/m²K)
    emissivity : float
        Surface emissivity for radiation
    cooling_method : str
        'air' or 'furnace' - determines if radiation is significant

    Returns
    -------
    BoundaryCondition
        Configured boundary condition for tempering
    """
    # In tempering furnace, radiation is significant
    use_radiation = True

    return BoundaryCondition(
        htc=htc,
        ambient_temp=temperature,
        emissivity=emissivity if use_radiation else 0.0,
        radiation_ambient=temperature
    )


def create_cooling_bc(
    ambient_temperature: float = 25.0,
    htc: float = 25.0,
    emissivity: float = 0.85,
    cooling_method: str = 'air'
) -> BoundaryCondition:
    """Create boundary condition for cooling after tempering.

    Parameters
    ----------
    ambient_temperature : float
        Ambient temperature in Celsius
    htc : float
        Convection coefficient (W/m²K)
    emissivity : float
        Surface emissivity for radiation
    cooling_method : str
        'air' or 'furnace'

    Returns
    -------
    BoundaryCondition
        Configured boundary condition for cooling
    """
    # Air cooling: higher HTC, radiation significant at high temps
    # Furnace cooling: low HTC, use radiation
    if cooling_method == 'air':
        use_radiation = True
    else:
        # Furnace cooling - slow cooling with radiation
        htc = 5.0  # Very low convection
        use_radiation = True

    return BoundaryCondition(
        htc=htc,
        ambient_temp=ambient_temperature,
        emissivity=emissivity if use_radiation else 0.0,
        radiation_ambient=ambient_temperature
    )


def estimate_biot_number(htc: float, length: float, k: float) -> float:
    """Calculate Biot number for lumped capacitance analysis.

    Bi = h * L / k

    If Bi < 0.1, lumped capacitance is valid (uniform temperature).

    Parameters
    ----------
    htc : float
        Heat transfer coefficient (W/m²K)
    length : float
        Characteristic length (m)
    k : float
        Thermal conductivity (W/mK)

    Returns
    -------
    float
        Biot number
    """
    return htc * length / k
