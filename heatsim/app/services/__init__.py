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
from .jominy_service import JominySimulator, JominyResult, simulate_jominy_test
from .comparison_service import ComparisonService, ComparisonMetrics
from .sensitivity_analysis import SensitivityAnalyzer, SensitivityAnalysisResult
from .optimization_service import OptimizationService, OptimizationResult
from .report_generator import (
    SimulationReportGenerator, generate_simulation_report,
    SimulationPDFReportGenerator, generate_simulation_pdf_report
)
from .data_export import DataExporter
from .snapshot_service import SnapshotService
from .snapshot_diff import SnapshotDiffService
from .material_change_tracker import MaterialChangeTracker
from .lineage_service import LineageService
from .compliance_report import ComplianceReportGenerator
from .cct_predictor import CCTCurvePredictor, predict_cct_curves
from .rosenthal_solver import RosenthalSolver, RosenthalParams
from .haz_predictor import HAZPredictor, HAZResult
from .preheat_calculator import PreheatCalculator, PreheatResult
from . import visualization
# Note: visualization_3d imported lazily where needed (requires PYVISTA_OFF_SCREEN)
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
    # Jominy hardenability test
    'JominySimulator',
    'JominyResult',
    'simulate_jominy_test',
    # Phase 3 services - Report generation
    'SimulationReportGenerator',
    'generate_simulation_report',
    'SimulationPDFReportGenerator',
    'generate_simulation_pdf_report',
    # Phase 7 services - Comparison
    'ComparisonService',
    'ComparisonMetrics',
    # Phase 8 services - Data export
    'DataExporter',
    # Phase 10 services - Snapshots, Diff, Change Tracking & Lineage
    'SnapshotService',
    'SnapshotDiffService',
    'MaterialChangeTracker',
    'LineageService',
    'ComplianceReportGenerator',
    # Phase 13 services - Process optimization
    'OptimizationService',
    'OptimizationResult',
    # CCT curve prediction
    'CCTCurvePredictor',
    'predict_cct_curves',
    # Phase 14 services - Welding simulation improvements
    'RosenthalSolver',
    'RosenthalParams',
    'HAZPredictor',
    'HAZResult',
    'PreheatCalculator',
    'PreheatResult',
    # Phase 3 services - Visualization
    'visualization',
    # Phase 4 services - COMSOL integration
    'comsol',
]
