from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.models.user import User
from app.models.audit import AuditLog
from app.forms.admin import UserForm
from functools import wraps

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Administratörsbehörighet krävs.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/')
@login_required
@admin_required
def index():
    return render_template('admin/index.html')


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
@limiter.limit("3 per hour", methods=["POST"])
def new_user():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Användarnamnet finns redan.', 'danger')
            return render_template('admin/user_form.html', form=form, title='Ny användare')

        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
        )
        if form.password.data:
            user.set_password(form.password.data)
        else:
            flash('Lösenord krävs för ny användare.', 'danger')
            return render_template('admin/user_form.html', form=form, title='Ny användare')

        db.session.add(user)
        db.session.commit()
        flash(f'Användare {user.username} har skapats.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, title='Ny användare')


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@limiter.limit("3 per hour", methods=["POST"])
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('Användaren hittades inte.', 'danger')
        return redirect(url_for('admin.users'))

    form = UserForm(obj=user)
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash(f'Användare {user.username} har uppdaterats.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, title=f'Redigera {user.username}')


@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    company_id = session.get('active_company_id')
    page = request.args.get('page', 1, type=int)

    query = AuditLog.query
    if company_id:
        query = query.filter_by(company_id=company_id)

    logs = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/audit_log.html', logs=logs)
