"""Charpy Impact test module - ASTM E23 / ISO 148-1."""
from flask import Blueprint

charpy_bp = Blueprint('charpy', __name__)

from . import routes  # noqa: E402, F401
