import os
import threading
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

# Background scan state (single-user system, simple dict is fine)
_scan_state = {
    'running': False,
    'progress': '',
    'projects_processed': 0,
    'projects_total': 0,
    'result': None,
}

# Background indexing state
_index_state = {
    'running': False,
    'progress': '',
    'docs_processed': 0,
    'docs_total': 0,
    'docs_indexed': 0,
    'docs_failed': 0,
    'errors': [],
    'result': None,
}


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
    """Start a project folder scan in the background."""
    scan_path = request.form.get('scan_path', '').strip()
    extract_text_flag = request.form.get('extract_text', 'on') == 'on'
    dry_run = request.form.get('dry_run', '') == 'on'

    if not scan_path:
        flash('Please enter a folder path to scan.', 'danger')
        return redirect(url_for('admin.scan'))

    if not os.path.isdir(scan_path):
        flash(f'Directory not found: {scan_path}', 'danger')
        return redirect(url_for('admin.scan'))

    if _scan_state['running']:
        flash('A scan is already running. Please wait for it to finish.', 'warning')
        return redirect(url_for('admin.scan_progress'))

    # Reset state and start background scan
    _scan_state.update({
        'running': True,
        'progress': 'Starting scan...',
        'projects_processed': 0,
        'projects_total': 0,
        'result': None,
    })

    app = current_app._get_current_object()

    def _run_scan():
        with app.app_context():
            from app.services.project_scanner import scan_directory
            try:
                result = scan_directory(
                    scan_path,
                    extract_text_flag=extract_text_flag,
                    dry_run=dry_run,
                    progress_callback=_update_scan_progress,
                )
                _scan_state['result'] = result
            except Exception as e:
                _scan_state['result'] = {'error': str(e)}
            finally:
                _scan_state['running'] = False
                _scan_state['progress'] = 'Complete'

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()

    return redirect(url_for('admin.scan_progress'))


def _update_scan_progress(msg, processed, total):
    """Callback for project_scanner to report progress."""
    _scan_state['progress'] = msg
    _scan_state['projects_processed'] = processed
    _scan_state['projects_total'] = total


@admin_bp.route('/scan/progress')
@login_required
def scan_progress():
    """Page that shows live scan progress."""
    # If scan is done and we have results, show the results page
    if not _scan_state['running'] and _scan_state['result']:
        result = _scan_state['result']
        scan_path = result.get('root_path', '')
        return render_template('admin/scan.html',
                               historical_path=scan_path,
                               scan_result=result)
    return render_template('admin/scan_progress.html')


@admin_bp.route('/scan/status')
@login_required
def scan_status():
    """JSON endpoint for scan progress polling."""
    return jsonify({
        'running': _scan_state['running'],
        'progress': _scan_state['progress'],
        'projects_processed': _scan_state['projects_processed'],
        'projects_total': _scan_state['projects_total'],
        'done': not _scan_state['running'] and _scan_state['result'] is not None,
    })


# --- Batch indexing ---

KEY_DOC_TYPES = ['MPQP', 'MPS', 'ITP', 'SPEC']


@admin_bp.route('/indexing/batch', methods=['POST'])
@login_required
def batch_index():
    """Start batch indexing of key document types in background."""
    if _index_state['running']:
        flash('Batch indexing is already running.', 'warning')
        return redirect(url_for('admin.batch_index_progress'))

    doc_types = request.form.getlist('doc_types') or KEY_DOC_TYPES

    # Reset state
    _index_state.update({
        'running': True,
        'progress': 'Starting batch indexing...',
        'docs_processed': 0,
        'docs_total': 0,
        'docs_indexed': 0,
        'docs_failed': 0,
        'errors': [],
        'result': None,
    })

    app = current_app._get_current_object()

    def _run_batch_index():
        import gc
        with app.app_context():
            from app.services.embedder import index_document as do_index
            from app.services.document_processor import extract_text

            # Query documents of key types that haven't been indexed yet
            docs = Document.query.filter(
                Document.document_type.in_(doc_types),
                Document.indexed_at.is_(None),
            ).order_by(Document.id).all()

            doc_ids = [d.id for d in docs]
            _index_state['docs_total'] = len(doc_ids)
            _index_state['progress'] = f'Found {len(doc_ids)} documents to index'

            for i, doc_id in enumerate(doc_ids):
                try:
                    doc = db.session.get(Document, doc_id)
                    if not doc:
                        continue

                    _index_state['progress'] = f'Indexing: {doc.file_name}'
                    _index_state['docs_processed'] = i

                    # Step 1: Extract text if needed
                    if not doc.extracted_text:
                        try:
                            file_size = doc.file_size or 0
                            if file_size > 50 * 1024 * 1024:
                                _index_state['docs_failed'] += 1
                                _index_state['errors'].append(f'{doc.file_name}: too large')
                                continue
                            extraction = extract_text(doc.file_path)
                            if extraction.get('error'):
                                _index_state['docs_failed'] += 1
                                continue
                            doc.extracted_text = extraction.get('text', '')
                            doc.page_count = extraction.get('page_count', 0)
                            db.session.commit()
                        except Exception as e:
                            _index_state['docs_failed'] += 1
                            db.session.rollback()
                            continue

                    if not doc.extracted_text or not doc.extracted_text.strip():
                        _index_state['docs_failed'] += 1
                        continue

                    # Step 2: Index (chunk + embed + store)
                    result = do_index(doc_id)
                    if 'error' in result:
                        _index_state['docs_failed'] += 1
                        if len(_index_state['errors']) < 50:
                            _index_state['errors'].append(
                                f'{doc.file_name}: {result["error"][:80]}')
                    else:
                        _index_state['docs_indexed'] += 1

                except Exception as e:
                    _index_state['docs_failed'] += 1
                    try:
                        db.session.rollback()
                    except Exception:
                        pass

                # Free memory periodically
                if i % 20 == 0:
                    gc.collect()

            _index_state['docs_processed'] = len(doc_ids)
            _index_state['result'] = {
                'total': len(doc_ids),
                'indexed': _index_state['docs_indexed'],
                'failed': _index_state['docs_failed'],
                'errors': _index_state['errors'],
                'doc_types': doc_types,
            }
            _index_state['running'] = False
            _index_state['progress'] = 'Complete'

    thread = threading.Thread(target=_run_batch_index, daemon=True)
    thread.start()

    return redirect(url_for('admin.batch_index_progress'))


@admin_bp.route('/indexing/batch/progress')
@login_required
def batch_index_progress():
    """Batch indexing progress page."""
    if not _index_state['running'] and _index_state['result']:
        return render_template('admin/indexing.html',
                               batch_result=_index_state['result'],
                               projects=Project.query.order_by(Project.project_number).all(),
                               documents=Document.query.order_by(Document.created_at.desc()).all(),
                               vector_stats=vector_store.get_collection_stats(),
                               ollama_status=check_ollama_status())
    return render_template('admin/index_progress.html')


@admin_bp.route('/indexing/batch/status')
@login_required
def batch_index_status():
    """JSON endpoint for batch indexing progress."""
    return jsonify({
        'running': _index_state['running'],
        'progress': _index_state['progress'],
        'docs_processed': _index_state['docs_processed'],
        'docs_total': _index_state['docs_total'],
        'docs_indexed': _index_state['docs_indexed'],
        'docs_failed': _index_state['docs_failed'],
        'done': not _index_state['running'] and _index_state['result'] is not None,
    })


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
