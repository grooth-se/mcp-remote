"""KIC (Fracture Toughness) test module - ASTM E399."""
from flask import Blueprint

kic_bp = Blueprint('kic', __name__)

from . import routes  # noqa: E402, F401
