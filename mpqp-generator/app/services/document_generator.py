"""Document generation service.

Orchestrates the full generation pipeline:
1. Gather reference project content (from selected projects)
2. Build generation prompt with requirements + references + template structure
3. Call LLM to generate document content section by section
4. Return structured content for template filling
"""
import logging
from datetime import datetime

from flask import current_app

from app import db
from app.models.generation import GenerationJob, DocumentVersion
from app.models.project import Project
from app.models.document import Document
from app.models.template import Template
from app.services.llm_client import generate

logger = logging.getLogger(__name__)

GENERATION_SYSTEM = """You are an expert in creating Manufacturing Procedure Quality Plans (MPQP),
Manufacturing Procedure Specifications (MPS), and Inspection and Test Plans (ITP)
for offshore oil & gas components manufactured by Subseatec.

You produce detailed, professional technical documents that:
- Follow the template structure exactly
- Reference correct standards (API, ASME, DNV, NORSOK)
- Include proper material specifications and testing requirements
- Maintain consistent technical writing style
- Are ready for engineering review with minimal edits needed"""

SECTION_PROMPT = """Generate the content for the following section of a {doc_type} document.

PROJECT: {project_name}
CUSTOMER: {customer_name}
PRODUCT TYPE: {product_type}

REQUIREMENTS FROM NEW PROJECT:
{requirements}

REFERENCE DOCUMENT SECTION (from similar project):
{reference_section}

SECTION TO GENERATE:
Title: {section_title}
Description: {section_description}

Write the complete content for this section. Be specific and detailed.
Use the reference as a guide for format and level of detail, but update all
references to match the new project requirements. Include:
- Correct standard references
- Updated material specifications
- Proper inspection and test points
- Accurate process parameters

Output ONLY the section content, no headers or metadata."""

FULL_DOC_PROMPT = """Generate a complete {doc_type} document for the following project.

PROJECT: {project_name}
CUSTOMER: {customer_name}
PRODUCT TYPE: {product_type}

NEW PROJECT REQUIREMENTS:
{requirements}

REFERENCE {doc_type} (from similar project "{ref_project}"):
{reference_text}

Generate the complete document following this structure:
{template_structure}

For each section:
1. Use the reference document as a guide for format and detail level
2. Update all references to match the new project requirements
3. Include correct standard references from the new specification
4. Update material specifications as per new requirements
5. Adjust inspection and test points as needed

Maintain professional technical writing style. Output the complete document
content section by section, using markdown headers (## Section Title) to
separate sections."""


def generate_document(job_id):
    """Run the full document generation pipeline for a job.

    Returns dict with generation result or error.
    """
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return {'error': f'Job {job_id} not found'}

    job.status = 'generating'
    job.generation_log = f'[{datetime.utcnow().isoformat()}] Generation started\n'
    db.session.commit()

    try:
        # Step 1: Gather inputs
        requirements = _format_requirements(job)
        reference_text = _gather_reference_text(job)
        template_structure = _get_template_structure(job)
        doc_type = _get_doc_type(job)

        _log(job, f'Inputs gathered: {len(requirements)} chars requirements, '
                   f'{len(reference_text)} chars reference text')

        # Step 2: Generate document content via LLM
        prompt = FULL_DOC_PROMPT.format(
            doc_type=doc_type,
            project_name=job.new_project_name or 'New Project',
            customer_name=job.customer.name if job.customer else 'Unknown',
            product_type=job.product_type or 'Unknown',
            requirements=requirements,
            ref_project=_get_ref_project_name(job),
            reference_text=reference_text[:6000],  # Fit within context window
            template_structure=template_structure,
        )

        _log(job, 'Calling LLM for document generation...')
        db.session.commit()

        content = generate(prompt, system=GENERATION_SYSTEM, max_tokens=4096)

        if not content:
            _log(job, 'ERROR: LLM generation returned empty result')
            job.status = 'failed'
            db.session.commit()
            return {'error': 'LLM generation failed — is Ollama running?'}

        _log(job, f'LLM generated {len(content)} characters')

        # Step 3: Save generated content
        result = _save_generated_content(job, content, doc_type)

        job.status = 'completed'
        _log(job, 'Generation completed successfully')
        db.session.commit()

        return result

    except Exception as e:
        logger.error(f'Generation failed for job {job_id}: {e}')
        _log(job, f'ERROR: {str(e)}')
        job.status = 'failed'
        db.session.commit()
        return {'error': str(e)}


