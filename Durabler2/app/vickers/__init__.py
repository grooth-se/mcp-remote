"""Vickers Hardness test module - ASTM E92 / ISO 6507."""
from flask import Blueprint

vickers_bp = Blueprint('vickers', __name__)

from . import routes  # noqa: E402, F401
