"""Upload blueprint routes - file upload handling."""

import os
import json
import pickle
import uuid
import shutil
from flask import (
    render_template, request, flash, redirect,
    url_for, current_app
)
from werkzeug.utils import secure_filename
import pandas as pd

from . import upload_bp
from app.extensions import db
from app.models import UploadSession
from app.calculation.services import IntegrationDataLoader

# Required files from Monitor G5
REQUIRED_FILES = {
    'valutakurser': 'Valutakurser (Currency Rates)',
    'projectadjustments': 'Project Adjustments',
    'CO_proj_crossref': 'CO Project Cross Reference',
    'projektuppf': 'Projektuppfoljning (Project Follow-up)',
    'inkoporderforteckning': 'Inkopsorderforteckning (Purchase Orders)',
    'kundorderforteckning': 'Kundorderforteckning (Customer Orders)',
    'kontoplan': 'Kontoplan (Chart of Accounts)',
    'verlista': 'Verifikationslista (Transaction List)',
    'tiduppfoljning': 'Tidsuppfoljning (Time Tracking)',
    'faktureringslogg': 'Faktureringslogg (Invoicing/Milestones)',
    'Accuredhistory': 'Accrued History'
}

# Default file paths config file
DEFAULT_PATHS_FILE = 'file_paths.json'


def get_paths_config_file():
    """Get path to the file paths config file."""
    instance_path = current_app.instance_path
    os.makedirs(instance_path, exist_ok=True)
    return os.path.join(instance_path, DEFAULT_PATHS_FILE)


def load_default_paths():
    """Load default file paths from config."""
    config_file = get_paths_config_file()
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return {}


def save_default_paths(paths):
    """Save default file paths to config."""
    config_file = get_paths_config_file()
    with open(config_file, 'w') as f:
        json.dump(paths, f, indent=2)


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@upload_bp.route('/', methods=['GET', 'POST'])
def index():
    """File path selection form with persistent defaults."""
    default_paths = load_default_paths()

    if request.method == 'POST':
        # Check if using file paths or file uploads
        use_paths = request.form.get('use_paths') == 'true'

        if use_paths:
            # Use file paths from form
            return handle_path_upload(request.form, default_paths)
        else:
            # Use traditional file upload
            return handle_file_upload(request.files)

    return render_template('upload/index.html',
                          required_files=REQUIRED_FILES,
                          default_paths=default_paths)


def handle_path_upload(form_data, current_defaults):
    """Handle upload using file paths."""
    session_id = str(uuid.uuid4())
    upload_folder = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        session_id
    )
    os.makedirs(upload_folder, exist_ok=True)

    files_saved = {}
    errors = []
    new_paths = {}

    for file_key, label in REQUIRED_FILES.items():
        path = form_data.get(f'path_{file_key}', '').strip()
        new_paths[file_key] = path

        if not path:
            errors.append(f'Missing path for: {label}')
            continue

        if not os.path.exists(path):
            errors.append(f'File not found: {path}')
            continue

        if not path.lower().endswith(('.xlsx', '.xls')):
            errors.append(f'Invalid file type for {label}: {path}')
            continue

        try:
            # Copy file to upload folder
            dest_path = os.path.join(upload_folder, f'{file_key}.xlsx')
            shutil.copy2(path, dest_path)
            files_saved[file_key] = dest_path
        except Exception as e:
            errors.append(f'Error copying {label}: {str(e)}')

    # Save paths as new defaults (even if some failed)
    save_default_paths(new_paths)

    # Create session record
    session = UploadSession(
        session_id=session_id,
        files_json=json.dumps(files_saved),
        validation_errors=json.dumps(errors) if errors else None,
        status='uploaded' if not errors else 'incomplete'
    )
    db.session.add(session)
    db.session.commit()

    if errors:
        flash(f'Upload incomplete: {len(errors)} files missing or invalid', 'warning')
        return render_template('upload/index.html',
                             required_files=REQUIRED_FILES,
                             default_paths=new_paths,
                             errors=errors)
    else:
        flash('All files loaded successfully!', 'success')
        return redirect(url_for('upload.validate', session_id=session_id))


