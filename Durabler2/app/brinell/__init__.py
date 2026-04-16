"""Brinell Hardness test module - ASTM E10 / ISO 6506."""
from flask import Blueprint

brinell_bp = Blueprint('brinell', __name__)

from . import routes  # noqa: E402, F401
