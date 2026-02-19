from flask import Blueprint

review_bp = Blueprint('review', __name__, template_folder='../templates/review')

from app.review import routes  # noqa: F401, E402