def generate_section(job_id, section_title, section_description=''):
    """Generate a single section (useful for incremental generation or refinement)."""
    job = db.session.get(GenerationJob, job_id)
    if not job:
        return {'error': f'Job {job_id} not found'}

    requirements = _format_requirements(job)
    reference_section = _get_reference_section(job, section_title)
    doc_type = _get_doc_type(job)

    prompt = SECTION_PROMPT.format(
        doc_type=doc_type,
        project_name=job.new_project_name or 'New Project',
        customer_name=job.customer.name if job.customer else 'Unknown',
        product_type=job.product_type or 'Unknown',
        requirements=requirements,
        reference_section=reference_section[:3000],
        section_title=section_title,
        section_description=section_description,
    )

    content = generate(prompt, system=GENERATION_SYSTEM, max_tokens=2048)
    if not content:
        return {'error': 'LLM generation failed'}

    return {'section': section_title, 'content': content}


def _format_requirements(job):
    """Format extracted requirements into a readable string for the prompt."""
    reqs = job.extracted_requirements or {}
    if not reqs or reqs.get('error'):
        return 'No specific requirements extracted.'

    lines = []
    if reqs.get('customer_name'):
        lines.append(f'Customer: {reqs["customer_name"]}')
    if reqs.get('product_description'):
        lines.append(f'Product: {reqs["product_description"]}')
    if reqs.get('materials'):
        lines.append(f'Materials: {", ".join(reqs["materials"])}')
    if reqs.get('standards'):
        lines.append(f'Standards: {", ".join(reqs["standards"])}')
    if reqs.get('testing_requirements'):
        lines.append(f'Testing: {", ".join(reqs["testing_requirements"])}')
    if reqs.get('welding_processes'):
        lines.append(f'Welding: {", ".join(reqs["welding_processes"])}')
    if reqs.get('heat_treatment'):
        lines.append(f'Heat Treatment: {reqs["heat_treatment"]}')
    if reqs.get('special_requirements'):
        lines.append(f'Special Requirements: {reqs["special_requirements"]}')

    return '\n'.join(lines) if lines else 'No specific requirements extracted.'


def _gather_reference_text(job):
    """Gather text from selected reference projects' output documents (MPQP/MPS/ITP)."""
    selected_ids = job.selected_references or []
    if not selected_ids:
        return 'No reference documents available.'

    texts = []
    for pid in selected_ids[:3]:  # Limit to 3 reference projects
        docs = Document.query.filter_by(project_id=pid).filter(
            Document.document_type.in_(['MPQP', 'MPS', 'ITP'])
        ).all()
        for doc in docs:
            if doc.extracted_text:
                texts.append(
                    f'--- Reference: {doc.file_name} (Project {doc.project.project_number if doc.project else pid}) ---\n'
                    + doc.extracted_text[:4000]
                )

    if not texts:
        # Fall back to any document with text
        for pid in selected_ids[:3]:
            docs = Document.query.filter_by(project_id=pid).filter(
                Document.extracted_text.isnot(None)
            ).limit(2).all()
            for doc in docs:
                texts.append(
                    f'--- Reference: {doc.file_name} ---\n' + doc.extracted_text[:3000]
                )

    return '\n\n'.join(texts) if texts else 'No reference documents available.'


