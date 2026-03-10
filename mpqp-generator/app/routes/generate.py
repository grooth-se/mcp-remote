import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app, jsonify
from flask_login import login_required

from app import db, csrf
from app.models.generation import GenerationJob
from app.models.project import Project

generate_bp = Blueprint('generate', __name__)


@generate_bp.route('/status/<int:job_id>')
@login_required
def status(job_id):
    """Show generation job status and details."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    return render_template('generate/status.html', job=job)


@generate_bp.route('/jobs')
@login_required
def job_list():
    """List all generation jobs."""
    jobs = GenerationJob.query.order_by(GenerationJob.created_at.desc()).all()
    return render_template('generate/job_list.html', jobs=jobs)


@generate_bp.route('/find-similar/<int:job_id>', methods=['POST'])
@login_required
def find_similar(job_id):
    """Run similarity matching for a generation job."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    # Optionally extract requirements first via LLM
    if not job.extracted_requirements:
        _extract_requirements(job)

    job.status = 'matching'
    db.session.commit()

    from app.services.similarity_engine import find_similar_for_job
    similar = find_similar_for_job(job)

    job.similar_projects = similar
    job.status = 'review'
    db.session.commit()

    if similar:
        flash(f'Found {len(similar)} similar projects. Review and select references below.', 'success')
    else:
        flash('No similar projects found. You can still proceed with generation.', 'warning')

    return redirect(url_for('generate.review', job_id=job.id))


@generate_bp.route('/review/<int:job_id>')
@login_required
def review(job_id):
    """Similarity review page — user selects reference projects."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    similar = job.similar_projects or []

    # Enrich with document counts
    for item in similar:
        project = db.session.get(Project, item.get('project_id'))
        if project:
            item['document_count'] = project.documents.count()
            # Find MPQP/MPS/ITP documents specifically
            from app.models.document import Document
            output_docs = Document.query.filter_by(project_id=project.id).filter(
                Document.document_type.in_(['MPQP', 'MPS', 'ITP'])
            ).all()
            item['output_documents'] = [
                {'id': d.id, 'name': d.file_name, 'type': d.document_type}
                for d in output_docs
            ]

    return render_template('generate/review.html', job=job, similar=similar)


@generate_bp.route('/select-references/<int:job_id>', methods=['POST'])
@login_required
def select_references(job_id):
    """Save user's selected reference projects."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    selected_ids = request.form.getlist('reference_projects', type=int)
    job.selected_references = selected_ids

    if selected_ids:
        job.status = 'review'  # Ready for generation
        flash(f'{len(selected_ids)} reference project(s) selected.', 'success')
    else:
        flash('No references selected. You can still generate, but quality may vary.', 'warning')

    db.session.commit()
    return redirect(url_for('generate.status', job_id=job.id))


@generate_bp.route('/extract-requirements/<int:job_id>', methods=['POST'])
@login_required
def extract_requirements(job_id):
    """Extract requirements from uploaded documents using LLM."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    _extract_requirements(job)
    return redirect(url_for('generate.status', job_id=job.id))


@generate_bp.route('/generate-document/<int:job_id>', methods=['POST'])
@login_required
def generate_doc(job_id):
    """Trigger LLM document generation for a job."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    from app.services.document_generator import generate_document as run_generation
    result = run_generation(job_id)

    if result.get('error'):
        flash(f'Generation failed: {result["error"]}', 'danger')
    else:
        flash(f'Document generated successfully ({result["content_length"]} chars, v{result["version"]}).', 'success')

    return redirect(url_for('generate.status', job_id=job.id))


