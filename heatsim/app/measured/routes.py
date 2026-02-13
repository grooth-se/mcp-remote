"""Measured data routes — browse and manage uploaded TC data."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from . import measured_bp
from app.extensions import db
from app.models import Simulation
from app.models.measured_data import MeasuredData


@measured_bp.route('/')
@login_required
def index():
    """List all measured data for current user."""
    q = request.args.get('q', '').strip()
    step = request.args.get('step', '')
    page = request.args.get('page', 1, type=int)

    query = MeasuredData.query.join(Simulation).filter(
        Simulation.user_id == current_user.id
    )

    if q:
        query = query.filter(
            db.or_(
                MeasuredData.name.ilike(f'%{q}%'),
                Simulation.name.ilike(f'%{q}%'),
                MeasuredData.filename.ilike(f'%{q}%'),
            )
        )
    if step:
        query = query.filter(MeasuredData.process_step == step)

    query = query.order_by(MeasuredData.uploaded_at.desc())
    pagination = query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'measured/index.html',
        datasets=pagination.items,
        pagination=pagination,
        q=q,
        step=step,
    )


@measured_bp.route('/<int:data_id>')
@login_required
def view(data_id):
    """View measured data detail."""
    md = MeasuredData.query.get_or_404(data_id)
    if md.simulation.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('measured.index'))

    return render_template('measured/view.html', md=md)


@measured_bp.route('/<int:data_id>/delete', methods=['POST'])
@login_required
def delete(data_id):
    """Delete measured data."""
    md = MeasuredData.query.get_or_404(data_id)
    if md.simulation.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('measured.index'))

    name = md.name
    db.session.delete(md)
    db.session.commit()
    flash(f'Deleted measured data: {name}', 'success')
    return redirect(url_for('measured.index'))