def _get_template_structure(job):
    """Get template structure definition."""
    if job.template and job.template.structure:
        sections = job.template.structure.get('sections', [])
        return '\n'.join(f'- {s.get("title", s)}' for s in sections)

    # Default MPQP structure
    doc_type = _get_doc_type(job)
    if doc_type == 'ITP':
        return DEFAULT_ITP_STRUCTURE
    elif doc_type == 'MPS':
        return DEFAULT_MPS_STRUCTURE
    return DEFAULT_MPQP_STRUCTURE


def _get_doc_type(job):
    """Determine document type for the job."""
    if job.template:
        return job.template.document_type
    return 'MPQP'


def _get_ref_project_name(job):
    """Get the name of the primary reference project."""
    selected_ids = job.selected_references or []
    if selected_ids:
        project = db.session.get(Project, selected_ids[0])
        if project:
            return f'{project.project_number} - {project.project_name or ""}'
    return 'None'


def _get_reference_section(job, section_title):
    """Find matching section text from reference documents."""
    selected_ids = job.selected_references or []
    for pid in selected_ids[:3]:
        docs = Document.query.filter_by(project_id=pid).filter(
            Document.document_type.in_(['MPQP', 'MPS', 'ITP'])
        ).all()
        for doc in docs:
            if doc.extracted_text and section_title.lower() in doc.extracted_text.lower():
                # Extract surrounding context
                idx = doc.extracted_text.lower().index(section_title.lower())
                start = max(0, idx - 200)
                end = min(len(doc.extracted_text), idx + 2000)
                return doc.extracted_text[start:end]
    return 'No matching reference section found.'


def _save_generated_content(job, content, doc_type):
    """Save the generated content as a text file and create a version record."""
    import os
    generated_dir = current_app.config['GENERATED_FOLDER']
    os.makedirs(generated_dir, exist_ok=True)

    # Save as markdown (can be converted to docx later)
    filename = f'{doc_type}_{job.new_project_name or "document"}_{job.id}_v{job.current_version}.md'
    filename = ''.join(c if c.isalnum() or c in '.-_' else '_' for c in filename)
    filepath = os.path.join(generated_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f'# {doc_type} - {job.new_project_name}\n\n')
        f.write(f'**Customer:** {job.customer.name if job.customer else "N/A"}\n')
        f.write(f'**Product Type:** {job.product_type or "N/A"}\n')
        f.write(f'**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}\n\n')
        f.write('---\n\n')
        f.write(content)

    job.generated_document_path = filepath

    # Create version record
    version = DocumentVersion(
        generation_job_id=job.id,
        version_number=job.current_version,
        file_path=filepath,
        changes_description='Initial generation',
    )
    db.session.add(version)

    return {
        'filepath': filepath,
        'filename': filename,
        'content_length': len(content),
        'version': job.current_version,
    }


def _log(job, message):
    """Append to generation log."""
    timestamp = datetime.utcnow().strftime('%H:%M:%S')
    job.generation_log = (job.generation_log or '') + f'[{timestamp}] {message}\n'


# Default document structures

DEFAULT_MPQP_STRUCTURE = """1. Scope and Purpose
2. Reference Documents and Standards
3. Material Specifications
4. Manufacturing Process Flow
5. Welding Procedures
6. Heat Treatment Requirements
7. Non-Destructive Testing (NDT)
8. Mechanical Testing
9. Dimensional Inspection
10. Surface Treatment and Coating
11. Marking and Traceability
12. Packaging and Shipping
13. Quality Records and Documentation
14. Hold and Witness Points"""

DEFAULT_MPS_STRUCTURE = """1. Scope
2. Reference Documents
3. Material Requirements
4. Manufacturing Sequence
5. Welding Requirements
6. Heat Treatment
7. Inspection Requirements
8. Testing Requirements
9. Acceptance Criteria
10. Documentation Requirements"""

DEFAULT_ITP_STRUCTURE = """1. General Information
2. Applicable Standards and Specifications
3. Material Receiving Inspection
4. In-Process Inspection Points
5. Welding Inspection
6. NDT Requirements
7. Mechanical Testing
8. Dimensional Verification
9. Final Inspection
10. Documentation and Certification
11. Hold / Witness / Review Points Matrix"""
