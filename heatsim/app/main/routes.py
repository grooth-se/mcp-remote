"""Main routes (dashboard)."""
from flask import render_template
from flask_login import login_required

from . import main_bp


@main_bp.route('/')
@login_required
def dashboard():
    """Main dashboard.

    Shows overview of simulation platform features.
    """
    return render_template('main/dashboard.html')