@generate_bp.route('/download/<int:job_id>')
@login_required
def download(job_id):
    """Download the generated markdown document."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    if not job.generated_document_path or not os.path.exists(job.generated_document_path):
        flash('No generated document available for download.', 'warning')
        return redirect(url_for('generate.status', job_id=job.id))

    return send_file(
        job.generated_document_path,
        as_attachment=True,
        download_name=os.path.basename(job.generated_document_path),
    )


@generate_bp.route('/export-word/<int:job_id>', methods=['POST'])
@login_required
def export_word(job_id):
    """Export the generated document as a Word (.docx) file."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    if not job.generated_document_path or not os.path.exists(job.generated_document_path):
        flash('No generated document available for export.', 'warning')
        return redirect(url_for('generate.status', job_id=job.id))

    with open(job.generated_document_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip the metadata header (everything before the first ---)
    if '---' in content:
        content = content.split('---', 1)[1].strip()

    from app.services.template_filler import create_word_document
    metadata = {
        'project_name': job.new_project_name or 'Document',
        'customer': job.customer.name if job.customer else 'N/A',
        'product_type': job.product_type or 'N/A',
        'doc_type': 'MPQP',
    }
    if job.template:
        metadata['doc_type'] = job.template.document_type

    docx_path = create_word_document(content, metadata)
    if not docx_path:
        flash('Word export failed. python-docx may not be installed.', 'danger')
        return redirect(url_for('generate.status', job_id=job.id))

    return send_file(
        docx_path,
        as_attachment=True,
        download_name=os.path.basename(docx_path),
    )


@generate_bp.route('/chat/<int:job_id>')
@login_required
def chat(job_id):
    """Chat refinement page for a generated document."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('main.index'))

    if not job.generated_document_path or not os.path.exists(job.generated_document_path):
        flash('Generate a document first before refining.', 'warning')
        return redirect(url_for('generate.status', job_id=job.id))

    # Read current document
    from app.services.chat_refinement import _read_document
    doc_content = _read_document(job)
    history = job.chat_history or []
    versions = job.versions.all()

    return render_template('generate/chat.html',
                           job=job, doc_content=doc_content,
                           history=history, versions=versions)


@generate_bp.route('/chat/<int:job_id>/send', methods=['POST'])
@csrf.exempt
@login_required
def chat_send(job_id):
    """Send a chat message for document refinement (AJAX endpoint)."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    data = request.get_json(silent=True)
    if not data or not data.get('message', '').strip():
        return jsonify({'error': 'Message is required'}), 400

    from app.services.chat_refinement import send_message
    result = send_message(job_id, data['message'].strip())

    if result.get('error'):
        return jsonify({'error': result['error']}), 500

    return jsonify({'response': result['response']})


@generate_bp.route('/chat/<int:job_id>/apply', methods=['POST'])
@csrf.exempt
@login_required
def chat_apply(job_id):
    """Apply revised content as a new document version (AJAX endpoint)."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    data = request.get_json(silent=True)
    if not data or not data.get('content', '').strip():
        return jsonify({'error': 'Content is required'}), 400

    description = data.get('description', 'Chat refinement')

    from app.services.chat_refinement import apply_revision
    result = apply_revision(job_id, data['content'].strip(), description)

    if result.get('error'):
        return jsonify({'error': result['error']}), 500

    return jsonify(result)


@generate_bp.route('/chat/<int:job_id>/clear', methods=['POST'])
@csrf.exempt
@login_required
def chat_clear(job_id):
    """Clear chat history (AJAX endpoint)."""
    from app.services.chat_refinement import clear_chat_history
    clear_chat_history(job_id)
    return jsonify({'status': 'ok'})


def _extract_requirements(job):
    """Internal helper to extract requirements via LLM."""
    from app.services.metadata_extractor import extract_metadata_from_text
    from app.services.document_processor import extract_text

    combined_text = ''
    for doc_info in (job.uploaded_documents or []):
        filepath = doc_info.get('filepath', '')
        if filepath:
            try:
                result = extract_text(filepath)
                combined_text += result.get('text', '')[:5000] + '\n\n'
            except Exception:
                pass

    if not combined_text.strip():
        job.extracted_requirements = {'error': 'No text could be extracted from uploaded documents'}
        db.session.commit()
        return

    job.status = 'analyzing'
    db.session.commit()

    metadata = extract_metadata_from_text(combined_text, job.new_project_name or 'new project')
    if metadata:
        job.extracted_requirements = metadata
        # Also update job materials/standards if extracted
        if metadata.get('materials') and not job.product_type:
            pass  # Keep user's selection
        flash('Requirements extracted from uploaded documents.', 'success')
    else:
        job.extracted_requirements = {'error': 'LLM extraction failed — is Ollama running?'}
        flash('Requirement extraction failed. Ollama may be offline.', 'warning')

    db.session.commit()
