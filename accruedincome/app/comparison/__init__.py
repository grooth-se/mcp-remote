"""Comparison blueprint."""

from flask import Blueprint

comparison_bp = Blueprint('comparison', __name__)

from . import routes  # noqa: F401, E402
