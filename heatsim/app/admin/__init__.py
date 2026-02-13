"""Admin blueprint."""
from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

from . import routes  # noqa: E402, F401
from . import audit_routes  # noqa: E402, F401
from . import settings_routes  # noqa: E402, F401
from . import material_change_routes  # noqa: E402, F401
