"""Upload blueprint."""

from flask import Blueprint

upload_bp = Blueprint('upload', __name__)

from . import routes  # noqa: F401, E402
