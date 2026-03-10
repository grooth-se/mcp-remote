"""Phase 2 tests: chunking, vector store, embedder service, admin routes."""
import os
import tempfile


# --- Chunker tests ---

def test_chunk_empty_text(app):
    from app.services.chunker import chunk_document
    assert chunk_document('') == []
    assert chunk_document('   ') == []


def test_chunk_short_text(app):
    from app.services.chunker import chunk_document
    text = 'This is a short paragraph with enough words to pass the minimum filter of ten words in a chunk.'
    chunks = chunk_document(text)
    assert len(chunks) == 1
    assert chunks[0]['chunk_index'] == 0


def test_chunk_with_sections(app):
    from app.services.chunker import chunk_document
    text = """1.1 Introduction
This section describes the manufacturing procedure for the Top Tensioned Riser system.
The procedure follows API 6A and ASME IX requirements for all welding activities.

2.1 Material Specifications
The main structural material is Inconel 625 with minimum yield strength of 120 ksi.
Heat treatment shall be performed according to customer specification CS-2024-001.

3.1 Testing Requirements
All welds shall be inspected using RT and UT methods per ASME V.
Mechanical testing includes tensile, impact, and hardness per ASTM A370.
"""
    chunks = chunk_document(text)
    assert len(chunks) >= 2  # Should split on section headers
    # Check sections are captured
    sections = [c['section'] for c in chunks]
    assert any('1.1' in s for s in sections)


def test_chunk_large_text(app):
    from app.services.chunker import chunk_document
    # Generate a long text that exceeds chunk size
    text = '\n\n'.join([f'Paragraph {i}. ' + ' '.join(['word'] * 100) for i in range(30)])
    chunks = chunk_document(text, chunk_size=500, chunk_overlap=100)
    assert len(chunks) > 1
    # Check overlap: last words of chunk N should appear in chunk N+1
    if len(chunks) >= 2:
        words_0 = set(chunks[0]['text'].split()[-20:])
        words_1 = set(chunks[1]['text'].split()[:50])
        assert len(words_0 & words_1) > 0, 'Expected overlap between consecutive chunks'


def test_chunk_indices_sequential(app):
    from app.services.chunker import chunk_document
    text = '\n\n'.join([f'Section {i}. ' + ' '.join(['content'] * 50) for i in range(10)])
    chunks = chunk_document(text)
    indices = [c['chunk_index'] for c in chunks]
    assert indices == list(range(len(chunks)))


# --- Vector store tests ---

def test_vector_store_add_and_search(app):
    from app.services import vector_store
    vector_store.reset_cache()

    # Use a temp dir for ChromaDB
    with tempfile.TemporaryDirectory() as tmpdir:
        app.config['VECTOR_DB_PATH'] = tmpdir

        # Add some test chunks with fake embeddings (768-dim for nomic-embed-text)
        dim = 768
        chunks = ['Welding procedure for Inconel 625', 'Heat treatment specification F22',
                   'Pressure testing requirements API 6A']
        embeddings = [[float(i + j) / 1000 for j in range(dim)] for i in range(len(chunks))]
        metadatas = [
            {'document_id': 1, 'project_id': 1, 'document_type': 'MPS', 'file_name': 'wps.pdf', 'chunk_index': 0, 'section': ''},
            {'document_id': 1, 'project_id': 1, 'document_type': 'MPS', 'file_name': 'ht.pdf', 'chunk_index': 1, 'section': ''},
            {'document_id': 2, 'project_id': 2, 'document_type': 'ITP', 'file_name': 'test.pdf', 'chunk_index': 0, 'section': ''},
        ]
        ids = ['chunk-1', 'chunk-2', 'chunk-3']

        vector_store.add_chunks(chunks, embeddings, metadatas, ids)

        stats = vector_store.get_collection_stats()
        assert stats['total_chunks'] == 3
        assert stats['status'] == 'online'

        # Search with a query embedding close to the first chunk
        query_emb = [0.001] * dim
        results = vector_store.search(query_emb, n_results=2)
        assert len(results['ids']) <= 2
        assert len(results['documents']) <= 2

        vector_store.reset_cache()


def test_vector_store_delete_by_document(app):
    from app.services import vector_store
    vector_store.reset_cache()

    with tempfile.TemporaryDirectory() as tmpdir:
        app.config['VECTOR_DB_PATH'] = tmpdir
        dim = 768

        chunks = ['chunk A', 'chunk B', 'chunk C']
        embeddings = [[float(i) / 100] * dim for i in range(3)]
        metadatas = [
            {'document_id': 10, 'project_id': 1, 'document_type': '', 'file_name': 'a.pdf', 'chunk_index': 0, 'section': ''},
            {'document_id': 10, 'project_id': 1, 'document_type': '', 'file_name': 'a.pdf', 'chunk_index': 1, 'section': ''},
            {'document_id': 20, 'project_id': 1, 'document_type': '', 'file_name': 'b.pdf', 'chunk_index': 0, 'section': ''},
        ]
        ids = ['a1', 'a2', 'b1']
        vector_store.add_chunks(chunks, embeddings, metadatas, ids)

        assert vector_store.get_collection_stats()['total_chunks'] == 3

        vector_store.delete_by_document(10)
        assert vector_store.get_collection_stats()['total_chunks'] == 1

        vector_store.reset_cache()


def test_vector_store_filter_search(app):
    from app.services import vector_store
    vector_store.reset_cache()

    with tempfile.TemporaryDirectory() as tmpdir:
        app.config['VECTOR_DB_PATH'] = tmpdir
        dim = 768

        chunks = ['MPQP content', 'ITP content']
        embeddings = [[0.5] * dim, [0.5] * dim]
        metadatas = [
            {'document_id': 1, 'project_id': 1, 'document_type': 'MPQP', 'file_name': 'mpqp.pdf', 'chunk_index': 0, 'section': ''},
            {'document_id': 2, 'project_id': 1, 'document_type': 'ITP', 'file_name': 'itp.pdf', 'chunk_index': 0, 'section': ''},
        ]
        ids = ['m1', 'i1']
        vector_store.add_chunks(chunks, embeddings, metadatas, ids)

        # Filter by document_type
        results = vector_store.search([0.5] * dim, n_results=10, where={'document_type': 'MPQP'})
        assert len(results['ids']) == 1
        assert results['metadatas'][0]['document_type'] == 'MPQP'

        vector_store.reset_cache()


# --- Admin route tests ---

def test_admin_index_shows_vector_stats(logged_in_client):
    resp = logged_in_client.get('/admin/')
    assert resp.status_code == 200
    assert b'Vector Database' in resp.data or b'ChromaDB' in resp.data


def test_admin_indexing_page(logged_in_client):
    resp = logged_in_client.get('/admin/indexing')
    assert resp.status_code == 200
    assert b'Document Indexing' in resp.data


def test_admin_search_page(logged_in_client):
    resp = logged_in_client.get('/admin/search')
    assert resp.status_code == 200
    assert b'Vector Search' in resp.data


def test_admin_search_with_query_no_results(logged_in_client):
    """Search with no indexed data should return empty results gracefully."""
    resp = logged_in_client.get('/admin/search?q=test+welding')
    assert resp.status_code == 200


def test_admin_vector_stats_api(logged_in_client):
    resp = logged_in_client.get('/admin/api/vector-stats')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'total_chunks' in data
    assert 'status' in data


# --- Text utils still works ---

def test_clean_text():
    from app.utils.text_utils import clean_text
    text = 'Hello\n\n\n\n\nWorld   with    spaces'
    result = clean_text(text)
    assert '\n\n\n' not in result
    assert '   ' not in result
