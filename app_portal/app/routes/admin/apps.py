from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, URL
from app.extensions import db
from app.models.application import Application
from app.services.app_health import check_health
from app.utils.decorators import admin_required
from app.utils.logging import log_audit

admin_apps_bp = Blueprint('admin_apps', __name__)


class AppForm(FlaskForm):
    app_code = StringField('App Code', validators=[DataRequired(), Length(max=50)])
    app_name = StringField('App Name', validators=[DataRequired(), Length(max=120)])
    description = TextAreaField('Description', validators=[Optional()])
    internal_url = StringField('Internal URL', validators=[DataRequired(), Length(max=256)])
    icon = StringField('Icon (Bootstrap Icon class)', validators=[Optional(), Length(max=50)])
    display_order = IntegerField('Display Order', default=0)
    requires_gpu = BooleanField('Requires GPU')
    submit = SubmitField('Save')


@admin_apps_bp.route('/')
@admin_required
def list_apps():
    apps = Application.query.order_by(Application.display_order).all()
    health = {}
    for app in apps:
        try:
            health[app.app_code] = check_health(app.internal_url)
        except Exception:
            health[app.app_code] = False
    return render_template('admin/apps/list.html', apps=apps, health=health)


@admin_apps_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_app():
    form = AppForm()
    if form.validate_on_submit():
        if Application.query.filter_by(app_code=form.app_code.data).first():
            flash('App code already exists.', 'danger')
        else:
            app = Application(
                app_code=form.app_code.data,
                app_name=form.app_name.data,
                description=form.description.data,
                internal_url=form.internal_url.data,
                icon=form.icon.data or 'bi-app',
                display_order=form.display_order.data or 0,
                requires_gpu=form.requires_gpu.data,
            )
            db.session.add(app)
            db.session.commit()
            log_audit(current_user.id, 'create_app', 'app', app.id, new_value=app.app_code)
            flash(f'Application {app.app_name} registered.', 'success')
            return redirect(url_for('admin_apps.list_apps'))
    return render_template('admin/apps/form.html', form=form, title='Register Application')


@admin_apps_bp.route('/<int:app_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_app(app_id):
    app = db.session.get(Application, app_id)
    if not app:
        flash('Application not found.', 'danger')
        return redirect(url_for('admin_apps.list_apps'))

    form = AppForm(obj=app)
    if form.validate_on_submit():
        old_name = app.app_name
        app.app_code = form.app_code.data
        app.app_name = form.app_name.data
        app.description = form.description.data
        app.internal_url = form.internal_url.data
        app.icon = form.icon.data or 'bi-app'
        app.display_order = form.display_order.data or 0
        app.requires_gpu = form.requires_gpu.data
        db.session.commit()
        log_audit(current_user.id, 'edit_app', 'app', app.id,
                  old_value=old_name, new_value=app.app_name)
        flash('Application updated.', 'success')
        return redirect(url_for('admin_apps.list_apps'))
    return render_template('admin/apps/form.html', form=form, title=f'Edit {app.app_name}', app=app)


@admin_apps_bp.route('/<int:app_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(app_id):
    app = db.session.get(Application, app_id)
    if not app:
        flash('Application not found.', 'danger')
        return redirect(url_for('admin_apps.list_apps'))

    app.is_active = not app.is_active
    db.session.commit()
    status = 'enabled' if app.is_active else 'disabled'
    log_audit(current_user.id, f'{status}_app', 'app', app.id)
    flash(f'{app.app_name} {status}.', 'success')
    return redirect(url_for('admin_apps.list_apps'))
