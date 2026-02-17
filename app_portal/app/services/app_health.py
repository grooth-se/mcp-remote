import urllib.request
import urllib.error
from flask import current_app


def check_health(internal_url):
    """Check if an app is reachable. Returns True if online."""
    timeout = current_app.config.get('HEALTH_CHECK_TIMEOUT', 3)
    try:
        req = urllib.request.Request(internal_url, method='GET')
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def check_all_apps():
    """Check health of all active apps. Returns dict of app_code -> online status."""
    from app.models.application import Application
    apps = Application.query.filter_by(is_active=True).all()
    results = {}
    for app in apps:
        results[app.app_code] = check_health(app.internal_url)
    return results
