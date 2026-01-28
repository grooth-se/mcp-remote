"""CTOD (Crack Tip Opening Displacement) test module - ASTM E1290."""

from flask import Blueprint

ctod_bp = Blueprint('ctod', __name__)

from . import routes
