from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_login import login_required, current_user
from app.models.application import Application
from app.services.token_service import generate_token
from app.services.app_health import check_health
from app.utils.logging import log_access

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    apps = current_user.get_permitted_apps()
    # Check health status for each app
    app_status = {}
    for app in apps:
        try:
            app_status[app.app_code] = check_health(app.internal_url)
        except Exception:
            app_status[app.app_code] = False
    return render_template('dashboard/index.html', apps=apps, app_status=app_status)


@dashboard_bp.route('/launch/<app_code>')
@login_required
def launch(app_code):
    app = Application.query.filter_by(app_code=app_code, is_active=True).first()
    if not app:
        abort(404)

    if not current_user.has_app_permission(app_code):
        flash('You do not have permission to access this application.', 'danger')
        return redirect(url_for('dashboard.index'))

    # Generate a token for the app
    from flask import current_app
    token = generate_token(current_user.id, current_app.config['TOKEN_EXPIRY_HOURS'])

    log_access(current_user.id, app.id, 'access_app', request.remote_addr,
               details=f'Launched {app.app_name}')

    # Redirect to the app's URL via nginx proxy path with token
    launch_url = f'/app/{app_code}/?token={token}'
    return redirect(launch_url)
