"""Tensile testing blueprint (ASTM E8/E8M)."""
from flask import Blueprint

tensile_bp = Blueprint('tensile', __name__)

from . import routes  # noqa: E402, F401
