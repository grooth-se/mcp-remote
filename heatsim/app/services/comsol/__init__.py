"""COMSOL integration services for multi-pass welding simulation.

This package provides:
- COMSOLClient: Interface to local COMSOL installation via mph library
- WeldModelBuilder: Builds and updates COMSOL models for weld simulation
- SequentialSolver: Runs string-by-string simulation sequence
- ResultsExtractor: Extracts data from COMSOL for visualization
- WeldVisualization: Generates plots and animations from results
"""
from .client import COMSOLClient, COMSOLError, COMSOLNotAvailableError
from .model_builder import WeldModelBuilder
from .sequential_solver import SequentialSolver
from .results_extractor import ResultsExtractor
from .visualization import WeldVisualization

__all__ = [
    'COMSOLClient',
    'COMSOLError',
    'COMSOLNotAvailableError',
    'WeldModelBuilder',
    'SequentialSolver',
    'ResultsExtractor',
    'WeldVisualization',
]
