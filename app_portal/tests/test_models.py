"""Tests for database models."""
from app.models.user import User
from app.models.application import Application
from app.models.permission import UserPermission


def test_user_password_hashing(app, db):
    user = User(username='hashtest')
    user.set_password('secret123')
    db.session.add(user)
    db.session.commit()

    assert user.check_password('secret123')
    assert not user.check_password('wrongpassword')
    assert user.password_hash != 'secret123'


def test_user_is_active(app, db):
    user = User(username='active_test')
    user.set_password('pass1234')
    db.session.add(user)
    db.session.commit()

    assert user.is_active is True
    user.is_active_user = False
    assert user.is_active is False


def test_user_has_app_permission_admin(admin_user, sample_app):
    """Admin users have access to all apps."""
    assert admin_user.has_app_permission('testapp') is True


def test_user_has_app_permission_granted(db, normal_user, sample_app):
    """Normal user with granted permission."""
    perm = UserPermission(user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm)
    db.session.commit()
    assert normal_user.has_app_permission('testapp') is True


def test_user_has_app_permission_denied(normal_user, sample_app):
    """Normal user without permission."""
    assert normal_user.has_app_permission('testapp') is False


def test_get_permitted_apps_admin(admin_user, sample_apps):
    """Admin sees all active apps."""
    apps = admin_user.get_permitted_apps()
    assert len(apps) == 3


def test_get_permitted_apps_user(db, normal_user, sample_apps):
    """Normal user sees only permitted apps."""
    perm = UserPermission(user_id=normal_user.id, app_id=sample_apps[0].id)
    db.session.add(perm)
    db.session.commit()
    apps = normal_user.get_permitted_apps()
    assert len(apps) == 1
    assert apps[0].app_code == 'accruedincome'


def test_application_repr(sample_app):
    assert 'testapp' in repr(sample_app)


def test_user_permission_unique_constraint(db, normal_user, sample_app):
    """Cannot add duplicate permissions."""
    perm1 = UserPermission(user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm1)
    db.session.commit()

    perm2 = UserPermission(user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm2)
    try:
        db.session.commit()
        assert False, "Should have raised IntegrityError"
    except Exception:
        db.session.rollback()
