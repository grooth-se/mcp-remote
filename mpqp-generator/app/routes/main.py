from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, login_user, logout_user

from app import db
from app.models.user import User
from app.models.project import Project, Customer
from app.models.generation import GenerationJob

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """Dashboard showing recent jobs and stats."""
    recent_jobs = GenerationJob.query.order_by(
        GenerationJob.created_at.desc()
    ).limit(10).all()

    stats = {
        'total_projects': Project.query.count(),
        'total_customers': Customer.query.count(),
        'total_jobs': GenerationJob.query.count(),
        'completed_jobs': GenerationJob.query.filter_by(status='completed').count(),
        'pending_jobs': GenerationJob.query.filter(
            GenerationJob.status.in_(['pending', 'processing', 'extracting', 'analyzing', 'matching', 'generating'])
        ).count(),
    }

    # Check Ollama status for dashboard indicator
    from app.services.llm_client import check_ollama_status
    ollama_status = check_ollama_status()

    return render_template('main/dashboard.html', recent_jobs=recent_jobs,
                           stats=stats, ollama=ollama_status)


@main_bp.route('/projects')
@login_required
def projects():
    """List all indexed projects."""
    page = request.args.get('page', 1, type=int)
    projects = Project.query.order_by(Project.project_number).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template('main/projects.html', projects=projects)


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Standalone login (used when portal auth is disabled)."""
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next', '/')
            return redirect(next_page)
        flash('Invalid username or password.', 'danger')

    return render_template('main/login.html')


@main_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))
