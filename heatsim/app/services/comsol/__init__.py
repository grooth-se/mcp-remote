"""COMSOL integration services for welding and heat treatment simulation.

This package provides:
- COMSOLClient: Interface to local COMSOL installation via mph library
- WeldModelBuilder: Builds and updates COMSOL models for weld simulation
- SequentialSolver: Runs string-by-string simulation sequence
- ResultsExtractor: Extracts data from COMSOL for visualization
- WeldVisualization: Generates plots and animations from results
- HeatTreatmentModelBuilder: Builds COMSOL models for heat treatment
- HeatTreatmentSolver / MockHeatTreatmentSolver: Runs multi-phase HT simulation
- HeatTreatmentResultsExtractor: Maps HT solver output to SimulationResult records
"""
from .client import COMSOLClient, COMSOLError, COMSOLNotAvailableError, MockCOMSOLClient
from .model_builder import WeldModelBuilder
from .sequential_solver import SequentialSolver
from .results_extractor import ResultsExtractor
from .visualization import WeldVisualization
from .ht_model_builder import HeatTreatmentModelBuilder
from .ht_solver import HeatTreatmentSolver, MockHeatTreatmentSolver
from .ht_results_extractor import HeatTreatmentResultsExtractor

__all__ = [
    'COMSOLClient',
    'MockCOMSOLClient',
    'COMSOLError',
    'COMSOLNotAvailableError',
    'WeldModelBuilder',
    'SequentialSolver',
    'ResultsExtractor',
    'WeldVisualization',
    'HeatTreatmentModelBuilder',
    'HeatTreatmentSolver',
    'MockHeatTreatmentSolver',
    'HeatTreatmentResultsExtractor',
]
