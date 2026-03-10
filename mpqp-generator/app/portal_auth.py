"""Portal authentication middleware.

Validates JWT tokens from the app portal and syncs user identity.
Pattern matches other portal-integrated apps (accruedincome, heatsim, etc.).
"""
import json
import urllib.request
import urllib.error
from functools import wraps

from flask import request, redirect, session, current_app, g
from flask_login import login_user, current_user

from app import db


class ScriptNameMiddleware:
    """Read X-Script-Name header from nginx and set WSGI SCRIPT_NAME."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        return self.app(environ, start_response)


def validate_token_with_portal(token, app_code, portal_url):
    """Validate a JWT token with the portal API."""
    try:
        url = f'{portal_url}/api/validate-token'
        data = json.dumps({'token': token, 'app_code': app_code}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('valid'):
                return result
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        pass
    return None


def _ensure_local_user(portal_data):
    """Create or update local user from portal data."""
    from app.models.user import User

    username = portal_data.get('username')
    if not username:
        return None

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(
            username=username,
            display_name=portal_data.get('display_name', username),
            email=portal_data.get('email'),
            is_admin=portal_data.get('is_admin', False),
            portal_synced=True,
        )
        db.session.add(user)
    else:
        user.display_name = portal_data.get('display_name', user.display_name)
        user.is_admin = portal_data.get('is_admin', user.is_admin)
        user.portal_synced = True

    db.session.commit()
    return user


def init_portal_auth(app):
    """Register portal auth middleware and before_request hook."""
    app.wsgi_app = ScriptNameMiddleware(app.wsgi_app)

    @app.before_request
    def check_portal_auth():
        # Skip auth for health, static, and api paths
        path = request.path
        if path in ('/health',) or path.startswith('/static/') or path.startswith('/api/'):
            return None

        portal_url = current_app.config.get('PORTAL_URL', 'http://portal:5000')
        app_code = current_app.config.get('APP_CODE', 'mpqpgenerator')
        external_url = current_app.config.get('PORTAL_EXTERNAL_URL', '/')

        # Check for token parameter (portal launch redirect)
        token = request.args.get('token')
        if token:
            result = validate_token_with_portal(token, app_code, portal_url)
            if result:
                session['portal_user'] = result.get('user', {}).get('username') or result.get('username')
                session['portal_role'] = result.get('user', {}).get('role') or result.get('role')
                session.permanent = True
                user = _ensure_local_user(result.get('user', result))
                if user:
                    login_user(user)
                # Redirect to clean URL (without token param)
                # Include script_root so redirect goes back through nginx prefix
                clean_url = request.script_root + request.path
                return redirect(clean_url)
            else:
                return redirect(external_url)

        # Check existing session
        if session.get('portal_user'):
            if not current_user.is_authenticated:
                from app.models.user import User
                user = User.query.filter_by(username=session['portal_user']).first()
                if user:
                    login_user(user)
            return None

        # No auth — redirect to portal
        return redirect(external_url)
