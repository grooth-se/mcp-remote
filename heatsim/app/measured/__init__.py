"""Measured data blueprint."""
from flask import Blueprint

measured_bp = Blueprint('measured', __name__)

from . import routes  # noqa: F401, E402
