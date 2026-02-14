"""Tests for Favorites & Quick Actions (Phase 7D)."""

import pytest

from app.models.user import User
from app.models.company import Company
from app.models.favorite import UserFavorite
from app.services.favorite_service import (
    get_user_favorites, add_favorite, remove_favorite,
    toggle_favorite, reorder_favorites, update_favorite,
    seed_default_favorites, MAX_FAVORITES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fav_user(db):
    """User for favorite tests."""
    user = User.query.filter_by(username='admin').first()
    if not user:
        user = User(username='fav_admin', email='fav@test.com', role='admin')
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
    return user


@pytest.fixture
def fav_company(db):
    """Company for dashboard test."""
    co = Company(name='Fav AB', org_number='556900-0099', company_type='AB')
    db.session.add(co)
    db.session.commit()
    return co


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestFavoriteModel:
    def test_creation(self, app, db, fav_user):
        with app.app_context():
            fav = UserFavorite(
                user_id=fav_user.id, label='Test', url='/test', icon='bi-star',
            )
            db.session.add(fav)
            db.session.commit()
            assert fav.id is not None
            assert repr(fav) == '<UserFavorite Test>'


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestFavoriteService:
    def test_get_ordered(self, app, db, fav_user):
        with app.app_context():
            for i, label in enumerate(['C', 'A', 'B']):
                db.session.add(UserFavorite(
                    user_id=fav_user.id, label=label, url=f'/{label}',
                    sort_order=i,
                ))
            db.session.commit()
            favs = get_user_favorites(fav_user.id)
            assert [f.label for f in favs] == ['C', 'A', 'B']

    def test_add_favorite(self, app, db, fav_user):
        with app.app_context():
            fav = add_favorite(fav_user.id, 'Added', '/added', 'bi-plus')
            assert fav is not None
            assert fav.label == 'Added'
            assert fav.sort_order == 1  # first one

    def test_remove_favorite(self, app, db, fav_user):
        with app.app_context():
            fav = add_favorite(fav_user.id, 'ToRemove', '/remove')
            assert remove_favorite(fav.id, fav_user.id) is True
            assert UserFavorite.query.get(fav.id) is None

    def test_remove_wrong_user(self, app, db, fav_user):
        with app.app_context():
            fav = add_favorite(fav_user.id, 'Mine', '/mine')
            assert remove_favorite(fav.id, fav_user.id + 999) is False

    def test_toggle_add(self, app, db, fav_user):
        with app.app_context():
            result = toggle_favorite(fav_user.id, '/toggle', 'Toggled')
            assert result['action'] == 'added'
            assert result['id'] is not None

    def test_toggle_remove(self, app, db, fav_user):
        with app.app_context():
            toggle_favorite(fav_user.id, '/toggle2', 'Toggled2')
            result = toggle_favorite(fav_user.id, '/toggle2', 'Toggled2')
            assert result['action'] == 'removed'

    def test_reorder(self, app, db, fav_user):
        with app.app_context():
            f1 = add_favorite(fav_user.id, 'First', '/first')
            f2 = add_favorite(fav_user.id, 'Second', '/second')
            f3 = add_favorite(fav_user.id, 'Third', '/third')
            # Reverse order
            count = reorder_favorites(fav_user.id, [f3.id, f2.id, f1.id])
            assert count == 3
            favs = get_user_favorites(fav_user.id)
            assert favs[0].label == 'Third'
            assert favs[2].label == 'First'

    def test_update_label(self, app, db, fav_user):
        with app.app_context():
            fav = add_favorite(fav_user.id, 'OldLabel', '/old')
            assert update_favorite(fav.id, fav_user.id, label='NewLabel') is True
            db.session.refresh(fav)
            assert fav.label == 'NewLabel'

    def test_update_icon(self, app, db, fav_user):
        with app.app_context():
            fav = add_favorite(fav_user.id, 'IconTest', '/icon')
            assert update_favorite(fav.id, fav_user.id, icon='bi-heart') is True
            db.session.refresh(fav)
            assert fav.icon == 'bi-heart'

    def test_seed_defaults(self, app, db, fav_user):
        with app.app_context():
            count = seed_default_favorites(fav_user.id)
            assert count == 5
            favs = get_user_favorites(fav_user.id)
            assert len(favs) == 5
            assert favs[0].label == 'Ny verifikation'

    def test_seed_no_duplicate(self, app, db, fav_user):
        with app.app_context():
            seed_default_favorites(fav_user.id)
            count2 = seed_default_favorites(fav_user.id)
            assert count2 == 0  # already has favorites

    def test_max_limit(self, app, db, fav_user):
        with app.app_context():
            for i in range(MAX_FAVORITES):
                add_favorite(fav_user.id, f'Fav {i}', f'/fav{i}')
            result = add_favorite(fav_user.id, 'Too many', '/toomany')
            assert result is None


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestFavoriteRoutes:
    def test_require_login(self, client):
        resp = client.get('/favorites/')
        assert resp.status_code == 302

    def test_favorites_page(self, logged_in_client):
        resp = logged_in_client.get('/favorites/')
        assert resp.status_code == 200
        assert 'Favoriter' in resp.data.decode()

    def test_toggle_route(self, logged_in_client):
        resp = logged_in_client.post('/favorites/toggle',
                                      json={'url': '/test', 'label': 'TestFav'},
                                      content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['action'] == 'added'

    def test_reorder_route(self, logged_in_client, db, admin_user):
        with logged_in_client.application.app_context():
            f1 = add_favorite(admin_user.id, 'R1', '/r1')
            f2 = add_favorite(admin_user.id, 'R2', '/r2')
            f1_id, f2_id = f1.id, f2.id
        resp = logged_in_client.post('/favorites/reorder',
                                      json={'ids': [f2_id, f1_id]},
                                      content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['updated'] == 2

    def test_update_route(self, logged_in_client, db, admin_user):
        with logged_in_client.application.app_context():
            fav = add_favorite(admin_user.id, 'Old', '/upd')
            fav_id = fav.id
        resp = logged_in_client.post(f'/favorites/{fav_id}/update',
                                      json={'label': 'New'},
                                      content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_delete_route(self, logged_in_client, db, admin_user):
        with logged_in_client.application.app_context():
            fav = add_favorite(admin_user.id, 'ToDelete', '/del')
            fav_id = fav.id
        resp = logged_in_client.post(f'/favorites/{fav_id}/delete',
                                      follow_redirects=True)
        assert resp.status_code == 200
        assert 'borttagen' in resp.data.decode()

    def test_reset_route(self, logged_in_client):
        resp = logged_in_client.post('/favorites/reset', follow_redirects=True)
        assert resp.status_code == 200
        assert 'standard' in resp.data.decode().lower()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestFavoriteIntegration:
    def test_dashboard_shows_favorites(self, logged_in_client, db, fav_company, admin_user):
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = fav_company.id
        resp = logged_in_client.get('/')
        html = resp.data.decode()
        assert 'dashboard-favorites' in html
        assert 'Snabbåtgärder' in html

    def test_dashboard_seeds_defaults(self, logged_in_client, db, fav_company, admin_user):
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = fav_company.id
        resp = logged_in_client.get('/')
        html = resp.data.decode()
        assert 'Ny verifikation' in html

    def test_dashboard_gear_icon(self, logged_in_client, db, fav_company, admin_user):
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = fav_company.id
        resp = logged_in_client.get('/')
        html = resp.data.decode()
        assert 'bi-gear-fill' in html
