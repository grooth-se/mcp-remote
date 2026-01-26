"""
Test Data Models.

Dataclasses for test data storage and retrieval.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import numpy as np


@dataclass
class TestRecord:
    """Main test record with all test information fields."""

    certificate_number: str
    test_type: str  # 'TENSILE', 'FCGR', 'KIC', 'CTOD', 'SONIC', 'VICKERS'

    # Optional fields
    id: Optional[int] = None
    test_standard: Optional[str] = None
    test_project: Optional[str] = None
    project_name: Optional[str] = None
    customer: Optional[str] = None
    customer_order: Optional[str] = None
    product_sn: Optional[str] = None
    specimen_id: Optional[str] = None
    location_orientation: Optional[str] = None
    material: Optional[str] = None
    test_date: Optional[str] = None
    temperature: Optional[str] = None
    operator: Optional[str] = None
    test_equipment: Optional[str] = None
    comments: Optional[str] = None

    # Status
    status: str = 'DRAFT'
    is_valid: bool = True
    validity_notes: List[str] = field(default_factory=list)

    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Link to certificate register
    certificate_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestRecord':
        """Create from dictionary."""
        # Filter out unknown keys
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class SpecimenGeometry:
    """Specimen geometry for all test types."""

    test_id: int
    specimen_type: Optional[str] = None

    # Common dimensions (mm)
    W: Optional[float] = None  # Width (fracture specimens)
    B: Optional[float] = None  # Thickness
    B_n: Optional[float] = None  # Net thickness (side-grooved)
    a_0: Optional[float] = None  # Initial crack length
    S: Optional[float] = None  # Span (SE(B))

    # Tensile specific
    diameter: Optional[float] = None
    diameter_std: Optional[float] = None
    width: Optional[float] = None
    width_std: Optional[float] = None
    thickness: Optional[float] = None
    thickness_std: Optional[float] = None
    gauge_length: Optional[float] = None
    parallel_length: Optional[float] = None
    final_diameter: Optional[float] = None
    final_gauge_length: Optional[float] = None
    cross_section_area: Optional[float] = None

    # Sonic specific
    length: Optional[float] = None
    mass: Optional[float] = None
    side_length: Optional[float] = None

    # Computed values
    a_W_ratio: Optional[float] = None
    ligament: Optional[float] = None

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpecimenGeometry':
        """Create from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class MaterialProperties:
    """Material properties for calculations."""

    test_id: int
    yield_strength: Optional[float] = None  # MPa
    ultimate_strength: Optional[float] = None  # MPa
    youngs_modulus: Optional[float] = None  # GPa
    poissons_ratio: float = 0.3

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MaterialProperties':
        """Create from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class RawTestData:
    """Raw test data arrays."""

    test_id: int
    data_type: str = 'main'  # 'main', 'precrack', 'crack_check', 'velocities'

    # Common arrays
    time: Optional[np.ndarray] = None
    force: Optional[np.ndarray] = None
    displacement: Optional[np.ndarray] = None
    extension: Optional[np.ndarray] = None
    cycles: Optional[np.ndarray] = None

    # Sonic velocities
    longitudinal_velocities: Optional[List[float]] = None
    shear_velocities: Optional[List[float]] = None

    # Vickers readings
    hardness_readings: Optional[List[Dict[str, Any]]] = None
    load_level: Optional[str] = None

    # Metadata
    source_file: Optional[str] = None
    num_points: Optional[int] = None

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (arrays as lists for JSON)."""
        data = {
            'test_id': self.test_id,
            'data_type': self.data_type,
            'source_file': self.source_file,
            'num_points': self.num_points,
            'longitudinal_velocities': self.longitudinal_velocities,
            'shear_velocities': self.shear_velocities,
            'hardness_readings': self.hardness_readings,
            'load_level': self.load_level,
        }

        # Arrays need special handling
        if self.time is not None:
            data['time'] = self.time
        if self.force is not None:
            data['force'] = self.force
        if self.displacement is not None:
            data['displacement'] = self.displacement
        if self.extension is not None:
            data['extension'] = self.extension
        if self.cycles is not None:
            data['cycles'] = self.cycles

        return data


