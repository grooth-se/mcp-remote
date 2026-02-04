"""Calculation blueprint."""

from flask import Blueprint

calculation_bp = Blueprint('calculation', __name__)

from . import routes  # noqa: F401, E402
