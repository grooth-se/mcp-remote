"""Authentication blueprint."""

from flask import Blueprint

auth_bp = Blueprint("auth", __name__)

from . import (
    profile_routes,  # noqa: E402, F401
    routes,  # noqa: E402, F401
)
