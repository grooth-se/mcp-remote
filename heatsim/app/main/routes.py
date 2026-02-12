"""Main routes (dashboard)."""
from datetime import datetime, timedelta
from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from . import main_bp
from app.extensions import db
from app.models import SteelGrade, Simulation
from app.models.simulation import STATUS_COMPLETED, STATUS_RUNNING, STATUS_FAILED, STATUS_READY


@main_bp.route('/')
@login_required
def dashboard():
    """Main dashboard.

    Shows overview of simulation platform features with statistics.
    """
    # Get user's simulations
    user_sims = Simulation.query.filter_by(user_id=current_user.id)

    # Statistics
    stats = {
        'total_simulations': user_sims.count(),
        'completed': user_sims.filter_by(status=STATUS_COMPLETED).count(),
        'running': user_sims.filter_by(status=STATUS_RUNNING).count(),
        'failed': user_sims.filter_by(status=STATUS_FAILED).count(),
        'ready': user_sims.filter_by(status=STATUS_READY).count(),
        'total_materials': SteelGrade.query.count(),
        'materials_with_composition': SteelGrade.query.filter(
            SteelGrade.composition != None
        ).count(),
    }

    # Recent simulations (last 10)
    recent_simulations = user_sims.order_by(
        Simulation.updated_at.desc()
    ).limit(10).all()

    # Simulations this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    stats['this_week'] = user_sims.filter(
        Simulation.created_at >= week_ago
    ).count()

    # Most used steel grades (top 5)
    top_grades = db.session.query(
        SteelGrade.designation,
        func.count(Simulation.id).label('count')
    ).join(Simulation).filter(
        Simulation.user_id == current_user.id
    ).group_by(SteelGrade.id).order_by(
        func.count(Simulation.id).desc()
    ).limit(5).all()

    return render_template(
        'main/dashboard.html',
        stats=stats,
        recent_simulations=recent_simulations,
        top_grades=top_grades
    )
