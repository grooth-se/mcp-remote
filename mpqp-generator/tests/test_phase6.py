"""Phase 6 tests: chat refinement service and routes."""
import os
import tempfile
import json


# --- Chat refinement service tests ---

def test_read_document(app, db):
    from app.services.chat_refinement import _read_document
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('# MPQP - Test\n\n---\n\n## Scope\nScope content.\n\n## Materials\nInconel 625\n')
        filepath = f.name

    try:
        job = GenerationJob(new_project_name='Read Test', generated_document_path=filepath)
        db.session.add(job)
        db.session.commit()

        content = _read_document(job)
        assert content is not None
        assert '## Scope' in content
        assert 'Inconel 625' in content
        # Metadata header should be stripped
        assert '# MPQP' not in content
    finally:
        os.unlink(filepath)


def test_read_document_missing(app, db):
    from app.services.chat_refinement import _read_document
    from app.models.generation import GenerationJob

    job = GenerationJob(new_project_name='No File')
    db.session.add(job)
    db.session.commit()

    assert _read_document(job) is None


def test_format_history():
    from app.services.chat_refinement import _format_history

    messages = [
        {'role': 'user', 'content': 'Update materials', 'timestamp': '2026-01-01T10:00:00'},
        {'role': 'assistant', 'content': 'Here is the updated section.', 'timestamp': '2026-01-01T10:00:05'},
    ]
    result = _format_history(messages)
    assert 'User: Update materials' in result
    assert 'Assistant: Here is the updated section.' in result


def test_replace_section():
    from app.services.chat_refinement import _replace_section

    content = """## Scope
This is the scope.

## Materials
Inconel 625 per ASTM B443.

## Testing
UT and MPI required.
"""
    new_materials = "## Materials\nSuper Duplex per ASTM A890."
    result = _replace_section(content, 'Materials', new_materials)

    assert 'Super Duplex' in result
    assert 'Inconel 625' not in result
    assert '## Scope' in result
    assert '## Testing' in result


def test_replace_section_not_found():
    from app.services.chat_refinement import _replace_section

    content = "## Scope\nContent here."
    result = _replace_section(content, 'Nonexistent Section', 'new content')
    assert result == content  # Unchanged


def test_replace_section_without_header():
    from app.services.chat_refinement import _replace_section

    content = "## Scope\nOld scope.\n\n## Materials\nOld materials."
    result = _replace_section(content, 'Scope', 'New scope content.')
    assert '## Scope' in result
    assert 'New scope content' in result


def test_apply_revision(app, db):
    from app.services.chat_refinement import apply_revision
    from app.models.generation import GenerationJob, DocumentVersion

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('# MPQP - Test\n\n---\n\n## Scope\nOriginal.\n')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Revision Test',
            generated_document_path=filepath,
            current_version=1,
        )
        db.session.add(job)
        db.session.commit()

        result = apply_revision(job.id, '## Scope\nUpdated scope content.', 'Test revision')
        assert result['version'] == 2
        assert os.path.exists(result['filepath'])

        db.session.refresh(job)
        assert job.current_version == 2
        assert job.generated_document_path == result['filepath']

        versions = DocumentVersion.query.filter_by(generation_job_id=job.id).all()
        assert len(versions) == 1
        assert versions[0].version_number == 2
        assert 'Test revision' in versions[0].changes_description

        # Clean up
        os.unlink(result['filepath'])
    finally:
        if os.path.exists(filepath):
            os.unlink(filepath)


def test_apply_revision_no_document(app, db):
    from app.services.chat_refinement import apply_revision
    from app.models.generation import GenerationJob

    job = GenerationJob(new_project_name='No Doc')
    db.session.add(job)
    db.session.commit()

    result = apply_revision(job.id, 'content', 'desc')
    assert 'error' in result


