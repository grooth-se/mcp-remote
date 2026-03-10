"""Embedding pipeline for document indexing.

Orchestrates: text extraction -> chunking -> embedding -> vector store insertion.
Designed for batch processing of historical projects and single-document indexing.
"""
import logging
import uuid

from flask import current_app

from app import db
from app.models.document import Document
from app.models.project import Project
from app.services.document_processor import extract_text
from app.services.chunker import chunk_document
from app.services.llm_client import get_embeddings
from app.services import vector_store

logger = logging.getLogger(__name__)


def index_document(document_id):
    """Index a single document: extract text, chunk, embed, store in vector DB.

    Returns dict with indexing stats or error.
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        return {'error': f'Document {document_id} not found'}

    # Step 1: Extract text if not already done
    if not doc.extracted_text:
        result = extract_text(doc.file_path)
        if result.get('error'):
            return {'error': f'Text extraction failed: {result["error"]}'}
        doc.extracted_text = result['text']
        doc.page_count = result.get('page_count', doc.page_count)
        db.session.commit()

    if not doc.extracted_text or not doc.extracted_text.strip():
        return {'error': 'No text content extracted from document'}

    # Step 2: Chunk the text
    chunks = chunk_document(doc.extracted_text)
    if not chunks:
        return {'error': 'No chunks generated from document'}

    # Step 3: Generate embeddings (one call per chunk)
    embeddings = []
    successful_chunks = []

    for chunk in chunks:
        emb = get_embeddings(chunk['text'])
        if emb is not None:
            embeddings.append(emb)
            successful_chunks.append(chunk)
        else:
            logger.warning(f'Embedding failed for chunk {chunk["chunk_index"]} in document {document_id}')

    if not embeddings:
        return {'error': 'All embedding generations failed — is Ollama running with nomic-embed-text?'}

    # Step 4: Prepare metadata and IDs
    chunk_ids = []
    metadatas = []
    for i, chunk in enumerate(successful_chunks):
        chunk_id = f'doc-{doc.id}-{i}-{uuid.uuid4().hex[:6]}'
        chunk_ids.append(chunk_id)
        metadatas.append({
            'document_id': doc.id,
            'project_id': doc.project_id or 0,
            'document_type': doc.document_type or '',
            'file_name': doc.file_name,
            'chunk_index': chunk['chunk_index'],
            'section': chunk.get('section', ''),
        })

    # Step 5: Store in vector DB
    vector_store.add_chunks(
        chunks=[c['text'] for c in successful_chunks],
        embeddings=embeddings,
        metadatas=metadatas,
        ids=chunk_ids,
    )

    # Update document record
    doc.embedding_ids = chunk_ids
    from datetime import datetime
    doc.indexed_at = datetime.utcnow()
    db.session.commit()

    stats = {
        'document_id': doc.id,
        'chunks_total': len(chunks),
        'chunks_indexed': len(successful_chunks),
        'chunks_failed': len(chunks) - len(successful_chunks),
    }
    logger.info(f'Indexed document {doc.id}: {stats}')
    return stats


def index_project(project_id):
    """Index all documents in a project.

    Returns list of per-document indexing results.
    """
    project = db.session.get(Project, project_id)
    if not project:
        return {'error': f'Project {project_id} not found'}

    documents = Document.query.filter_by(project_id=project_id).all()
    if not documents:
        return {'error': f'No documents found for project {project_id}'}

    results = []
    for doc in documents:
        result = index_document(doc.id)
        results.append(result)

    # Update project indexed timestamp
    from datetime import datetime
    project.indexed_at = datetime.utcnow()
    db.session.commit()

    indexed_count = sum(1 for r in results if 'error' not in r)
    logger.info(f'Indexed project {project_id}: {indexed_count}/{len(documents)} documents')

    return {
        'project_id': project_id,
        'total_documents': len(documents),
        'indexed': indexed_count,
        'failed': len(documents) - indexed_count,
        'details': results,
    }


def reindex_document(document_id):
    """Delete existing embeddings and re-index a document."""
    doc = db.session.get(Document, document_id)
    if not doc:
        return {'error': f'Document {document_id} not found'}

    # Clear existing chunks
    vector_store.delete_by_document(doc.id)
    doc.embedding_ids = []
    doc.extracted_text = None
    doc.indexed_at = None
    db.session.commit()

    return index_document(document_id)


def search_similar_chunks(query_text, n_results=10, project_id=None, document_type=None):
    """Search for similar document chunks.

    Args:
        query_text: Text to search for
        n_results: Number of results
        project_id: Optional filter by project
        document_type: Optional filter by document type (MPQP, MPS, ITP, etc.)

    Returns:
        List of dicts with chunk text, metadata, and similarity score
    """
    where = {}
    if project_id:
        where['project_id'] = project_id
    if document_type:
        where['document_type'] = document_type

    results = vector_store.search_by_text(
        query_text,
        n_results=n_results,
        where=where if where else None,
    )

    formatted = []
    for i, doc_text in enumerate(results['documents']):
        formatted.append({
            'text': doc_text,
            'metadata': results['metadatas'][i] if i < len(results['metadatas']) else {},
            'distance': results['distances'][i] if i < len(results['distances']) else 1.0,
            'similarity': 1.0 - (results['distances'][i] if i < len(results['distances']) else 1.0),
            'id': results['ids'][i] if i < len(results['ids']) else '',
        })

    return formatted
