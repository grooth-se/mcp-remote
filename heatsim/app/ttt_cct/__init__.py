"""TTT/CCT diagram management and JMAK parameter blueprint."""
from flask import Blueprint

ttt_cct_bp = Blueprint('ttt_cct', __name__, template_folder='../templates/ttt_cct')

from . import routes  # noqa: F401, E402 — register routes on blueprint
