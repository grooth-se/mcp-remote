"""Admin blueprint."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__)

from . import (
    audit_routes,  # noqa: E402, F401
    material_change_routes,  # noqa: E402, F401
    routes,  # noqa: E402, F401
    settings_routes,  # noqa: E402, F401
)
