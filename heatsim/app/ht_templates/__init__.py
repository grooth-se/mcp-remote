"""Heat treatment templates blueprint."""
from flask import Blueprint

ht_templates_bp = Blueprint('ht_templates', __name__)

from . import routes  # noqa: F401, E402
