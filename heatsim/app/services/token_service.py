"""JWT token generation and validation for portal authentication."""
from datetime import datetime, timedelta, timezone
import jwt
from flask import current_app


def generate_token(user_id, expiry_hours=8):
    """Generate a JWT token for a user."""
    payload = {
        'user_id': user_id,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def validate_token(token):
    """Validate a JWT token. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
