"""Main routes (dashboard)."""
from datetime import datetime, timedelta
from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from . import main_bp
from app.extensions import db
from app.models import SteelGrade, Simulation, MeasuredData
from app.models.simulation import (
    SimulationResult,
    STATUS_COMPLETED, STATUS_RUNNING, STATUS_FAILED, STATUS_READY,
)


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
        Simulation.created_at.desc()
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

    # Simulations with measured data
    sims_with_measured = db.session.query(
        func.count(func.distinct(MeasuredData.simulation_id))
    ).filter(
        MeasuredData.simulation_id.in_(
            db.session.query(Simulation.id).filter_by(user_id=current_user.id)
        )
    ).scalar() or 0
    stats['with_measured_data'] = sims_with_measured

    # Weekly simulation trend (last 8 weeks)
    weekly_counts = []
    for i in range(7, -1, -1):
        week_start = datetime.utcnow() - timedelta(weeks=i + 1)
        week_end = datetime.utcnow() - timedelta(weeks=i)
        count = user_sims.filter(
            Simulation.created_at >= week_start,
            Simulation.created_at < week_end
        ).count()
        weekly_counts.append({
            'week': week_end.strftime('%m/%d'),
            'count': count
        })

    # t8/5 range insights
    t85_values = db.session.query(SimulationResult.t_800_500).join(Simulation).filter(
        Simulation.user_id == current_user.id,
        Simulation.status == STATUS_COMPLETED,
        SimulationResult.result_type == 'full_cycle',
        SimulationResult.t_800_500 != None
    ).all()
    t85_list = [v[0] for v in t85_values if v[0] and v[0] > 0]

    param_insights = {}
    if t85_list:
        param_insights['t85_min'] = round(min(t85_list), 1)
        param_insights['t85_max'] = round(max(t85_list), 1)
        param_insights['t85_avg'] = round(sum(t85_list) / len(t85_list), 1)

    return render_template(
        'main/dashboard.html',
        stats=stats,
        recent_simulations=recent_simulations,
        top_grades=top_grades,
        weekly_counts=weekly_counts,
        param_insights=param_insights,
    )
