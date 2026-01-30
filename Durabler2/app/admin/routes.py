"""Admin routes for user management."""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from . import admin_bp
from .forms import UserCreateForm, UserEditForm, PasswordChangeForm
from app.extensions import db
from app.models import User, AuditLog, admin_required, ROLE_LABELS


@admin_bp.route('/')
@login_required
@admin_required
def index():
    """Admin dashboard."""
    user_count = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    return render_template('admin/index.html',
                           user_count=user_count,
                           active_users=active_users)


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """List all users."""
    users = User.query.order_by(User.user_id).all()
    return render_template('admin/users.html', users=users, role_labels=ROLE_LABELS)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def user_create():
    """Create a new user."""
    form = UserCreateForm()

    if form.validate_on_submit():
        # Generate user_id based on role
        user_id = User.generate_user_id(form.role.data)

        user = User(
            user_id=user_id,
            username=form.username.data,
            full_name=form.full_name.data,
            email=form.email.data or None,
            role=form.role.data,
            is_active=form.is_active.data
        )
        user.set_password(form.password.data)

        db.session.add(user)

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='CREATE_USER',
            table_name='users',
            new_values={
                'user_id': user_id,
                'username': user.username,
                'role': user.role
            },
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'User {user.username} ({user.user_id}) created successfully!', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, title='Create User')


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(id):
    """Edit an existing user."""
    user = User.query.get_or_404(id)
    form = UserEditForm(original_username=user.username)

    if form.validate_on_submit():
        old_values = {
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
            'is_active': user.is_active
        }

        # Check if role changed - need to regenerate user_id
        if form.role.data != user.role:
            user.user_id = User.generate_user_id(form.role.data)

        user.username = form.username.data
        user.full_name = form.full_name.data
        user.email = form.email.data or None
        user.role = form.role.data
        user.is_active = form.is_active.data

        new_values = {
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
            'is_active': user.is_active
        }

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='UPDATE_USER',
            table_name='users',
            record_id=user.id,
            old_values=old_values,
            new_values=new_values,
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'User {user.username} updated successfully!', 'success')
        return redirect(url_for('admin.users'))

    # Pre-populate form
    if request.method == 'GET':
        form.username.data = user.username
        form.full_name.data = user.full_name
        form.email.data = user.email
        form.role.data = user.role
        form.is_active.data = user.is_active

    return render_template('admin/user_form.html', form=form, user=user,
                           title=f'Edit User: {user.username}')


@admin_bp.route('/users/<int:id>/password', methods=['GET', 'POST'])
@login_required
@admin_required
def user_password(id):
    """Change a user's password."""
    user = User.query.get_or_404(id)
    form = PasswordChangeForm()

    if form.validate_on_submit():
        user.set_password(form.password.data)

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action='CHANGE_PASSWORD',
            table_name='users',
            record_id=user.id,
            new_values={'password_changed': True},
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

        flash(f'Password for {user.username} changed successfully!', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/password_form.html', form=form, user=user)


@admin_bp.route('/users/<int:id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def user_toggle_active(id):
    """Toggle user active status."""
    user = User.query.get_or_404(id)

    # Prevent deactivating yourself
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin.users'))

    old_status = user.is_active
    user.is_active = not user.is_active

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action='TOGGLE_USER_STATUS',
        table_name='users',
        record_id=user.id,
        old_values={'is_active': old_status},
        new_values={'is_active': user.is_active},
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.username} has been {status}.', 'success')
    return redirect(url_for('admin.users'))
