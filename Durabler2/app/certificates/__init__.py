"""Certificate register blueprint."""
from flask import Blueprint

certificates_bp = Blueprint('certificates', __name__)

from . import routes  # noqa: E402, F401
