"""Boundary condition handlers for heat transfer simulation.

Supports:
- Convection: q = h * (T_surface - T_ambient)
- Radiation: q = epsilon * sigma * (T_surface^4 - T_ambient^4)
- Combined convection + radiation
- Insulated (adiabatic) boundaries
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


def create_quench_bc(
    process_type: str,
    ambient_temp: float = 25.0,
    emissivity: float = 0.85,
    custom_htc: Optional[float] = None
) -> BoundaryCondition:
    """Factory function to create boundary condition for quench process.

    Parameters
    ----------
    process_type : str
        Process type from PROCESS_TYPES constants
    ambient_temp : float
        Quench medium temperature in Celsius
    emissivity : float
        Surface emissivity for radiation
    custom_htc : float, optional
        Override default HTC value

    Returns
    -------
    BoundaryCondition
        Configured boundary condition
    """
    from app.models.simulation import DEFAULT_HTC

    htc = custom_htc if custom_htc is not None else DEFAULT_HTC.get(process_type, 100)

    return BoundaryCondition(
        htc=htc,
        ambient_temp=ambient_temp,
        emissivity=emissivity
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
