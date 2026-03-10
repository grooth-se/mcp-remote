import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required
from werkzeug.utils import secure_filename

from app import db
from app.models.template import Template
from app.models.document import Document
from app.models.project import Customer, Project
from app.services.llm_client import check_ollama_status
from app.services import vector_store

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@login_required
def index():
    """Admin dashboard with system status."""
    ollama_status = check_ollama_status()
    templates = Template.query.filter_by(active=True).all()
    customers = Customer.query.order_by(Customer.name).all()
    vector_stats = vector_store.get_collection_stats()

    indexed_docs = Document.query.filter(Document.indexed_at.isnot(None)).count()
    total_docs = Document.query.count()
    indexed_projects = Project.query.filter(Project.indexed_at.isnot(None)).count()
    total_projects = Project.query.count()

    return render_template('admin/index.html',
                           ollama_status=ollama_status,
                           templates=templates,
                           customers=customers,
                           vector_stats=vector_stats,
                           indexed_docs=indexed_docs,
                           total_docs=total_docs,
                           indexed_projects=indexed_projects,
                           total_projects=total_projects)


@admin_bp.route('/templates', methods=['GET'])
@login_required
def templates():
    """Template management."""
    templates = Template.query.order_by(Template.document_type, Template.name).all()
    return render_template('admin/templates.html', templates=templates)


@admin_bp.route('/templates/upload', methods=['POST'])
@login_required
def upload_template():
    """Upload a new document template."""
    name = request.form.get('name', '').strip()
    document_type = request.form.get('document_type', '')
    description = request.form.get('description', '').strip()
    customer_id = request.form.get('customer_id', type=int)

    f = request.files.get('template_file')
    if not f or not f.filename:
        flash('Please select a template file.', 'danger')
        return redirect(url_for('admin.templates'))

    if not name:
        flash('Template name is required.', 'danger')
        return redirect(url_for('admin.templates'))

    filename = secure_filename(f.filename)
    ext = os.path.splitext(filename)[1].lower()
    fmt = 'DOCX' if ext in ('.docx', '.doc') else 'XLSX' if ext in ('.xlsx', '.xls') else ext.upper()

    template_dir = current_app.config['TEMPLATE_FOLDER_PATH']
    os.makedirs(template_dir, exist_ok=True)
    filepath = os.path.join(template_dir, filename)
    f.save(filepath)

    template = Template(
        name=name,
        description=description,
        document_type=document_type,
        format=fmt,
        file_path=filepath,
        customer_id=customer_id if customer_id else None,
    )
    db.session.add(template)
    db.session.commit()

    flash(f'Template "{name}" uploaded.', 'success')
    return redirect(url_for('admin.templates'))


@admin_bp.route('/indexing')
@login_required
def indexing():
    """Document indexing management page."""
    projects = Project.query.order_by(Project.project_number).all()
    documents = Document.query.order_by(Document.created_at.desc()).all()
    vector_stats = vector_store.get_collection_stats()
    ollama_status = check_ollama_status()

    return render_template('admin/indexing.html',
                           projects=projects,
                           documents=documents,
                           vector_stats=vector_stats,
                           ollama_status=ollama_status)


@admin_bp.route('/indexing/document/<int:document_id>', methods=['POST'])
@login_required
def index_document(document_id):
    """Index a single document into the vector store."""
    from app.services.embedder import index_document as do_index
    result = do_index(document_id)

    if 'error' in result:
        flash(f'Indexing failed: {result["error"]}', 'danger')
    else:
        flash(f'Document indexed: {result["chunks_indexed"]} chunks created.', 'success')

    return redirect(url_for('admin.indexing'))


@admin_bp.route('/indexing/project/<int:project_id>', methods=['POST'])
@login_required
def index_project(project_id):
    """Index all documents in a project."""
    from app.services.embedder import index_project as do_index
    result = do_index(project_id)

    if 'error' in result:
        flash(f'Indexing failed: {result["error"]}', 'danger')
    else:
        flash(f'Project indexed: {result["indexed"]}/{result["total_documents"]} documents.', 'success')

    return redirect(url_for('admin.indexing'))


@admin_bp.route('/indexing/reindex/<int:document_id>', methods=['POST'])
@login_required
def reindex_document(document_id):
    """Re-index a document (delete old chunks and re-process)."""
    from app.services.embedder import reindex_document as do_reindex
    result = do_reindex(document_id)

    if 'error' in result:
        flash(f'Re-indexing failed: {result["error"]}', 'danger')
    else:
        flash(f'Document re-indexed: {result["chunks_indexed"]} chunks.', 'success')

    return redirect(url_for('admin.indexing'))


@admin_bp.route('/search')
@login_required
def search():
    """Vector search interface for testing."""
    query = request.args.get('q', '').strip()
    doc_type = request.args.get('document_type', '')
    n_results = request.args.get('n', 10, type=int)
    results = []

    if query:
        from app.services.embedder import search_similar_chunks
        results = search_similar_chunks(
            query,
            n_results=n_results,
            document_type=doc_type if doc_type else None,
        )

    return render_template('admin/search.html',
                           query=query,
                           doc_type=doc_type,
                           results=results)


@admin_bp.route('/scan', methods=['GET'])
@login_required
def scan():
    """Project folder scanning page."""
    historical_path = current_app.config['HISTORICAL_PROJECTS_PATH']
    return render_template('admin/scan.html', historical_path=historical_path)


@admin_bp.route('/scan', methods=['POST'])
@login_required
def scan_run():
    """Execute a project folder scan."""
    scan_path = request.form.get('scan_path', '').strip()
    extract_text_flag = request.form.get('extract_text', 'on') == 'on'
    dry_run = request.form.get('dry_run', '') == 'on'

    if not scan_path:
        flash('Please enter a folder path to scan.', 'danger')
        return redirect(url_for('admin.scan'))

    if not os.path.isdir(scan_path):
        flash(f'Directory not found: {scan_path}', 'danger')
        return redirect(url_for('admin.scan'))

    from app.services.project_scanner import scan_directory
    result = scan_directory(scan_path, extract_text_flag=extract_text_flag, dry_run=dry_run)

    if result.get('error'):
        flash(f'Scan failed: {result["error"]}', 'danger')
    else:
        msg = (f'Scan complete: {result["projects_found"]} projects found, '
               f'{result["projects_created"]} created, '
               f'{result["documents_created"]} documents added.')
        if dry_run:
            msg += ' (Dry run — no changes saved)'
        flash(msg, 'success')

    return render_template('admin/scan.html',
                           historical_path=scan_path,
                           scan_result=result)


@admin_bp.route('/metadata/<int:project_id>', methods=['POST'])
@login_required
def extract_metadata(project_id):
    """Extract metadata for a project using LLM."""
    from app.services.metadata_extractor import extract_project_metadata
    result = extract_project_metadata(project_id)

    if 'error' in result:
        flash(f'Metadata extraction failed: {result["error"]}', 'danger')
    else:
        materials = result.get('materials', [])
        standards = result.get('standards', [])
        flash(f'Metadata extracted: {len(materials)} materials, {len(standards)} standards.', 'success')

    return redirect(url_for('admin.indexing'))


@admin_bp.route('/api/vector-stats')
@login_required
def api_vector_stats():
    """JSON endpoint for vector store statistics."""
    return jsonify(vector_store.get_collection_stats())
