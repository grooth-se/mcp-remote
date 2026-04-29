from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, limiter
from app.forms.auth import LoginForm
from app.models.audit import AuditLog
from app.models.user import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.active:
            login_user(user)
            audit = AuditLog(user_id=user.id, action='login',
                             entity_type='user', entity_id=user.id)
            db.session.add(audit)
            db.session.commit()
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc:
                next_page = None
            return redirect(next_page or url_for('dashboard.index'))
        audit = AuditLog(user_id=None, action='login_failed',
                         entity_type='user', entity_id=None,
                         new_values={'username': form.username.data})
        db.session.add(audit)
        db.session.commit()
        flash('Felaktigt användarnamn eller lösenord.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Du har loggats ut.', 'info')
    return redirect(url_for('auth.login'))