@dataclass
class TestResult:
    """Single test result with uncertainty."""

    test_id: int
    parameter_name: str
    value: float
    uncertainty: Optional[float] = None
    unit: Optional[str] = None
    coverage_factor: float = 2.0
    extra_data: Optional[Dict[str, Any]] = None
    is_valid: bool = True

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestResult':
        """Create from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    @property
    def formatted_value(self) -> str:
        """Get formatted value with uncertainty."""
        if self.value is None:
            return '-'
        if self.uncertainty:
            return f"{self.value:.4g} ± {self.uncertainty:.2g}"
        return f"{self.value:.4g}"


@dataclass
class CrackMeasurement:
    """Crack length measurements for fracture tests."""

    test_id: int
    measurement_type: str  # 'precrack', 'final', 'compliance'
    measurements: List[float]
    average_value: Optional[float] = None

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CrackMeasurement':
        """Create from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class TestBlob:
    """Binary data storage for plots and photos."""

    test_id: int
    blob_type: str  # 'plot', 'photo', 'report'
    data: bytes
    description: Optional[str] = None
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    created_at: Optional[str] = None

    id: Optional[int] = None


@dataclass
class FCGRDataPoint:
    """Single FCGR per-cycle data point."""

    test_id: int
    cycle_count: int
    crack_length: float  # mm
    delta_K: float  # MPa√m
    da_dN: float  # mm/cycle
    P_max: Optional[float] = None  # kN
    P_min: Optional[float] = None  # kN
    compliance: Optional[float] = None  # mm/kN
    is_valid: bool = True
    is_outlier: bool = False

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FCGRDataPoint':
        """Create from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class ParisLawResult:
    """Paris law regression result."""

    test_id: int
    fit_type: str  # 'initial', 'final', 'region_1', 'region_2'
    C: float  # Paris law coefficient
    m: float  # Paris law exponent
    r_squared: Optional[float] = None
    n_points: Optional[int] = None
    delta_K_min: Optional[float] = None
    delta_K_max: Optional[float] = None
    da_dN_min: Optional[float] = None
    da_dN_max: Optional[float] = None
    std_error_C: Optional[float] = None
    std_error_m: Optional[float] = None

    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParisLawResult':
        """Create from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    @property
    def equation(self) -> str:
        """Get Paris law equation string."""
        return f"da/dN = {self.C:.2e} × ΔK^{self.m:.2f}"


@dataclass
class CompleteTestData:
    """
    Complete test data container for save/load operations.

    Combines all related data for a single test.
    """

    record: TestRecord
    geometry: Optional[SpecimenGeometry] = None
    material: Optional[MaterialProperties] = None
    raw_data: Optional[List[RawTestData]] = None
    results: Optional[List[TestResult]] = None
    crack_measurements: Optional[List[CrackMeasurement]] = None
    blobs: Optional[List[TestBlob]] = None

    # FCGR specific
    fcgr_data_points: Optional[List[FCGRDataPoint]] = None
    paris_law_results: Optional[List[ParisLawResult]] = None

    @property
    def certificate_number(self) -> str:
        """Get certificate number."""
        return self.record.certificate_number

    @property
    def test_type(self) -> str:
        """Get test type."""
        return self.record.test_type

    def get_result(self, parameter_name: str) -> Optional[TestResult]:
        """Get a specific result by parameter name."""
        if self.results:
            for result in self.results:
                if result.parameter_name == parameter_name:
                    return result
        return None

    def get_result_value(self, parameter_name: str) -> Optional[float]:
        """Get result value by parameter name."""
        result = self.get_result(parameter_name)
        return result.value if result else None

    def get_plot_data(self) -> Optional[bytes]:
        """Get main plot binary data."""
        if self.blobs:
            for blob in self.blobs:
                if blob.blob_type == 'plot':
                    return blob.data
        return None

    def get_photos(self) -> List[TestBlob]:
        """Get all photo blobs."""
        if self.blobs:
            return [b for b in self.blobs if b.blob_type == 'photo']
        return []
