"""Favorites routes (Phase 7D)."""

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify,
)
from flask_login import login_required, current_user

from app.services.favorite_service import (
    get_user_favorites, add_favorite, remove_favorite,
    toggle_favorite, reorder_favorites, update_favorite,
    seed_default_favorites,
)

favorites_bp = Blueprint('favorites', __name__)


@favorites_bp.route('/')
@login_required
def index():
    favorites = get_user_favorites(current_user.id)
    return render_template('favorites/index.html', favorites=favorites)


@favorites_bp.route('/toggle', methods=['POST'])
@login_required
def toggle():
    data = request.get_json(silent=True)
    if not data or not data.get('url') or not data.get('label'):
        return jsonify({'error': 'url och label krävs'}), 400
    result = toggle_favorite(
        current_user.id,
        data['url'],
        data['label'],
        data.get('icon', 'bi-star-fill'),
    )
    return jsonify(result)


@favorites_bp.route('/reorder', methods=['POST'])
@login_required
def reorder():
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get('ids'), list):
        return jsonify({'error': 'ids krävs'}), 400
    count = reorder_favorites(current_user.id, data['ids'])
    return jsonify({'updated': count})


@favorites_bp.route('/<int:favorite_id>/update', methods=['POST'])
@login_required
def update(favorite_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'data krävs'}), 400
    ok = update_favorite(
        favorite_id, current_user.id,
        label=data.get('label'), icon=data.get('icon'),
    )
    if not ok:
        return jsonify({'error': 'Hittades inte'}), 404
    return jsonify({'ok': True})


@favorites_bp.route('/<int:favorite_id>/delete', methods=['POST'])
@login_required
def delete(favorite_id):
    ok = remove_favorite(favorite_id, current_user.id)
    if request.is_json:
        return jsonify({'ok': ok})
    if ok:
        flash('Favorit borttagen.', 'success')
    return redirect(url_for('favorites.index'))


@favorites_bp.route('/reset', methods=['POST'])
@login_required
def reset():
    """Delete all favorites and re-seed defaults."""
    from app.models.favorite import UserFavorite
    from app.extensions import db
    UserFavorite.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    seed_default_favorites(current_user.id)
    flash('Favoriter återställda till standard.', 'success')
    return redirect(url_for('favorites.index'))