def test_apply_section_update(app, db):
    from app.services.chat_refinement import apply_section_update
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('---\n\n## Scope\nOld scope.\n\n## Materials\nOld materials.\n')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Section Update',
            generated_document_path=filepath,
            current_version=1,
        )
        db.session.add(job)
        db.session.commit()

        result = apply_section_update(job.id, 'Materials', '## Materials\nNew Duplex steel.')
        assert result['version'] == 2

        # Read the new file and verify
        with open(result['filepath'], 'r') as f:
            new_content = f.read()
        assert 'New Duplex steel' in new_content
        assert '## Scope' in new_content

        os.unlink(result['filepath'])
    finally:
        if os.path.exists(filepath):
            os.unlink(filepath)


def test_get_chat_history_empty(app, db):
    from app.services.chat_refinement import get_chat_history
    from app.models.generation import GenerationJob

    job = GenerationJob(new_project_name='Empty Chat')
    db.session.add(job)
    db.session.commit()

    assert get_chat_history(job.id) == []


def test_clear_chat_history(app, db):
    from app.services.chat_refinement import clear_chat_history
    from app.models.generation import GenerationJob

    job = GenerationJob(
        new_project_name='Clear Chat',
        chat_history=[{'role': 'user', 'content': 'hello', 'timestamp': '2026-01-01'}],
    )
    db.session.add(job)
    db.session.commit()

    assert clear_chat_history(job.id)
    db.session.refresh(job)
    assert job.chat_history == []


def test_clear_chat_history_nonexistent(app, db):
    from app.services.chat_refinement import clear_chat_history
    assert clear_chat_history(9999) is False


# --- Route tests ---

def test_chat_page_requires_document(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='No Doc Chat', status='pending')
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.get(f'/generate/chat/{job.id}', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Generate a document first' in resp.data


def test_chat_page_with_document(app, db, logged_in_client):
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('---\n\n## Scope\nTest scope.\n')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Chat Page Test',
            status='completed',
            generated_document_path=filepath,
            current_version=1,
        )
        db.session.add(job)
        db.session.commit()

        resp = logged_in_client.get(f'/generate/chat/{job.id}')
        assert resp.status_code == 200
        assert b'Refine Document' in resp.data
        assert b'Test scope' in resp.data
    finally:
        os.unlink(filepath)


def test_chat_send_no_message(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='Send Test', status='completed')
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.post(
        f'/generate/chat/{job.id}/send',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400


def test_chat_send_job_not_found(app, db, logged_in_client):
    resp = logged_in_client.post(
        '/generate/chat/9999/send',
        data=json.dumps({'message': 'test'}),
        content_type='application/json',
    )
    assert resp.status_code == 404


def test_chat_apply_no_content(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='Apply Test', status='completed')
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.post(
        f'/generate/chat/{job.id}/apply',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400


def test_chat_apply_success(app, db, logged_in_client):
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('---\n\n## Scope\nOriginal.\n')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Apply Success',
            status='completed',
            generated_document_path=filepath,
            current_version=1,
        )
        db.session.add(job)
        db.session.commit()

        resp = logged_in_client.post(
            f'/generate/chat/{job.id}/apply',
            data=json.dumps({'content': '## Scope\nRevised content.', 'description': 'Test apply'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['version'] == 2

        # Clean up generated file
        if os.path.exists(data['filepath']):
            os.unlink(data['filepath'])
    finally:
        if os.path.exists(filepath):
            os.unlink(filepath)


def test_chat_clear_route(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(
        new_project_name='Clear Route',
        chat_history=[{'role': 'user', 'content': 'hi', 'timestamp': '2026-01-01'}],
    )
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.post(f'/generate/chat/{job.id}/clear')
    assert resp.status_code == 200

    db.session.refresh(job)
    assert job.chat_history == []


def test_status_page_shows_refine_button(app, db, logged_in_client):
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('---\n\n## Test\nContent')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Refine Button',
            status='completed',
            generated_document_path=filepath,
        )
        db.session.add(job)
        db.session.commit()

        resp = logged_in_client.get(f'/generate/status/{job.id}')
        assert resp.status_code == 200
        assert b'Refine with Chat' in resp.data
    finally:
        os.unlink(filepath)
