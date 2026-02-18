"""Portal authentication middleware.

Validates JWT tokens from the Subseatec App Portal.
When a user clicks an app in the portal, they are redirected here with a
?token=... query parameter. This module validates that token against the
portal's /api/validate-token endpoint and stores the user in the session.
"""

import urllib.request
import urllib.error
import json
from functools import wraps
from flask import session, request, redirect, abort, current_app, g


def validate_token_with_portal(token):
    """Call the portal API to validate a JWT token.

    Returns user dict on success, None on failure.
    """
    portal_url = current_app.config.get('PORTAL_URL', 'http://portal:5000')
    app_code = current_app.config.get('APP_CODE', 'accruedincome')
    url = f'{portal_url}/api/validate-token'

    payload = json.dumps({'token': token, 'app_code': app_code}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('valid'):
            return data.get('user')
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        pass
    return None


def init_portal_auth(app):
    """Register the before_request hook that handles portal authentication."""

    @app.before_request
    def check_portal_auth():
        # Skip auth for health check endpoint and static files
        if request.endpoint == 'health' or request.path == '/health':
            return
        if request.path.startswith('/static/'):
            return

        # If portal auth is disabled (local dev), skip
        if not current_app.config.get('PORTAL_AUTH_ENABLED', False):
            g.portal_user = None
            return

        # Check for token in query string (initial launch from portal)
        token = request.args.get('token')
        if token:
            user = validate_token_with_portal(token)
            if user:
                session['portal_user'] = user
                session.permanent = True
                # Redirect to same URL without the token parameter
                from urllib.parse import urlencode, urlparse, parse_qs
                parsed = urlparse(request.url)
                params = parse_qs(parsed.query)
                params.pop('token', None)
                clean_query = urlencode(params, doseq=True)
                clean_url = request.path
                if clean_query:
                    clean_url += '?' + clean_query
                return redirect(clean_url)
            else:
                abort(403, description='Invalid or expired token. Please launch this app from the portal.')

        # Check for existing session
        if 'portal_user' not in session:
            # No session — redirect to portal login
            portal_url = current_app.config.get('PORTAL_EXTERNAL_URL', '/')
            return redirect(portal_url)

        # Make user available in templates via g
        g.portal_user = session.get('portal_user')

    @app.context_processor
    def inject_portal_user():
        """Make portal_user available in all templates."""
        return {'portal_user': getattr(g, 'portal_user', session.get('portal_user'))}
