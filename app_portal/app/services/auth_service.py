from datetime import datetime, timedelta, timezone
from flask import current_app
from app.extensions import db
from app.models.user import User
from app.models.session import UserSession
from app.services.token_service import generate_token


def authenticate(username, password):
    """Validate username/password. Returns User or None."""
    user = User.query.filter_by(username=username).first()
    if user and user.is_active and user.check_password(password):
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        return user
    return None


def create_session(user, ip_address=None, user_agent=None, remember=False):
    """Create a new session for the user. Returns the session token."""
    if remember:
        hours = current_app.config.get('REMEMBER_ME_DAYS', 7) * 24
    else:
        hours = current_app.config.get('SESSION_LIFETIME_HOURS', 8)

    token = generate_token(user.id, hours)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    session = UserSession(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent[:256] if user_agent else None,
    )
    db.session.add(session)
    db.session.commit()
    return token


def validate_session(token):
    """Validate a session token. Returns User or None."""
    session = UserSession.query.filter_by(token=token, is_active=True).first()
    if not session:
        return None
    if session.is_expired:
        session.is_active = False
        db.session.commit()
        return None
    return session.user


def logout_session(token):
    """Invalidate a session."""
    session = UserSession.query.filter_by(token=token).first()
    if session:
        session.is_active = False
        db.session.commit()


def change_password(user, old_password, new_password):
    """Change user password. Returns (success, error_message)."""
    if not user.check_password(old_password):
        return False, 'Current password is incorrect.'
    if len(new_password) < current_app.config.get('MIN_PASSWORD_LENGTH', 8):
        return False, f'Password must be at least {current_app.config["MIN_PASSWORD_LENGTH"]} characters.'
    user.set_password(new_password)
    # Invalidate all existing sessions
    UserSession.query.filter_by(user_id=user.id, is_active=True).update({'is_active': False})
    db.session.commit()
    return True, None


def revoke_user_sessions(user_id):
    """Revoke all active sessions for a user."""
    UserSession.query.filter_by(user_id=user_id, is_active=True).update({'is_active': False})
    db.session.commit()
