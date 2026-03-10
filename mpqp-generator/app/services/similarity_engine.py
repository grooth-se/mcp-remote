"""Multi-factor similarity engine for finding reference projects.

Combines metadata-based scoring (customer, product type, materials, standards)
with vector similarity search for a hybrid ranking approach.

Weighting factors (from context spec):
  - Customer match:  40%
  - Product type:    30%
  - Material overlap: 15%
  - Standard overlap: 15%
"""
import logging
from flask import current_app

from app import db
from app.models.project import Project
from app.services import vector_store
from app.services.llm_client import get_embeddings

logger = logging.getLogger(__name__)

# Weight factors
W_CUSTOMER = 0.40
W_PRODUCT = 0.30
W_MATERIAL = 0.15
W_STANDARD = 0.15

# Product categories for partial matching
CATEGORY_MAP = {
    'TTR': 'Riser', 'SCR': 'Riser', 'CWOR': 'Riser', 'SLS': 'Riser',
    'BODY': 'Component', 'VALVE': 'Component', 'FLANGE': 'Component',
}


def find_similar_projects(customer_id=None, product_type=None, materials=None,
                          standards=None, query_text=None, max_results=None):
    """Find similar historical projects using multi-factor scoring.

    Args:
        customer_id: Customer ID for the new project
        product_type: Product type code (TTR, SCR, etc.)
        materials: List of material grades
        standards: List of standards referenced
        query_text: Combined text from uploaded documents (for vector search)
        max_results: Maximum number of results

    Returns:
        List of dicts sorted by combined score, each containing:
        - project: Project object
        - score: Combined similarity score (0-1)
        - metadata_score: Score from metadata matching
        - vector_score: Score from vector similarity
        - breakdown: Dict with per-factor scores
    """
    max_results = max_results or current_app.config.get('MAX_SIMILAR_PROJECTS', 10)
    materials = materials or []
    standards = standards or []

    # Get all historical projects
    projects = Project.query.filter(Project.indexed_at.isnot(None)).all()
    if not projects:
        # Fall back to all projects if none are indexed
        projects = Project.query.all()

    if not projects:
        return []

    # Step 1: Compute metadata scores for all projects
    scored = []
    for project in projects:
        meta_score, breakdown = _compute_metadata_score(
            project, customer_id, product_type, materials, standards
        )
        scored.append({
            'project': project,
            'metadata_score': meta_score,
            'breakdown': breakdown,
        })

    # Step 2: Optionally add vector similarity scores
    if query_text:
        vector_scores = _compute_vector_scores(query_text, projects)
        for item in scored:
            pid = item['project'].id
            item['vector_score'] = vector_scores.get(pid, 0.0)
    else:
        for item in scored:
            item['vector_score'] = 0.0

    # Step 3: Combine scores (70% metadata, 30% vector when available)
    for item in scored:
        if item['vector_score'] > 0:
            item['score'] = 0.7 * item['metadata_score'] + 0.3 * item['vector_score']
        else:
            item['score'] = item['metadata_score']

    # Sort by combined score descending
    scored.sort(key=lambda x: x['score'], reverse=True)

    # Return top N
    results = scored[:max_results]

    logger.info(f'Found {len(results)} similar projects '
                f'(customer_id={customer_id}, product_type={product_type})')
    return results


def _compute_metadata_score(project, customer_id, product_type, materials, standards):
    """Compute weighted metadata similarity score for a single project."""
    breakdown = {
        'customer': 0.0,
        'product': 0.0,
        'materials': 0.0,
        'standards': 0.0,
    }

    # Customer match (exact)
    if customer_id and project.customer_id:
        if project.customer_id == customer_id:
            breakdown['customer'] = 1.0

    # Product type match (exact or same category)
    if product_type and project.product_type:
        if project.product_type == product_type:
            breakdown['product'] = 1.0
        elif CATEGORY_MAP.get(project.product_type) == CATEGORY_MAP.get(product_type):
            breakdown['product'] = 0.5  # Same category but different specific type

    # Material overlap
    if materials and project.materials:
        proj_materials = set(m.upper().strip() for m in (project.materials or []))
        new_materials = set(m.upper().strip() for m in materials)
        if new_materials:
            overlap = len(proj_materials & new_materials)
            breakdown['materials'] = overlap / len(new_materials)

    # Standard overlap
    if standards and project.standards:
        proj_standards = set(s.upper().strip() for s in (project.standards or []))
        new_standards = set(s.upper().strip() for s in standards)
        if new_standards:
            overlap = len(proj_standards & new_standards)
            breakdown['standards'] = overlap / len(new_standards)

    score = (
        W_CUSTOMER * breakdown['customer'] +
        W_PRODUCT * breakdown['product'] +
        W_MATERIAL * breakdown['materials'] +
        W_STANDARD * breakdown['standards']
    )

    return score, breakdown


def _compute_vector_scores(query_text, projects):
    """Compute vector similarity scores using ChromaDB.

    Returns dict of {project_id: score}.
    """
    scores = {}

    # Truncate query text for embedding
    text_for_embedding = query_text[:2000]

    try:
        embedding = get_embeddings(text_for_embedding)
        if embedding is None:
            return scores

        # Search for similar chunks across all projects
        results = vector_store.search(embedding, n_results=50)

        # Aggregate scores by project (take max similarity per project)
        for i, metadata in enumerate(results.get('metadatas', [])):
            pid = metadata.get('project_id', 0)
            if pid == 0:
                continue
            distance = results['distances'][i] if i < len(results['distances']) else 1.0
            similarity = max(0.0, 1.0 - distance)
            if pid not in scores or similarity > scores[pid]:
                scores[pid] = similarity

    except Exception as e:
        logger.warning(f'Vector similarity search failed: {e}')

    return scores


def find_similar_for_job(job):
    """Convenience wrapper that extracts parameters from a GenerationJob.

    Also collects combined text from uploaded documents for vector search.
    """
    from app.services.document_processor import extract_text

    # Gather combined text from uploaded documents
    combined_text = ''
    for doc_info in (job.uploaded_documents or []):
        filepath = doc_info.get('filepath', '')
        if filepath:
            try:
                result = extract_text(filepath)
                text = result.get('text', '')
                combined_text += text[:5000] + '\n\n'  # First 5000 chars per doc
            except Exception:
                pass

    # Extract requirements if available
    materials = []
    standards = []
    if job.extracted_requirements:
        materials = job.extracted_requirements.get('materials', [])
        standards = job.extracted_requirements.get('standards', [])

    results = find_similar_projects(
        customer_id=job.customer_id,
        product_type=job.product_type,
        materials=materials,
        standards=standards,
        query_text=combined_text if combined_text.strip() else None,
    )

    # Convert to serializable format for storage
    serialized = []
    for item in results:
        project = item['project']
        serialized.append({
            'project_id': project.id,
            'project_number': project.project_number,
            'project_name': project.project_name or '',
            'customer': project.customer.name if project.customer else '',
            'product_type': project.product_type or '',
            'materials': project.materials or [],
            'standards': project.standards or [],
            'score': round(item['score'], 4),
            'metadata_score': round(item['metadata_score'], 4),
            'vector_score': round(item['vector_score'], 4),
            'breakdown': {k: round(v, 4) for k, v in item['breakdown'].items()},
        })

    return serialized
