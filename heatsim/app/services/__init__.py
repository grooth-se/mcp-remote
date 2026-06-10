"""Application services."""

# Note: visualization_3d imported lazily where needed (requires PYVISTA_OFF_SCREEN)
from . import comsol, visualization
from .boundary_conditions import (
    BoundaryCondition,
    InsulatedBoundary,
    create_cooling_bc,
    create_heating_bc,
    create_quench_bc,
    create_tempering_bc,
    create_transfer_bc,
)
from .cad_geometry import CADAnalysisResult, CADGeometryAnalyzer, analyze_step_file
from .cct_predictor import CCTCurvePredictor, predict_cct_curves
from .comparison_service import ComparisonMetrics, ComparisonService
from .compliance_report import ComplianceReportGenerator
from .data_export import DataExporter
from .excel_importer import ExcelImporter
from .geometry import Cylinder, HollowCylinder, Plate, Ring, create_geometry
from .hardness_predictor import HardnessPredictor, HardnessResult, predict_hardness_profile
from .haz_predictor import HAZPredictor, HAZResult
from .heat_solver import (
    HeatSolver,
    MultiPhaseHeatSolver,
    PhaseConfig,
    SolverConfig,
    SolverResult,
)
from .heat_solver import (
    PhaseResult as SolverPhaseResult,
)
from .jominy_service import JominyResult, JominySimulator, simulate_jominy_test
from .lineage_service import LineageService
from .material_change_tracker import MaterialChangeTracker
from .optimization_service import OptimizationResult, OptimizationService
from .phase_tracker import PhaseResult, PhaseTracker
from .preheat_calculator import PreheatCalculator, PreheatResult
from .property_evaluator import PropertyEvaluator, PropertyPlotter, evaluate_property
from .report_generator import (
    SimulationPDFReportGenerator,
    SimulationReportGenerator,
    generate_simulation_pdf_report,
    generate_simulation_report,
)
from .rosenthal_solver import RosenthalParams, RosenthalSolver
from .seed_data import (
    STANDARD_COMPOSITIONS,
    STANDARD_GRADES,
    seed_standard_compositions,
    seed_standard_grades,
)
from .sensitivity_analysis import SensitivityAnalysisResult, SensitivityAnalyzer
from .snapshot_diff import SnapshotDiffService
from .snapshot_service import SnapshotService

__all__ = [
    # Phase 2 services
    "PropertyEvaluator",
    "PropertyPlotter",
    "evaluate_property",
    "ExcelImporter",
    "seed_standard_grades",
    "seed_standard_compositions",
    "STANDARD_GRADES",
    "STANDARD_COMPOSITIONS",
    # Phase 3 services - Geometry
    "Cylinder",
    "Plate",
    "Ring",
    "HollowCylinder",
    "create_geometry",
    # Phase 3 services - Boundary conditions
    "BoundaryCondition",
    "InsulatedBoundary",
    "create_quench_bc",
    "create_heating_bc",
    "create_transfer_bc",
    "create_tempering_bc",
    "create_cooling_bc",
    # Phase 3 services - Solver
    "HeatSolver",
    "MultiPhaseHeatSolver",
    "SolverConfig",
    "SolverResult",
    "PhaseConfig",
    "SolverPhaseResult",
    # Phase 3 services - Phase transformation
    "PhaseTracker",
    "PhaseResult",
    # Phase 3 services - CAD geometry
    "CADGeometryAnalyzer",
    "CADAnalysisResult",
    "analyze_step_file",
    # Phase 3 services - Hardness prediction
    "HardnessPredictor",
    "HardnessResult",
    "predict_hardness_profile",
    # Jominy hardenability test
    "JominySimulator",
    "JominyResult",
    "simulate_jominy_test",
    # Phase 3 services - Report generation
    "SimulationReportGenerator",
    "generate_simulation_report",
    "SimulationPDFReportGenerator",
    "generate_simulation_pdf_report",
    # Phase 7 services - Comparison
    "ComparisonService",
    "ComparisonMetrics",
    # Phase 8 services - Data export
    "DataExporter",
    # Phase 10 services - Snapshots, Diff, Change Tracking & Lineage
    "SnapshotService",
    "SnapshotDiffService",
    "MaterialChangeTracker",
    "LineageService",
    "ComplianceReportGenerator",
    # Phase 13 services - Process optimization
    "OptimizationService",
    "OptimizationResult",
    # CCT curve prediction
    "CCTCurvePredictor",
    "predict_cct_curves",
    # Phase 14 services - Welding simulation improvements
    "RosenthalSolver",
    "RosenthalParams",
    "HAZPredictor",
    "HAZResult",
    "PreheatCalculator",
    "PreheatResult",
    # Phase 3 services - Visualization
    "visualization",
    # Phase 4 services - COMSOL integration
    "comsol",
]
