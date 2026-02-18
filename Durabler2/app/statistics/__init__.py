"""Statistics module for test data analysis."""
from flask import Blueprint

statistics_bp = Blueprint('statistics', __name__)

from . import routes  # noqa: E402, F401
