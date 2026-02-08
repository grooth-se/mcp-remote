"""CAD geometry analysis service for STEP file import.

This module provides functionality to analyze STEP files and extract
geometric properties (volume, surface area, bounding box) for use in
equivalent 1D heat treatment simulations.

The key insight is that for thermal analysis, the characteristic length
L_c = V/A (volume/surface area) determines the thermal response. By
calculating this from arbitrary 3D CAD geometry, we can create an
equivalent 1D geometry (cylinder or plate) that produces similar
thermal behavior in the simulation.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Tuple, Optional
import math


@dataclass
class CADAnalysisResult:
    """Results from analyzing a STEP CAD file.

    Attributes:
        filename: Original STEP filename
        volume: Volume in cubic meters
        surface_area: Surface area in square meters
        characteristic_length: V/A ratio in meters (key thermal parameter)
        bounding_box: (x, y, z) dimensions in meters
        equivalent_type: 'cylinder' or 'plate'
        equivalent_params: Parameters for the equivalent 1D geometry
    """
    filename: str
    volume: float
    surface_area: float
    characteristic_length: float
    bounding_box: Tuple[float, float, float]
    equivalent_type: str
    equivalent_params: Dict[str, float]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'filename': self.filename,
            'volume': self.volume,
            'surface_area': self.surface_area,
            'characteristic_length': self.characteristic_length,
            'bounding_box': list(self.bounding_box),
            'equivalent_type': self.equivalent_type,
            'equivalent_params': self.equivalent_params
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CADAnalysisResult':
        """Create from dictionary."""
        return cls(
            filename=data['filename'],
            volume=data['volume'],
            surface_area=data['surface_area'],
            characteristic_length=data['characteristic_length'],
            bounding_box=tuple(data['bounding_box']),
            equivalent_type=data['equivalent_type'],
            equivalent_params=data['equivalent_params']
        )


class CADGeometryAnalyzer:
    """Analyzer for extracting thermal properties from STEP files.

    Uses CadQuery to load and analyze STEP files, extracting volume
    and surface area to calculate equivalent 1D geometry parameters.
    """

    def __init__(self, step_path: Path):
        """Initialize analyzer with path to STEP file.

        Args:
            step_path: Path to the STEP file to analyze
        """
        self.step_path = Path(step_path)
        if not self.step_path.exists():
            raise FileNotFoundError(f"STEP file not found: {step_path}")

        self._solid = None
        self._load_step()

    def _load_step(self):
        """Load the STEP file using CadQuery."""
        try:
            import cadquery as cq
        except ImportError:
            raise ImportError(
                "CadQuery is required for STEP file analysis. "
                "Install with: pip install cadquery"
            )

        # Import the STEP file
        result = cq.importers.importStep(str(self.step_path))

        # Get the solid(s) from the result
        if hasattr(result, 'val'):
            self._solid = result.val()
        else:
            self._solid = result.objects[0] if result.objects else None

        if self._solid is None:
            raise ValueError(f"Could not extract solid from STEP file: {self.step_path}")

    def _get_volume_mm3(self) -> float:
        """Get volume in cubic millimeters (CAD unit)."""
        try:
            # CadQuery Volume() returns mm³
            return self._solid.Volume()
        except Exception as e:
            raise ValueError(f"Could not calculate volume: {e}")

    def _get_surface_area_mm2(self) -> float:
        """Get surface area in square millimeters (CAD unit)."""
        try:
            # CadQuery Area() returns mm²
            return self._solid.Area()
        except Exception as e:
            raise ValueError(f"Could not calculate surface area: {e}")

    def _get_bounding_box_mm(self) -> Tuple[float, float, float]:
        """Get bounding box dimensions in millimeters."""
        try:
            bb = self._solid.BoundingBox()
            return (bb.xlen, bb.ylen, bb.zlen)
        except Exception as e:
            raise ValueError(f"Could not calculate bounding box: {e}")

    def _calculate_equivalent_cylinder(self, V: float, A: float) -> Dict[str, float]:
        """Calculate equivalent cylinder dimensions.

        For a cylinder: V = π R² L, A = 2πRL + 2πR² (with end caps)

        We solve for R and L that match the given V and A.
        The characteristic length L_c = V/A is preserved.

        For simplicity, we assume L/R = 2 (typical shaft geometry) and solve.

        Args:
            V: Volume in m³
            A: Surface area in m²

        Returns:
            Dictionary with 'radius' and 'length' in meters
        """
        # Assume L = 2R (reasonable for many shaft-like geometries)
        # V = π R² (2R) = 2π R³
        # A = 2πR(2R) + 2πR² = 4πR² + 2πR² = 6πR²

        # From V: R = (V / (2π))^(1/3)
        R_from_V = (V / (2 * math.pi)) ** (1/3)

        # From A: R = sqrt(A / (6π))
        R_from_A = math.sqrt(A / (6 * math.pi))

        # Use geometric mean as compromise
        R = math.sqrt(R_from_V * R_from_A)
        L = V / (math.pi * R * R)  # Calculate L to preserve V exactly

        return {'radius': R, 'length': L}

    def _calculate_equivalent_plate(self, V: float, A: float) -> Dict[str, float]:
        """Calculate equivalent plate dimensions.

        For an infinite plate (1D heat transfer), only thickness matters.
        The characteristic length for a plate is t/2 (half-thickness).

        For a finite plate: V = t × w × L, A ≈ 2 × w × L (ignoring edges)
        So t ≈ 2V/A

        Args:
            V: Volume in m³
            A: Surface area in m²

        Returns:
            Dictionary with 'thickness', 'width', 'length' in meters
        """
        # Characteristic thickness (this is what matters for 1D thermal sim)
        thickness = 2 * V / A

        # Assume square plate for width/length (for display purposes)
        # A ≈ 2 × side²  →  side = sqrt(A/2)
        side = math.sqrt(A / 2)

        return {
            'thickness': thickness,
            'width': side,
            'length': side
        }

    def _determine_best_equivalent(self, bbox: Tuple[float, float, float]) -> str:
        """Determine whether cylinder or plate is better equivalent.

        Based on bounding box aspect ratios:
        - If one dimension is much smaller than others → plate-like
        - If two dimensions are similar and larger → cylinder-like

        Args:
            bbox: Bounding box dimensions (x, y, z)

        Returns:
            'cylinder' or 'plate'
        """
        dims = sorted(bbox)  # smallest to largest

        # Aspect ratio of smallest to largest
        if dims[2] == 0:
            return 'cylinder'  # Avoid division by zero

        aspect = dims[0] / dims[2]

        # If the smallest dimension is much smaller than others, it's plate-like
        if aspect < 0.3:
            return 'plate'

        # Otherwise default to cylinder (more common for heat treatment parts)
        return 'cylinder'

    def analyze(self, preferred_equivalent: str = 'auto') -> CADAnalysisResult:
        """Analyze the STEP file and calculate equivalent geometry.

        Args:
            preferred_equivalent: 'auto', 'cylinder', or 'plate'

        Returns:
            CADAnalysisResult with all analysis data
        """
        # Get raw measurements in mm
        volume_mm3 = self._get_volume_mm3()
        area_mm2 = self._get_surface_area_mm2()
        bbox_mm = self._get_bounding_box_mm()

        # Convert to SI units (meters)
        volume_m3 = volume_mm3 * 1e-9  # mm³ → m³
        area_m2 = area_mm2 * 1e-6      # mm² → m²
        bbox_m = tuple(d * 1e-3 for d in bbox_mm)  # mm → m

        # Calculate characteristic length
        char_length = volume_m3 / area_m2 if area_m2 > 0 else 0

        # Determine equivalent geometry type
        if preferred_equivalent == 'auto':
            equiv_type = self._determine_best_equivalent(bbox_m)
        else:
            equiv_type = preferred_equivalent

        # Calculate equivalent geometry parameters
        if equiv_type == 'cylinder':
            equiv_params = self._calculate_equivalent_cylinder(volume_m3, area_m2)
        else:
            equiv_params = self._calculate_equivalent_plate(volume_m3, area_m2)

        return CADAnalysisResult(
            filename=self.step_path.name,
            volume=volume_m3,
            surface_area=area_m2,
            characteristic_length=char_length,
            bounding_box=bbox_m,
            equivalent_type=equiv_type,
            equivalent_params=equiv_params
        )


def analyze_step_file(path: Path, equiv_type: str = 'auto') -> CADAnalysisResult:
    """Convenience function for analyzing a STEP file.

    Args:
        path: Path to the STEP file
        equiv_type: 'auto', 'cylinder', or 'plate'

    Returns:
        CADAnalysisResult with analysis data
    """
    analyzer = CADGeometryAnalyzer(path)
    return analyzer.analyze(preferred_equivalent=equiv_type)
