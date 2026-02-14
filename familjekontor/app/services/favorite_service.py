"""Favorites service (Phase 7D)."""

from app.extensions import db
from app.models.favorite import UserFavorite

MAX_FAVORITES = 20

DEFAULT_FAVORITES = [
    {'label': 'Ny verifikation', 'url': '/accounting/new', 'icon': 'bi-plus-circle'},
    {'label': 'Ny leverantörsfaktura', 'url': '/invoices/supplier-invoices/new', 'icon': 'bi-receipt'},
    {'label': 'Ny kundfaktura', 'url': '/invoices/customer-invoices/new', 'icon': 'bi-file-earmark-text'},
    {'label': 'Resultaträkning', 'url': '/reports/profit-and-loss', 'icon': 'bi-bar-chart'},
    {'label': 'Rapportcenter', 'url': '/report-center/', 'icon': 'bi-grid-3x3-gap'},
]


def get_user_favorites(user_id):
    """Return user's favorites ordered by sort_order."""
    return (
        UserFavorite.query
        .filter_by(user_id=user_id)
        .order_by(UserFavorite.sort_order)
        .all()
    )


def add_favorite(user_id, label, url, icon='bi-star-fill'):
    """Add a new favorite. Returns the created UserFavorite."""
    count = UserFavorite.query.filter_by(user_id=user_id).count()
    if count >= MAX_FAVORITES:
        return None
    max_order = db.session.query(
        db.func.coalesce(db.func.max(UserFavorite.sort_order), 0)
    ).filter_by(user_id=user_id).scalar()
    fav = UserFavorite(
        user_id=user_id, label=label, url=url, icon=icon,
        sort_order=max_order + 1,
    )
    db.session.add(fav)
    db.session.commit()
    return fav


def remove_favorite(favorite_id, user_id):
    """Remove a favorite. Returns True if found and removed."""
    fav = UserFavorite.query.filter_by(id=favorite_id, user_id=user_id).first()
    if not fav:
        return False
    db.session.delete(fav)
    db.session.commit()
    return True


def toggle_favorite(user_id, url, label, icon='bi-star-fill'):
    """Toggle a favorite by URL. Returns {action, id}."""
    existing = UserFavorite.query.filter_by(user_id=user_id, url=url).first()
    if existing:
        fav_id = existing.id
        db.session.delete(existing)
        db.session.commit()
        return {'action': 'removed', 'id': fav_id}
    fav = add_favorite(user_id, label, url, icon)
    if fav is None:
        return {'action': 'error', 'id': None}
    return {'action': 'added', 'id': fav.id}


def reorder_favorites(user_id, ordered_ids):
    """Update sort_order based on ordered list of IDs. Returns count updated."""
    count = 0
    for i, fav_id in enumerate(ordered_ids):
        fav = UserFavorite.query.filter_by(id=fav_id, user_id=user_id).first()
        if fav:
            fav.sort_order = i
            count += 1
    db.session.commit()
    return count


def update_favorite(favorite_id, user_id, label=None, icon=None):
    """Update label and/or icon. Returns True if found and updated."""
    fav = UserFavorite.query.filter_by(id=favorite_id, user_id=user_id).first()
    if not fav:
        return False
    if label is not None:
        fav.label = label
    if icon is not None:
        fav.icon = icon
    db.session.commit()
    return True


def seed_default_favorites(user_id):
    """Create default favorites if user has none. Returns count created."""
    existing = UserFavorite.query.filter_by(user_id=user_id).count()
    if existing > 0:
        return 0
    count = 0
    for i, d in enumerate(DEFAULT_FAVORITES):
        fav = UserFavorite(
            user_id=user_id, label=d['label'], url=d['url'],
            icon=d['icon'], sort_order=i,
        )
        db.session.add(fav)
        count += 1
    db.session.commit()
    return count
