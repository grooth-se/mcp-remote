"""FCGR (Fatigue Crack Growth Rate) test module - ASTM E647."""

from flask import Blueprint

fcgr_bp = Blueprint('fcgr', __name__)

from . import routes
