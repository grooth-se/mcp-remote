from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo
from app.services.auth_service import authenticate, change_password
from app.utils.logging import log_access

auth_bp = Blueprint('auth', __name__)


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Sign In')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(), EqualTo('new_password', message='Passwords must match.')
    ])
    submit = SubmitField('Change Password')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate(form.username.data, form.password.data)
        if user:
            login_user(user, remember=form.remember_me.data)
            log_access(user.id, None, 'login', request.remote_addr)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            log_access(None, None, 'login_failed', request.remote_addr,
                       details=f'Username: {form.username.data}')
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    log_access(current_user.id, None, 'logout', request.remote_addr)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password_view():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        success, error = change_password(current_user, form.current_password.data, form.new_password.data)
        if success:
            flash('Password changed successfully. Please log in again.', 'success')
            logout_user()
            return redirect(url_for('auth.login'))
        else:
            flash(error, 'danger')
    return render_template('auth/change_password.html', form=form)
