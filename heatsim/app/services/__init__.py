"""Application services."""
from .property_evaluator import PropertyEvaluator
from .excel_importer import ExcelImporter
from .seed_data import seed_standard_grades, STANDARD_GRADES
from .geometry import Cylinder, Plate, Ring, create_geometry
from .boundary_conditions import BoundaryCondition, InsulatedBoundary, create_quench_bc
from .heat_solver import HeatSolver, SolverConfig, SolverResult
from .phase_tracker import PhaseTracker, PhaseResult
from . import visualization

__all__ = [
    # Phase 2 services
    'PropertyEvaluator',
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
    # Phase 3 services - Solver
    'HeatSolver',
    'SolverConfig',
    'SolverResult',
    # Phase 3 services - Phase transformation
    'PhaseTracker',
    'PhaseResult',
    # Phase 3 services - Visualization
    'visualization',
]
