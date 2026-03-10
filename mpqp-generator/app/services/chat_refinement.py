"""Chat refinement service for iterative document improvement.

Manages a conversation between the user and the LLM to refine
generated documents section by section or as a whole.
"""
import os
import logging
from datetime import datetime

from flask import current_app

from app import db
from app.models.generation import GenerationJob, DocumentVersion
from app.services.llm_client import generate

logger = logging.getLogger(__name__)

REFINEMENT_SYSTEM = """You are an expert technical writer specializing in MPQP, MPS, and ITP documents
for offshore oil & gas manufacturing. You are helping refine a generated document.

Rules:
- When asked to modify a section, output ONLY the updated section content
- Keep the same markdown format (## headers, bullet points, numbered lists)
- Maintain technical accuracy — correct standards, material specs, and processes
- Be concise in explanations but thorough in document content
- If asked a question about the document, answer briefly then suggest improvements"""

REFINEMENT_PROMPT = """Here is the current document:

{document_content}

User request: {user_message}

Respond with the updated content. If the request targets a specific section,
output only that section with its ## header. If it's a general question,
answer briefly."""


def send_message(job_id, user_message):
    """Send a chat message and get LLM response for document refinement.

    Args:
        job_id: GenerationJob ID
        user_message: The user's refinement request

    Returns:
        Dict with 'response' text, or 'error' string.
    """
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return {'error': f'Job {job_id} not found'}

    # Read current document content
    doc_content = _read_document(job)
    if not doc_content:
        return {'error': 'No generated document to refine'}

    # Build conversation context from history
    history = job.chat_history or []

    # Build the prompt with document + recent history for context
    context_messages = _format_history(history[-6:])  # Last 3 exchanges
    prompt = REFINEMENT_PROMPT.format(
        document_content=doc_content[:4000],
        user_message=user_message,
    )
    if context_messages:
        prompt = f"Previous conversation:\n{context_messages}\n\n{prompt}"

    # Call LLM
    response = generate(prompt, system=REFINEMENT_SYSTEM, max_tokens=2048)
    if not response:
        return {'error': 'LLM generation failed — is Ollama running?'}

    # Save to chat history
    timestamp = datetime.utcnow().isoformat()
    history.append({'role': 'user', 'content': user_message, 'timestamp': timestamp})
    history.append({'role': 'assistant', 'content': response, 'timestamp': timestamp})
    job.chat_history = history
    db.session.commit()

    return {'response': response}


def apply_revision(job_id, revised_content, description='Chat refinement'):
    """Apply a revised version of the document.

    Creates a new version with the updated content.

    Args:
        job_id: GenerationJob ID
        revised_content: The full updated document content
        description: Change description for version history

    Returns:
        Dict with version info, or 'error' string.
    """
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return {'error': f'Job {job_id} not found'}

    if not job.generated_document_path:
        return {'error': 'No generated document to revise'}

    # Increment version
    new_version = (job.current_version or 1) + 1

    # Save new version file
    generated_dir = current_app.config['GENERATED_FOLDER']
    os.makedirs(generated_dir, exist_ok=True)

    doc_type = 'MPQP'
    if job.template:
        doc_type = job.template.document_type

    filename = f'{doc_type}_{job.new_project_name or "document"}_{job.id}_v{new_version}.md'
    filename = ''.join(c if c.isalnum() or c in '.-_' else '_' for c in filename)
    filepath = os.path.join(generated_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f'# {doc_type} - {job.new_project_name}\n\n')
        f.write(f'**Version:** {new_version}\n')
        f.write(f'**Updated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}\n\n')
        f.write('---\n\n')
        f.write(revised_content)

    # Update job
    job.generated_document_path = filepath
    job.current_version = new_version

    # Create version record
    version = DocumentVersion(
        generation_job_id=job.id,
        version_number=new_version,
        file_path=filepath,
        changes_description=description,
    )
    db.session.add(version)
    db.session.commit()

    logger.info(f'Revision applied: job {job_id} v{new_version}')
    return {
        'version': new_version,
        'filepath': filepath,
        'description': description,
    }


def apply_section_update(job_id, section_title, new_section_content):
    """Replace a specific section in the document with updated content.

    Args:
        job_id: GenerationJob ID
        section_title: The ## header title to replace
        new_section_content: New content for that section (with or without header)

    Returns:
        Dict with version info, or 'error' string.
    """
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return {'error': f'Job {job_id} not found'}

    doc_content = _read_document(job)
    if not doc_content:
        return {'error': 'No generated document to update'}

    # Find and replace the section
    updated = _replace_section(doc_content, section_title, new_section_content)
    if updated == doc_content:
        return {'error': f'Section "{section_title}" not found in document'}

    return apply_revision(job_id, updated, description=f'Updated section: {section_title}')


def get_chat_history(job_id):
    """Get the chat history for a job.

    Returns:
        List of message dicts, or empty list.
    """
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return []
    return job.chat_history or []


def clear_chat_history(job_id):
    """Clear chat history for a job."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return False
    job.chat_history = []
    db.session.commit()
    return True


def _read_document(job):
    """Read the current generated document content."""
    if not job.generated_document_path or not os.path.exists(job.generated_document_path):
        return None
    with open(job.generated_document_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Strip metadata header
    if '---' in content:
        content = content.split('---', 1)[1].strip()
    return content


def _format_history(messages):
    """Format recent chat messages for context."""
    lines = []
    for msg in messages:
        role = 'User' if msg['role'] == 'user' else 'Assistant'
        lines.append(f'{role}: {msg["content"][:500]}')
    return '\n'.join(lines)


def _replace_section(content, section_title, new_content):
    """Replace a section in markdown content by its header title."""
    import re

    # Ensure new content has the header
    if not new_content.strip().startswith('#'):
        new_content = f'## {section_title}\n{new_content}'

    # Find the section boundaries
    pattern = rf'(^|\n)(##\s+{re.escape(section_title)}\s*\n)'
    match = re.search(pattern, content)
    if not match:
        return content

    start = match.start(2)
    # Find next section header or end of content
    next_header = re.search(r'\n##\s+', content[match.end():])
    if next_header:
        end = match.end() + next_header.start()
    else:
        end = len(content)

    return content[:start] + new_content.strip() + '\n\n' + content[end:].lstrip()
