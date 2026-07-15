from sqlalchemy import func

from app.extensions import db
from app.models.application import Application
from app.models.log import AccessLog
from app.models.user import User

# Actions offered in the usage filter UI
USAGE_ACTIONS = ('access_app', 'validate', 'denied', 'login', 'logout')
# Actions counted as "activity" in the per-app summary/chart
COUNTED_ACTIONS = ('access_app', 'validate', 'denied')


def _apply_filters(query, app_id=None, user_id=None, action=None,
                   start=None, end=None):
    if app_id:
        query = query.filter(AccessLog.app_id == app_id)
    if user_id:
        query = query.filter(AccessLog.user_id == user_id)
    if action:
        query = query.filter(AccessLog.action == action)
    if start:
        query = query.filter(AccessLog.timestamp >= start)
    if end:
        query = query.filter(AccessLog.timestamp < end)
    return query


def per_app_summary(**filters):
    """One row per app: counts per action, unique users, last-used timestamp.
    Sorted by total activity, busiest first."""
    counts = _apply_filters(
        db.session.query(AccessLog.app_id, AccessLog.action, func.count(AccessLog.id))
        .filter(AccessLog.app_id.isnot(None),
                AccessLog.action.in_(COUNTED_ACTIONS)),
        **filters).group_by(AccessLog.app_id, AccessLog.action).all()

    extras = _apply_filters(
        db.session.query(AccessLog.app_id,
                         func.count(func.distinct(AccessLog.user_id)),
                         func.max(AccessLog.timestamp))
        .filter(AccessLog.app_id.isnot(None),
                AccessLog.action.in_(COUNTED_ACTIONS)),
        **filters).group_by(AccessLog.app_id).all()

    apps = {a.id: a for a in Application.query.all()}
    summary = {}

    def row_for(app_id):
        app = apps.get(app_id)
        return summary.setdefault(app_id, {
            'app_id': app_id,
            'app_name': app.app_name if app else f'(deleted #{app_id})',
            'app_code': app.app_code if app else None,
            'access_app': 0, 'validate': 0, 'denied': 0,
            'unique_users': 0, 'last_used': None,
        })

    for app_id, action, count in counts:
        row_for(app_id)[action] = count
    for app_id, unique_users, last_used in extras:
        row = row_for(app_id)
        row['unique_users'] = unique_users
        row['last_used'] = last_used

    return sorted(summary.values(),
                  key=lambda r: r['access_app'] + r['validate'] + r['denied'],
                  reverse=True)


def per_user_app_counts(page=1, per_page=50, **filters):
    """Paginated per-user-per-app-per-action counts, busiest first."""
    query = _apply_filters(
        db.session.query(User.username, Application.app_name, AccessLog.action,
                         func.count(AccessLog.id).label('count'),
                         func.max(AccessLog.timestamp).label('last_used'))
        .outerjoin(User, AccessLog.user_id == User.id)
        .outerjoin(Application, AccessLog.app_id == Application.id)
        .filter(AccessLog.action.in_(COUNTED_ACTIONS)),
        **filters
    ).group_by(User.username, Application.app_name, AccessLog.action)

    total = query.count()
    pages = max(1, -(-total // per_page))
    rows = (query.order_by(func.count(AccessLog.id).desc())
            .limit(per_page).offset((page - 1) * per_page).all())
    return {
        'items': [{'username': r.username or '-', 'app_name': r.app_name or '-',
                   'action': r.action, 'count': r.count, 'last_used': r.last_used}
                  for r in rows],
        'page': page, 'pages': pages, 'total': total,
    }


def iter_export_rows(max_rows, **filters):
    """Yield the filtered raw log rows for CSV export, newest first,
    capped at max_rows to keep exports bounded."""
    query = _apply_filters(
        db.session.query(AccessLog.timestamp, User.username, AccessLog.action,
                         Application.app_name, AccessLog.ip_address, AccessLog.details)
        .outerjoin(User, AccessLog.user_id == User.id)
        .outerjoin(Application, AccessLog.app_id == Application.id),
        **filters).order_by(AccessLog.timestamp.desc())
    for row in query.limit(max_rows).yield_per(500):
        yield row
