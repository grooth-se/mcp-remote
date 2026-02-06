"""Welding simulation blueprint.

Provides web interface for multi-pass weld simulation with COMSOL integration.
"""
from flask import Blueprint

welding_bp = Blueprint('welding', __name__)

from . import routes  # noqa: F401, E402
