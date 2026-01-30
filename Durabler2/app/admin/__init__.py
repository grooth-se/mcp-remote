"""Admin blueprint for user management and system configuration."""
from flask import Blueprint

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')

from . import routes  # noqa: E402, F401
