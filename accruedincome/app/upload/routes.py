"""Upload blueprint routes - file upload handling."""

import os
import json
import uuid
from flask import (
    render_template, request, flash, redirect,
    url_for, current_app
)
from werkzeug.utils import secure_filename
import pandas as pd

from . import upload_bp
from app.extensions import db
from app.models import UploadSession

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


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@upload_bp.route('/', methods=['GET', 'POST'])
def index():
    """Multi-file upload form."""
    if request.method == 'POST':
        session_id = str(uuid.uuid4())
        upload_folder = os.path.join(
            current_app.config['UPLOAD_FOLDER'],
            session_id
        )
        os.makedirs(upload_folder, exist_ok=True)

        files_saved = {}
        errors = []

        for file_key, label in REQUIRED_FILES.items():
            if file_key in request.files:
                file = request.files[file_key]
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
                                 errors=errors)
        else:
            flash('All files uploaded successfully!', 'success')
            return redirect(url_for('upload.validate', session_id=session_id))

    return render_template('upload/index.html', required_files=REQUIRED_FILES)


@upload_bp.route('/validate/<session_id>')
def validate(session_id):
    """Validate uploaded files before calculation."""
    session = UploadSession.query.filter_by(session_id=session_id).first_or_404()
    files = json.loads(session.files_json)

    validation_results = {}
    all_valid = True

    for file_key, filepath in files.items():
        try:
            df = pd.read_excel(filepath)
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


@upload_bp.route('/sessions')
def sessions():
    """List all upload sessions."""
    sessions = UploadSession.query\
        .order_by(UploadSession.created_at.desc())\
        .limit(20).all()
    return render_template('upload/sessions.html', sessions=sessions)
