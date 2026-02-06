"""Simulation blueprint for heat treatment simulations."""
from flask import Blueprint

simulation_bp = Blueprint('simulation', __name__)

from . import routes  # noqa: F401, E402
