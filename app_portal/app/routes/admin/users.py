from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Email
from app.extensions import db
from app.models.user import User
from app.services.auth_service import revoke_user_sessions
from app.utils.decorators import admin_required
from app.utils.logging import log_audit

admin_users_bp = Blueprint('admin_users', __name__)


class UserCreateForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    display_name = StringField('Display Name', validators=[Optional(), Length(max=120)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    is_admin = BooleanField('Admin')
    submit = SubmitField('Create User')


class UserEditForm(FlaskForm):
    display_name = StringField('Display Name', validators=[Optional(), Length(max=120)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    submit = SubmitField('Save Changes')


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField('Reset Password')


@admin_users_bp.route('/')
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template('admin/users/list.html', users=users)


@admin_users_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    form = UserCreateForm()
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
    if form.validate_on_submit():
        old_name = user.display_name
        user.display_name = form.display_name.data
        user.email = form.email.data
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
