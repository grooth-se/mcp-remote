"""LLM-based metadata extraction from document text.

Uses Ollama to extract structured metadata (customer, product type,
materials, standards) from project documents.
"""
import logging
import re

from app import db
from app.models.project import Project
from app.models.document import Document
from app.services.llm_client import generate_json

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM = """You are an expert in offshore oil & gas manufacturing documentation.
You analyze technical specifications, manufacturing procedures, and inspection plans.
Always respond with valid JSON."""

EXTRACTION_PROMPT = """Analyze the following document text and extract key metadata.

Document filename: {filename}
Document type: {doc_type}

TEXT (first 3000 characters):
{text}

Extract and return a JSON object with these fields:
{{
    "customer_name": "Customer/client name if mentioned, or null",
    "project_reference": "Project number or reference if mentioned, or null",
    "product_type": "One of: TTR, SCR, CWOR, SLS, BODY, VALVE, FLANGE, or null if unclear",
    "product_description": "Brief description of the product/component",
    "materials": ["List of material grades mentioned, e.g. Inconel 625, F22, AISI 4130"],
    "standards": ["List of standards referenced, e.g. API 6A, ASME IX, DNV-RP-0034"],
    "testing_requirements": ["List of test types, e.g. RT, UT, tensile, impact, hardness"],
    "welding_processes": ["Welding processes if mentioned, e.g. GTAW, SMAW, SAW"],
    "heat_treatment": "Heat treatment description if mentioned, or null",
    "special_requirements": "Any special requirements or deviations noted, or null"
}}

Return ONLY the JSON object, no other text."""


def extract_document_metadata(document_id):
    """Extract metadata from a single document using LLM.

    Returns the extracted metadata dict or error.
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        return {'error': f'Document {document_id} not found'}

    if not doc.extracted_text:
        return {'error': 'No extracted text available — extract text first'}

    # Use first 3000 chars to stay within context window
    text_sample = doc.extracted_text[:3000]

    prompt = EXTRACTION_PROMPT.format(
        filename=doc.file_name,
        doc_type=doc.document_type or 'Unknown',
        text=text_sample,
    )

    result = generate_json(prompt, system=EXTRACTION_SYSTEM)
    if result is None:
        return {'error': 'LLM metadata extraction failed — is Ollama running?'}

    # Store metadata on document
    doc.metadata_ = result
    db.session.commit()

    logger.info(f'Extracted metadata for document {doc.id}: {list(result.keys())}')
    return result


def extract_project_metadata(project_id):
    """Extract and aggregate metadata across all documents in a project.

    Extracts from each document, then merges into project-level metadata.
    """
    project = db.session.get(Project, project_id)
    if not project:
        return {'error': f'Project {project_id} not found'}

    documents = Document.query.filter_by(project_id=project_id).filter(
        Document.extracted_text.isnot(None)
    ).all()

    if not documents:
        return {'error': 'No documents with extracted text'}

    all_metadata = []
    for doc in documents:
        if not doc.metadata_ or not isinstance(doc.metadata_, dict) or len(doc.metadata_) < 3:
            result = extract_document_metadata(doc.id)
            if 'error' not in result:
                all_metadata.append(result)
        else:
            all_metadata.append(doc.metadata_)

    if not all_metadata:
        return {'error': 'No metadata could be extracted from any documents'}

    # Merge metadata across documents
    merged = _merge_project_metadata(all_metadata)

    # Update project fields from merged metadata
    if merged.get('customer_name') and not project.customer_id:
        from app.models.project import Customer
        customer = Customer.query.filter_by(name=merged['customer_name']).first()
        if not customer:
            customer = Customer(name=merged['customer_name'])
            db.session.add(customer)
            db.session.flush()
        project.customer_id = customer.id

    if merged.get('product_type') and not project.product_type:
        project.product_type = merged['product_type']
        project.product_category = Project.PRODUCT_CATEGORIES.get(merged['product_type'], '')

    if merged.get('materials'):
        project.materials = merged['materials']

    if merged.get('standards'):
        project.standards = merged['standards']

    project.metadata_ = merged
    db.session.commit()

    logger.info(f'Updated project {project_id} metadata: {list(merged.keys())}')
    return merged


def _merge_project_metadata(metadata_list):
    """Merge metadata from multiple documents into a single project summary."""
    merged = {
        'customer_name': None,
        'product_type': None,
        'product_description': None,
        'materials': [],
        'standards': [],
        'testing_requirements': [],
        'welding_processes': [],
    }

    for meta in metadata_list:
        if not isinstance(meta, dict):
            continue

        # Take first non-null customer/product
        if meta.get('customer_name') and not merged['customer_name']:
            merged['customer_name'] = meta['customer_name']

        if meta.get('product_type') and not merged['product_type']:
            pt = meta['product_type'].upper().strip()
            valid_types = {t[0] for t in Project.PRODUCT_TYPES}
            if pt in valid_types:
                merged['product_type'] = pt

        if meta.get('product_description') and not merged['product_description']:
            merged['product_description'] = meta['product_description']

        # Merge lists (deduplicated)
        for key in ('materials', 'standards', 'testing_requirements', 'welding_processes'):
            items = meta.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if item and item not in merged[key]:
                        merged[key].append(item)

        # Copy other scalar fields
        for key in ('heat_treatment', 'special_requirements', 'project_reference'):
            if meta.get(key) and key not in merged:
                merged[key] = meta[key]

    return merged


def extract_metadata_from_text(text, filename='unknown'):
    """Standalone extraction without database — useful for uploaded documents.

    Returns extracted metadata dict or None.
    """
    text_sample = text[:3000]
    prompt = EXTRACTION_PROMPT.format(
        filename=filename,
        doc_type='Unknown',
        text=text_sample,
    )
    return generate_json(prompt, system=EXTRACTION_SYSTEM)
