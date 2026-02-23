from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Email
from app.extensions import db
from app.models.user import User
from app.models.application import Application
from app.models.permission import UserPermission
from app.services.auth_service import revoke_user_sessions
from app.utils.decorators import admin_required
from app.utils.logging import log_audit

admin_users_bp = Blueprint('admin_users', __name__)


def _durabler_role_choices():
    """Return (value, label) choices for the Durabler2 role dropdown."""
    app = Application.query.filter_by(app_code='durabler2').first()
    roles = app.get_available_roles() if app else {}
    choices = [('', '-- No access --')]
    choices.extend((v, label) for v, label in roles.items())
    return choices


class UserCreateForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    display_name = StringField('Display Name', validators=[Optional(), Length(max=120)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    is_admin = BooleanField('Admin')
    durabler_role = SelectField('Durabler2 Role', choices=[])
    submit = SubmitField('Create User')


class UserEditForm(FlaskForm):
    display_name = StringField('Display Name', validators=[Optional(), Length(max=120)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    durabler_role = SelectField('Durabler2 Role', choices=[])
    submit = SubmitField('Save Changes')


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField('Reset Password')


@admin_users_bp.route('/')
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    durabler_app = Application.query.filter_by(app_code='durabler2').first()
    durabler_roles = durabler_app.get_available_roles() if durabler_app else {}
    # Build a {user_id: role_value} map
    user_roles = {}
    if durabler_app:
        perms = UserPermission.query.filter_by(app_id=durabler_app.id).all()
        for p in perms:
            user_roles[p.user_id] = p.role
    return render_template('admin/users/list.html', users=users,
                           durabler_roles=durabler_roles, user_roles=user_roles)


@admin_users_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    form = UserCreateForm()
    form.durabler_role.choices = _durabler_role_choices()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists.', 'danger')
        else:
            user = User(
                username=form.username.data,
                display_name=form.display_name.data,
                email=form.email.data,
                is_admin=form.is_admin.data,
                created_by=current_user.id,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            # Grant Durabler2 permission with selected role
            durabler_role = form.durabler_role.data
            if durabler_role:
                durabler_app = Application.query.filter_by(app_code='durabler2').first()
                if durabler_app:
                    perm = UserPermission(user_id=user.id, app_id=durabler_app.id,
                                          role=durabler_role, granted_by=current_user.id)
                    db.session.add(perm)
            db.session.commit()
            log_audit(current_user.id, 'create_user', 'user', user.id, new_value=user.username)
            flash(f'User {user.username} created.', 'success')
            return redirect(url_for('admin_users.list_users'))
    return render_template('admin/users/form.html', form=form, title='Create User')


@admin_users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users.list_users'))

    form = UserEditForm(obj=user)
    form.durabler_role.choices = _durabler_role_choices()

    # Pre-select current Durabler2 role
    durabler_app = Application.query.filter_by(app_code='durabler2').first()
    current_perm = None
    if durabler_app:
        current_perm = UserPermission.query.filter_by(
            user_id=user.id, app_id=durabler_app.id).first()
    if request.method == 'GET' and current_perm:
        form.durabler_role.data = current_perm.role or ''

    if form.validate_on_submit():
        old_name = user.display_name
        user.display_name = form.display_name.data
        user.email = form.email.data

        # Update Durabler2 role
        durabler_role = form.durabler_role.data
        if durabler_app:
            if durabler_role:
                if current_perm:
                    current_perm.role = durabler_role
                else:
                    perm = UserPermission(user_id=user.id, app_id=durabler_app.id,
                                          role=durabler_role, granted_by=current_user.id)
                    db.session.add(perm)
            else:
                # No role selected — revoke Durabler2 access
                if current_perm:
                    db.session.delete(current_perm)

        db.session.commit()
        log_audit(current_user.id, 'edit_user', 'user', user.id,
                  old_value=old_name, new_value=user.display_name)
        flash('User updated.', 'success')
        return redirect(url_for('admin_users.list_users'))
    return render_template('admin/users/form.html', form=form, title=f'Edit {user.username}', user=user)


@admin_users_bp.route('/<int:user_id>/reset-password', methods=['GET', 'POST'])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users.list_users'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        revoke_user_sessions(user.id)
        db.session.commit()
        log_audit(current_user.id, 'reset_password', 'user', user.id)
        flash(f'Password reset for {user.username}.', 'success')
        return redirect(url_for('admin_users.list_users'))
    return render_template('admin/users/form.html', form=form, title=f'Reset Password: {user.username}', user=user)


@admin_users_bp.route('/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users.list_users'))
    if user.id == current_user.id:
        flash('You cannot deactivate yourself.', 'danger')
        return redirect(url_for('admin_users.list_users'))

    user.is_active_user = not user.is_active_user
    if not user.is_active_user:
        revoke_user_sessions(user.id)
    db.session.commit()
    status = 'activated' if user.is_active_user else 'deactivated'
    log_audit(current_user.id, f'{status}_user', 'user', user.id)
    flash(f'User {user.username} {status}.', 'success')
    return redirect(url_for('admin_users.list_users'))


@admin_users_bp.route('/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users.list_users'))
    if user.id == current_user.id:
        flash('You cannot change your own admin status.', 'danger')
        return redirect(url_for('admin_users.list_users'))

    user.is_admin = not user.is_admin
    db.session.commit()
    status = 'granted' if user.is_admin else 'revoked'
    log_audit(current_user.id, f'admin_{status}', 'user', user.id)
    flash(f'Admin rights {status} for {user.username}.', 'success')
    return redirect(url_for('admin_users.list_users'))


@admin_users_bp.route('/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users.list_users'))
    if user.id == current_user.id:
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('admin_users.list_users'))

    username = user.username
    log_audit(current_user.id, 'delete_user', 'user', user.id, old_value=username)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {username} deleted.', 'success')
    return redirect(url_for('admin_users.list_users'))
