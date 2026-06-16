"""Metallographic Examination module - ASTM E45/E381, ISO 4967/4969.

Micro (inclusion content) and macro (macroetch) evaluation of polished
and etched surfaces.
"""
from flask import Blueprint

metallography_bp = Blueprint('metallography', __name__)

from . import routes  # noqa: E402, F401
