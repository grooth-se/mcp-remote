"""User profile and password management routes."""
from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from . import auth_bp
from .profile_forms import ChangePasswordForm
from app.extensions import db
from app.models import AuditLog


@auth_bp.route('/profile')
@login_required
def profile():
    """Display user profile information."""
    return render_template('auth/profile.html')


@auth_bp.route('/profile/password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change current user's password."""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html', form=form)

        current_user.set_password(form.new_password.data)
        db.session.commit()
        AuditLog.log('update_user', resource_type='user',
                      resource_id=current_user.id,
                      resource_name=current_user.username,
                      details={'action': 'password_change'})

        flash('Password changed successfully.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/change_password.html', form=form)
