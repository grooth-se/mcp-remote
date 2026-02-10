"""Simplified geometry classes for heat transfer simulation.

Supports:
- Cylinder: 1D radial heat transfer (r direction)
- Plate: 1D through-thickness (x direction)
- Ring: 1D radial with inner/outer boundaries
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple
import numpy as np


@dataclass
class GeometryBase(ABC):
    """Base class for simplified geometries."""

    @abstractmethod
    def create_mesh(self, n_nodes: int) -> np.ndarray:
        """Create spatial mesh for finite difference."""
        pass

    @abstractmethod
    def get_surface_area(self, position: float) -> float:
        """Get surface area at radial/thickness position."""
        pass

    @abstractmethod
    def get_volume_element(self, position: float, dr: float) -> float:
        """Get volume of element at position."""
        pass

    @property
    @abstractmethod
    def characteristic_length(self) -> float:
        """Get characteristic length for Biot number."""
        pass


@dataclass
class Cylinder(GeometryBase):
    """Solid cylinder geometry for 1D radial heat transfer.

    Parameters
    ----------
    radius : float
        Outer radius in meters
    length : float
        Axial length in meters (for volume calculations)
    """
    radius: float
    length: float = 1.0

    def create_mesh(self, n_nodes: int) -> np.ndarray:
        """Create radial mesh from center (r=0) to surface (r=R)."""
        return np.linspace(0, self.radius, n_nodes)

    def get_surface_area(self, position: float) -> float:
        """Cylindrical surface area at radius r."""
        return 2 * np.pi * position * self.length

    def get_volume_element(self, position: float, dr: float) -> float:
        """Annular volume element: 2*pi*r*dr*L."""
        return 2 * np.pi * position * dr * self.length

    @property
    def outer_surface_area(self) -> float:
        """Total outer surface area (cylindrical + end caps)."""
        return 2 * np.pi * self.radius * self.length + 2 * np.pi * self.radius**2

    @property
    def volume(self) -> float:
        """Total volume."""
        return np.pi * self.radius**2 * self.length

    @property
    def characteristic_length(self) -> float:
        """Volume / Surface area ratio."""
        return self.volume / self.outer_surface_area

    def __str__(self) -> str:
        return f"Cylinder(R={self.radius*1000:.1f}mm, L={self.length*1000:.1f}mm)"


@dataclass
class Plate(GeometryBase):
    """Infinite plate geometry for 1D through-thickness heat transfer.

    Symmetric about centerline - only solve half thickness.

    Parameters
    ----------
    thickness : float
        Total plate thickness in meters
    width : float
        Plate width (for area calculations)
    length : float
        Plate length (for area calculations)
    """
    thickness: float
    width: float = 1.0
    length: float = 1.0

    def create_mesh(self, n_nodes: int) -> np.ndarray:
        """Create mesh from center (x=0) to surface (x=t/2)."""
        return np.linspace(0, self.thickness / 2, n_nodes)

    def get_surface_area(self, position: float) -> float:
        """Plate area (constant for 1D)."""
        return self.width * self.length

    def get_volume_element(self, position: float, dx: float) -> float:
        """Slab volume element."""
        return self.width * self.length * dx

    @property
    def outer_surface_area(self) -> float:
        """Total surface area (both faces)."""
        return 2 * self.width * self.length

    @property
    def volume(self) -> float:
        """Total volume."""
        return self.thickness * self.width * self.length

    @property
    def characteristic_length(self) -> float:
        """Half thickness for plate."""
        return self.thickness / 2

    def __str__(self) -> str:
        return f"Plate(t={self.thickness*1000:.1f}mm)"


@dataclass
class Ring(GeometryBase):
    """Hollow cylinder (ring) geometry for 1D radial heat transfer.

    Parameters
    ----------
    inner_radius : float
        Inner radius in meters
    outer_radius : float
        Outer radius in meters
    length : float
        Axial length in meters
    """
    inner_radius: float
    outer_radius: float
    length: float = 1.0

    def create_mesh(self, n_nodes: int) -> np.ndarray:
        """Create radial mesh from inner to outer radius."""
        return np.linspace(self.inner_radius, self.outer_radius, n_nodes)

    def get_surface_area(self, position: float) -> float:
        """Cylindrical surface area at radius r."""
        return 2 * np.pi * position * self.length

    def get_volume_element(self, position: float, dr: float) -> float:
        """Annular volume element."""
        return 2 * np.pi * position * dr * self.length

    @property
    def wall_thickness(self) -> float:
        """Wall thickness of ring."""
        return self.outer_radius - self.inner_radius

    @property
    def outer_surface_area(self) -> float:
        """Outer cylindrical surface area."""
        return 2 * np.pi * self.outer_radius * self.length

    @property
    def inner_surface_area(self) -> float:
        """Inner cylindrical surface area."""
        return 2 * np.pi * self.inner_radius * self.length

    @property
    def volume(self) -> float:
        """Total volume."""
        return np.pi * (self.outer_radius**2 - self.inner_radius**2) * self.length

    @property
    def characteristic_length(self) -> float:
        """Wall thickness for ring."""
        return self.wall_thickness

    def __str__(self) -> str:
        return f"Ring(Ri={self.inner_radius*1000:.1f}mm, Ro={self.outer_radius*1000:.1f}mm)"


def create_geometry(geometry_type: str, config: dict) -> GeometryBase:
    """Factory function to create geometry from type and config.

    Parameters
    ----------
    geometry_type : str
        One of 'cylinder', 'plate', 'ring'
    config : dict
        Geometry parameters (values in mm, converted to meters internally)

    Returns
    -------
    GeometryBase
        Geometry instance
    """
    # Convert mm to meters (config stores dimensions in mm for UI convenience)
    mm_to_m = 0.001

    if geometry_type == 'cylinder':
        return Cylinder(
            radius=config.get('radius', 50) * mm_to_m,
            length=config.get('length', 100) * mm_to_m
        )
    elif geometry_type == 'plate':
        return Plate(
            thickness=config.get('thickness', 20) * mm_to_m,
            width=config.get('width', 100) * mm_to_m,
            length=config.get('length', 100) * mm_to_m
        )
    elif geometry_type == 'ring':
        return Ring(
            inner_radius=config.get('inner_radius', 20) * mm_to_m,
            outer_radius=config.get('outer_radius', 50) * mm_to_m,
            length=config.get('length', 100) * mm_to_m
        )
    else:
        raise ValueError(f"Unknown geometry type: {geometry_type}")
