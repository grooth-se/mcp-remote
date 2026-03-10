"""ChromaDB vector store for document embeddings.

Stores document chunks with metadata for semantic similarity search.
Uses Ollama's nomic-embed-text for local embeddings.
"""
import logging
import os

from flask import current_app

logger = logging.getLogger(__name__)

# Module-level client cache
_client = None
_collection = None

COLLECTION_NAME = 'mpqp_documents'


def _get_client():
    """Get or create ChromaDB persistent client."""
    global _client
    if _client is not None:
        return _client

    import chromadb
    persist_dir = current_app.config.get('VECTOR_DB_PATH', './data/vectordb')
    os.makedirs(persist_dir, exist_ok=True)
    _client = chromadb.PersistentClient(path=persist_dir)
    return _client


def _get_collection():
    """Get or create the document collection."""
    global _collection
    if _collection is not None:
        return _collection

    client = _get_client()
    _collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={'hnsw:space': 'cosine'},
    )
    return _collection


def reset_cache():
    """Reset module-level caches (for testing)."""
    global _client, _collection
    _client = None
    _collection = None


def add_chunks(chunks, embeddings, metadatas, ids):
    """Add document chunks with pre-computed embeddings to the vector store.

    Args:
        chunks: List of text chunks
        embeddings: List of embedding vectors (from Ollama)
        metadatas: List of metadata dicts per chunk
        ids: List of unique IDs per chunk
    """
    collection = _get_collection()
    # ChromaDB has a batch limit of ~5000, process in batches
    batch_size = 500
    for i in range(0, len(chunks), batch_size):
        end = min(i + batch_size, len(chunks))
        collection.add(
            documents=chunks[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end],
            ids=ids[i:end],
        )
    logger.info(f'Added {len(chunks)} chunks to vector store')


def search(query_embedding, n_results=10, where=None, where_document=None):
    """Search for similar chunks by embedding vector.

    Args:
        query_embedding: Embedding vector for the query
        n_results: Number of results to return
        where: Optional metadata filter dict (e.g. {'project_id': 5})
        where_document: Optional document content filter

    Returns:
        Dict with 'ids', 'documents', 'metadatas', 'distances'
    """
    collection = _get_collection()
    kwargs = {
        'query_embeddings': [query_embedding],
        'n_results': n_results,
    }
    if where:
        kwargs['where'] = where
    if where_document:
        kwargs['where_document'] = where_document

    results = collection.query(**kwargs)
    return {
        'ids': results['ids'][0] if results['ids'] else [],
        'documents': results['documents'][0] if results['documents'] else [],
        'metadatas': results['metadatas'][0] if results['metadatas'] else [],
        'distances': results['distances'][0] if results['distances'] else [],
    }


def search_by_text(query_text, n_results=10, where=None):
    """Search using text — generates embedding via Ollama first.

    Convenience wrapper that handles the embedding step.
    """
    from app.services.llm_client import get_embeddings
    embedding = get_embeddings(query_text)
    if embedding is None:
        logger.error('Failed to generate query embedding')
        return {'ids': [], 'documents': [], 'metadatas': [], 'distances': []}
    return search(embedding, n_results=n_results, where=where)


def delete_by_document(document_id):
    """Delete all chunks for a specific document."""
    collection = _get_collection()
    collection.delete(where={'document_id': document_id})
    logger.info(f'Deleted chunks for document_id={document_id}')


def delete_by_project(project_id):
    """Delete all chunks for a specific project."""
    collection = _get_collection()
    collection.delete(where={'project_id': project_id})
    logger.info(f'Deleted chunks for project_id={project_id}')


def get_collection_stats():
    """Get statistics about the vector store."""
    try:
        collection = _get_collection()
        count = collection.count()
        return {
            'total_chunks': count,
            'collection_name': COLLECTION_NAME,
            'status': 'online',
        }
    except Exception as e:
        logger.error(f'Vector store stats failed: {e}')
        return {
            'total_chunks': 0,
            'collection_name': COLLECTION_NAME,
            'status': 'error',
            'error': str(e),
        }
