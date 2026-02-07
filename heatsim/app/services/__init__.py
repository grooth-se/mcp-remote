"""Application services."""
from .property_evaluator import PropertyEvaluator, PropertyPlotter, evaluate_property
from .excel_importer import ExcelImporter
from .seed_data import seed_standard_grades, STANDARD_GRADES
from .geometry import Cylinder, Plate, Ring, create_geometry
from .boundary_conditions import (
    BoundaryCondition, InsulatedBoundary,
    create_quench_bc, create_heating_bc, create_transfer_bc,
    create_tempering_bc, create_cooling_bc
)
from .heat_solver import (
    HeatSolver, MultiPhaseHeatSolver,
    SolverConfig, SolverResult, PhaseConfig, PhaseResult as SolverPhaseResult
)
from .phase_tracker import PhaseTracker, PhaseResult
from . import visualization
from . import comsol

__all__ = [
    # Phase 2 services
    'PropertyEvaluator',
    'PropertyPlotter',
    'evaluate_property',
    'ExcelImporter',
    'seed_standard_grades',
    'STANDARD_GRADES',
    # Phase 3 services - Geometry
    'Cylinder',
    'Plate',
    'Ring',
    'create_geometry',
    # Phase 3 services - Boundary conditions
    'BoundaryCondition',
    'InsulatedBoundary',
    'create_quench_bc',
    'create_heating_bc',
    'create_transfer_bc',
    'create_tempering_bc',
    'create_cooling_bc',
    # Phase 3 services - Solver
    'HeatSolver',
    'MultiPhaseHeatSolver',
    'SolverConfig',
    'SolverResult',
    'PhaseConfig',
    'SolverPhaseResult',
    # Phase 3 services - Phase transformation
    'PhaseTracker',
    'PhaseResult',
    # Phase 3 services - Visualization
    'visualization',
    # Phase 4 services - COMSOL integration
    'comsol',
]