def handle_file_upload(files):
    """Handle traditional file upload."""
    session_id = str(uuid.uuid4())
    upload_folder = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        session_id
    )
    os.makedirs(upload_folder, exist_ok=True)

    files_saved = {}
    errors = []

    for file_key, label in REQUIRED_FILES.items():
        if file_key in files:
            file = files[file_key]
            if file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(upload_folder, f'{file_key}.xlsx')
                file.save(filepath)
                files_saved[file_key] = filepath
            elif file.filename:
                errors.append(f'Invalid file type for {label}')
            else:
                errors.append(f'Missing: {label}')
        else:
            errors.append(f'Missing: {label}')

    # Create session record
    session = UploadSession(
        session_id=session_id,
        files_json=json.dumps(files_saved),
        validation_errors=json.dumps(errors) if errors else None,
        status='uploaded' if not errors else 'incomplete'
    )
    db.session.add(session)
    db.session.commit()

    if errors:
        flash(f'Upload incomplete: {len(errors)} files missing or invalid', 'warning')
        return render_template('upload/index.html',
                             required_files=REQUIRED_FILES,
                             default_paths=load_default_paths(),
                             errors=errors)
    else:
        flash('All files uploaded successfully!', 'success')
        return redirect(url_for('upload.validate', session_id=session_id))


@upload_bp.route('/validate/<session_id>')
def validate(session_id):
    """Validate uploaded files before calculation."""
    session = UploadSession.query.filter_by(session_id=session_id).first_or_404()
    files = json.loads(session.files_json)

    validation_results = {}
    all_valid = True

    for file_key, filepath in files.items():
        try:
            df = pd.read_excel(filepath, engine='openpyxl')
            validation_results[file_key] = {
                'status': 'ok',
                'rows': len(df),
                'columns': df.columns.tolist()[:5],
                'label': REQUIRED_FILES.get(file_key, file_key)
            }
        except Exception as e:
            validation_results[file_key] = {
                'status': 'error',
                'message': str(e),
                'label': REQUIRED_FILES.get(file_key, file_key)
            }
            all_valid = False

    if all_valid:
        session.status = 'validated'
        db.session.commit()

    return render_template('upload/validate.html',
                          session=session,
                          validation=validation_results,
                          all_valid=all_valid)


@upload_bp.route('/from-integration', methods=['POST'])
def from_integration():
    """Load data from MG5integration API instead of Excel files."""
    closing_date = request.form.get('closing_date', '').strip() or None

    try:
        loader = IntegrationDataLoader()
        dataframes = loader.load()
    except ConnectionError as e:
        flash(f'Could not connect to MG5 Integration: {e}', 'error')
        return redirect(url_for('upload.index'))
    except Exception as e:
        flash(f'Error loading integration data: {e}', 'error')
        return redirect(url_for('upload.index'))

    # Create session with source='integration' and optional closing_date
    session_id = str(uuid.uuid4())
    files_meta = {'source': 'integration'}
    if closing_date:
        files_meta['closing_date'] = closing_date
    session = UploadSession(
        session_id=session_id,
        files_json=json.dumps(files_meta),
        status='validated'
    )
    db.session.add(session)
    db.session.commit()

    # Store dataframes in a temp file for the calculation step
    upload_folder = os.path.join(
        current_app.config['UPLOAD_FOLDER'], session_id
    )
    os.makedirs(upload_folder, exist_ok=True)
    pickle_path = os.path.join(upload_folder, 'integration_data.pkl')
    with open(pickle_path, 'wb') as f:
        pickle.dump(dataframes, f)

    flash('Data loaded from MG5 Integration successfully!', 'success')
    return redirect(url_for('calculation.index'))


@upload_bp.route('/integration-health')
def integration_health():
    """Check MG5integration API health (AJAX endpoint)."""
    loader = IntegrationDataLoader()
    result = loader.check_health()
    return json.dumps(result), 200, {'Content-Type': 'application/json'}


@upload_bp.route('/sessions')
def sessions():
    """List all upload sessions."""
    sessions = UploadSession.query\
        .order_by(UploadSession.created_at.desc())\
        .limit(20).all()
    return render_template('upload/sessions.html', sessions=sessions)
