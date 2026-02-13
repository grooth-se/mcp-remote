"""Admin routes for material change log."""
from flask import render_template, request

from . import admin_bp
from app.models import MaterialChangeLog, SteelGrade, User, admin_required


ENTITY_TYPE_LABELS = {
    'steel_grade': 'Steel Grade',
    'material_property': 'Material Property',
    'phase_diagram': 'Phase Diagram',
    'composition': 'Composition',
    'phase_property': 'Phase Property',
}


@admin_bp.route('/material-changes')
@admin_required
def material_changes():
    """Browse material change log with filters."""
    page = request.args.get('page', 1, type=int)
    entity_type_filter = request.args.get('entity_type', '')
    grade_filter = request.args.get('grade', '', type=str)
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = MaterialChangeLog.query

    if entity_type_filter:
        query = query.filter(MaterialChangeLog.entity_type == entity_type_filter)
    if grade_filter:
        query = query.filter(MaterialChangeLog.steel_grade_id == int(grade_filter))
    if action_filter:
        query = query.filter(MaterialChangeLog.action == action_filter)
    if user_filter:
        query = query.filter(MaterialChangeLog.changed_by_username.ilike(f'%{user_filter}%'))
    if date_from:
        query = query.filter(MaterialChangeLog.changed_at >= date_from)
    if date_to:
        query = query.filter(MaterialChangeLog.changed_at <= date_to + ' 23:59:59')

    query = query.order_by(MaterialChangeLog.changed_at.desc())
    pagination = query.paginate(page=page, per_page=50, error_out=False)

    # Get steel grades for filter dropdown
    grades = SteelGrade.query.order_by(SteelGrade.designation).all()
    usernames = [u.username for u in User.query.order_by(User.username).all()]

    # Build grade lookup for display
    grade_map = {g.id: g.designation for g in grades}

    return render_template(
        'admin/material_changes.html',
        entries=pagination.items,
        pagination=pagination,
        entity_type_filter=entity_type_filter,
        grade_filter=grade_filter,
        action_filter=action_filter,
        user_filter=user_filter,
        date_from=date_from,
        date_to=date_to,
        entity_type_labels=ENTITY_TYPE_LABELS,
        grades=grades,
        grade_map=grade_map,
        usernames=usernames,
    )
