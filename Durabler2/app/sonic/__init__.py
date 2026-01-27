"""Sonic Resonance (E1875) test module blueprint."""
from flask import Blueprint

sonic_bp = Blueprint('sonic', __name__)

from . import routes  # noqa: E402, F401
