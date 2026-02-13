"""Admin routes for user management and system overview."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user

from . import admin_bp
from .forms import CreateUserForm, EditUserForm
from app.extensions import db
from app.models import User, Simulation, SteelGrade, WeldProject, admin_required


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin dashboard with system overview."""
    user_count = User.query.count()
    sim_count = Simulation.query.count()
    grade_count = SteelGrade.query.count()
    weld_count = WeldProject.query.count()

    recent_logins = User.query.filter(
        User.last_login.isnot(None)
    ).order_by(User.last_login.desc()).limit(10).all()

    return render_template(
        'admin/dashboard.html',
        user_count=user_count,
        sim_count=sim_count,
        grade_count=grade_count,
        weld_count=weld_count,
        recent_logins=recent_logins,
    )


@admin_bp.route('/users')
@admin_required
def users():
    """List all users with search and filter."""
    q = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '')
    page = request.args.get('page', 1, type=int)

    query = User.query
    if q:
        query = query.filter(User.username.ilike(f'%{q}%'))
    if role_filter:
        query = query.filter(User.role == role_filter)

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'admin/users.html',
        users=pagination.items,
        pagination=pagination,
        q=q,
        role_filter=role_filter,
    )


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@admin_required
def create_user():
    """Create a new user."""
    form = CreateUserForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            role=form.role.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{user.username}" created.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, is_edit=False)


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(id):
    """Edit an existing user."""
    user = User.query.get_or_404(id)
    form = EditUserForm(obj=user)

    if form.validate_on_submit():
        user.role = form.role.data
        if form.new_password.data:
            user.set_password(form.new_password.data)
            flash(f'Password reset for "{user.username}".', 'info')
        db.session.commit()
        flash(f'User "{user.username}" updated.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, is_edit=True, user=user)


@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@admin_required
def delete_user(id):
    """Delete a user (cannot delete yourself)."""
    user = User.query.get_or_404(id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{username}" deleted.', 'success')
    return redirect(url_for('admin.users'))
