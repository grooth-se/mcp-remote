import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required
from werkzeug.utils import secure_filename

from app import db
from app.models.generation import GenerationJob
from app.models.project import Customer
from app.models.template import Template
from app.services.document_processor import extract_text, get_file_info, SUPPORTED_EXTENSIONS

upload_bp = Blueprint('upload', __name__)

ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls'}


def _allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


@upload_bp.route('/', methods=['GET'])
@login_required
def index():
    """Upload form for new generation job."""
    customers = Customer.query.order_by(Customer.name).all()
    templates = Template.query.filter_by(active=True).order_by(Template.document_type, Template.name).all()
    from app.models.project import Project
    product_types = Project.PRODUCT_TYPES
    return render_template('upload/index.html',
                           customers=customers,
                           templates=templates,
                           product_types=product_types)


@upload_bp.route('/', methods=['POST'])
@login_required
def create():
    """Handle file upload and create generation job."""
    project_name = request.form.get('project_name', '').strip()
    customer_name = request.form.get('customer_name', '').strip()
    product_type = request.form.get('product_type', '')
    template_id = request.form.get('template_id', type=int)
    doc_type = request.form.get('document_type', 'MPQP')

    if not project_name:
        flash('Project name is required.', 'danger')
        return redirect(url_for('upload.index'))

    files = request.files.getlist('documents')
    if not files or all(f.filename == '' for f in files):
        flash('Please upload at least one document.', 'danger')
        return redirect(url_for('upload.index'))

    # Get or create customer
    customer_id = None
    if customer_name:
        customer = Customer.query.filter_by(name=customer_name).first()
        if not customer:
            customer = Customer(name=customer_name)
            db.session.add(customer)
            db.session.flush()
        customer_id = customer.id

    # Create job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Save uploaded files and extract text
    uploaded_docs = []
    for f in files:
        if f.filename and _allowed_file(f.filename):
            filename = secure_filename(f.filename)
            filepath = os.path.join(job_dir, filename)
            f.save(filepath)

            info = get_file_info(filepath)
            result = extract_text(filepath)

            uploaded_docs.append({
                'filename': filename,
                'filepath': filepath,
                'format': result.get('format', ''),
                'page_count': result.get('page_count', 0),
                'text_length': len(result.get('text', '')),
                'size': info['size_human'],
                'error': result.get('error'),
            })

    if not uploaded_docs:
        flash('No valid documents were uploaded. Supported formats: PDF, DOCX, XLSX.', 'danger')
        return redirect(url_for('upload.index'))

    # Create generation job
    job = GenerationJob(
        status='pending',
        new_project_name=project_name,
        customer_id=customer_id,
        product_type=product_type,
        template_id=template_id,
        uploaded_documents=uploaded_docs,
    )
    db.session.add(job)
    db.session.commit()

    flash(f'Generation job created with {len(uploaded_docs)} document(s).', 'success')
    return redirect(url_for('generate.status', job_id=job.id))


@upload_bp.route('/api/customers')
@login_required
def api_customers():
    """JSON endpoint for customer autocomplete."""
    q = request.args.get('q', '').strip()
    query = Customer.query.order_by(Customer.name)
    if q:
        query = query.filter(Customer.name.ilike(f'%{q}%'))
    customers = [{'id': c.id, 'name': c.name} for c in query.limit(20).all()]
    return jsonify(customers)
