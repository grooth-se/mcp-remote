"""Portal authentication middleware.

Validates JWT tokens from the Subseatec App Portal.
When a user clicks an app in the portal, they are redirected here with a
?token=... query parameter. This module validates that token against the
portal API and auto-creates/logs in a local user via Flask-Login (when
available). Apps without Flask-Login work with session-only auth.

Also installs a WSGI middleware that reads the X-Script-Name header
(set by nginx) so Flask url_for() and redirect() include the correct
/app/<code> prefix automatically.
"""

import urllib.request
import urllib.error
import json
from flask import session, request, redirect, abort, current_app, g


def validate_token_with_portal(token):
    """Call the portal API to validate a JWT token."""
    portal_url = current_app.config.get("PORTAL_URL", "http://portal:5000")
    app_code = current_app.config.get("APP_CODE", "unknown")
    url = f"{portal_url}/api/validate-token"

    payload = json.dumps({"token": token, "app_code": app_code}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("valid"):
            return data.get("user")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        pass
    return None


def _ensure_local_user(portal_user):
    """Find or create a local User and call login_user().

    Returns True if Flask-Login login succeeded, False if Flask-Login
    is not available or the app doesn't support local users.
    """
    try:
        from flask_login import login_user
        from app.extensions import db
        from app.models import User

        username = portal_user.get("username", "portal_user")
        # Resolve role: prefer portal-provided role, then fall back to admin check
        portal_role = portal_user.get("role") or ("admin" if portal_user.get("is_admin") else "engineer")

        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, role=portal_role)
            if portal_user.get("display_name"):
                user.full_name = portal_user["display_name"]
            # Generate a Durabler-style user_id
            if hasattr(User, "generate_user_id"):
                user.user_id = User.generate_user_id(portal_role)
            if hasattr(user, "set_password"):
                import secrets
                user.set_password(secrets.token_hex(32))
            db.session.add(user)
            db.session.commit()
        else:
            # Sync role for existing users on every login
            if getattr(user, "role", None) != portal_role:
                user.role = portal_role
                db.session.commit()

        login_user(user)
        return True
    except Exception:
        return False


def _is_flask_login_authenticated():
    """Check if current_user is authenticated via Flask-Login.

    Returns None if Flask-Login is not available or not initialized.
    """
    try:
        from flask_login import current_user
        return current_user.is_authenticated
    except Exception:
        return None


class ScriptNameMiddleware:
    """WSGI middleware that reads X-Script-Name header from nginx
    and sets SCRIPT_NAME so Flask generates correct prefixed URLs."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            # Strip script_name from PATH_INFO if present
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name):] or "/"
        return self.wsgi_app(environ, start_response)


def init_portal_auth(app):
    """Register the before_request hook and WSGI middleware."""

    # Install SCRIPT_NAME middleware so url_for() / redirect() include prefix
    app.wsgi_app = ScriptNameMiddleware(app.wsgi_app)

    @app.before_request
    def check_portal_auth():
        if request.endpoint == "health" or request.path == "/health":
            return
        if request.path.startswith("/static/"):
            return
        if not current_app.config.get("PORTAL_AUTH_ENABLED", False):
            return

        token = request.args.get("token")
        if token:
            user = validate_token_with_portal(token)
            if user:
                session["portal_user"] = user
                session.permanent = True
                _ensure_local_user(user)
                # Redirect to clean URL without token parameter.
                # url_for / redirect will auto-include the SCRIPT_NAME prefix.
                from urllib.parse import urlencode, urlparse, parse_qs
                parsed = urlparse(request.url)
                params = parse_qs(parsed.query)
                params.pop("token", None)
                clean_query = urlencode(params, doseq=True)
                clean_url = request.script_root + request.path
                if clean_query:
                    clean_url += "?" + clean_query
                return redirect(clean_url)
            else:
                abort(403, description="Invalid or expired token. Please launch this app from the portal.")

        if "portal_user" in session:
            # Session exists — ensure Flask-Login user is set (if app uses it)
            fl_auth = _is_flask_login_authenticated()
            if fl_auth is False:
                # Flask-Login available but user not logged in — fix it
                _ensure_local_user(session["portal_user"])
            g.portal_user = session.get("portal_user")
            return

        portal_url = current_app.config.get("PORTAL_EXTERNAL_URL", "/")
        return redirect(portal_url)

    @app.context_processor
    def inject_portal_user():
        return {"portal_user": getattr(g, "portal_user", session.get("portal_user"))}
