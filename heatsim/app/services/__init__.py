"""Application services."""
from .property_evaluator import PropertyEvaluator, PropertyPlotter, evaluate_property
from .excel_importer import ExcelImporter
from .seed_data import seed_standard_grades, seed_standard_compositions, STANDARD_GRADES, STANDARD_COMPOSITIONS
from .geometry import Cylinder, Plate, Ring, HollowCylinder, create_geometry
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
from .cad_geometry import CADGeometryAnalyzer, CADAnalysisResult, analyze_step_file
from .hardness_predictor import HardnessPredictor, HardnessResult, predict_hardness_profile
from . import visualization
from . import comsol

__all__ = [
    # Phase 2 services
    'PropertyEvaluator',
    'PropertyPlotter',
    'evaluate_property',
    'ExcelImporter',
    'seed_standard_grades',
    'seed_standard_compositions',
    'STANDARD_GRADES',
    'STANDARD_COMPOSITIONS',
    # Phase 3 services - Geometry
    'Cylinder',
    'Plate',
    'Ring',
    'HollowCylinder',
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
    # Phase 3 services - CAD geometry
    'CADGeometryAnalyzer',
    'CADAnalysisResult',
    'analyze_step_file',
    # Phase 3 services - Hardness prediction
    'HardnessPredictor',
    'HardnessResult',
    'predict_hardness_profile',
    # Phase 3 services - Visualization
    'visualization',
    # Phase 4 services - COMSOL integration
    'comsol',
]
