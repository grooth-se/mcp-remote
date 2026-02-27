"""Phase transformation kinetics package.

Provides JMAK-based isothermal and continuous cooling transformation
models, Scheil additivity for CCT from TTT, and critical temperature
calculations from steel composition.

Public API:
    JMAKModel           - JMAK kinetics for isothermal transformations
    KoistinenMarburgerModel - Martensite transformation (athermal)
    PhasePredictor      - Orchestrator with three-tier fallback
    calculate_critical_temperatures - Ae1/Ae3/Bs/Ms/Mf from composition
"""
from .jmak_model import JMAKModel
from .martensite_model import KoistinenMarburgerModel
from .critical_temperatures import calculate_critical_temperatures
from .phase_predictor import PhasePredictor

__all__ = [
    'JMAKModel',
    'KoistinenMarburgerModel',
    'calculate_critical_temperatures',
    'PhasePredictor',
]
