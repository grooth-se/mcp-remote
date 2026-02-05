"""Materials management blueprint."""
from flask import Blueprint

materials_bp = Blueprint('materials', __name__)

from . import routes  # noqa: F401, E402
