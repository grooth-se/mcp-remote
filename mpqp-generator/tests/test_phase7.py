"""Phase 7 tests: polish, health endpoint, deployment readiness."""
import os
import tempfile


def test_health_endpoint(app, db, client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['app'] == 'mpqp-generator'
    assert data['database'] == 'ok'


def test_dashboard_shows_ollama_status(app, db, logged_in_client):
    resp = logged_in_client.get('/')
    assert resp.status_code == 200
    # Should show either online or offline indicator
    assert b'Ollama' in resp.data


def test_dashboard_shows_stats(app, db, logged_in_client):
    resp = logged_in_client.get('/')
    assert resp.status_code == 200
    assert b'Indexed Projects' in resp.data
    assert b'Documents Generated' in resp.data


def test_dashboard_completed_job_shows_actions(app, db, logged_in_client):
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('# Test\nContent')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Action Test',
            status='completed',
            generated_document_path=filepath,
        )
        db.session.add(job)
        db.session.commit()

        resp = logged_in_client.get('/')
        assert resp.status_code == 200
        # Should have refine and download action buttons
        assert b'bi-chat-dots' in resp.data
        assert b'bi-download' in resp.data
    finally:
        os.unlink(filepath)


def test_job_list_shows_version(app, db, logged_in_client):
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('# Test\nContent')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Version Display',
            status='completed',
            generated_document_path=filepath,
            current_version=3,
        )
        db.session.add(job)
        db.session.commit()

        resp = logged_in_client.get('/generate/jobs')
        assert resp.status_code == 200
        assert b'v3' in resp.data
    finally:
        os.unlink(filepath)


def test_job_list_shows_action_buttons(app, db, logged_in_client):
    from app.models.generation import GenerationJob

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('# Test\nContent')
        filepath = f.name

    try:
        job = GenerationJob(
            new_project_name='Buttons Test',
            status='completed',
            generated_document_path=filepath,
        )
        db.session.add(job)
        db.session.commit()

        resp = logged_in_client.get('/generate/jobs')
        assert resp.status_code == 200
        assert b'bi-chat-dots' in resp.data
    finally:
        os.unlink(filepath)


def test_entrypoint_script_exists():
    path = os.path.join(os.path.dirname(__file__), '..', 'entrypoint.sh')
    assert os.path.exists(path)
    assert os.access(path, os.X_OK)


def test_dockerfile_has_healthcheck():
    path = os.path.join(os.path.dirname(__file__), '..', 'Dockerfile')
    with open(path) as f:
        content = f.read()
    assert 'HEALTHCHECK' in content
    assert 'ENTRYPOINT' in content


def test_nginx_conf_exists():
    path = os.path.join(os.path.dirname(__file__), '..', 'nginx.conf')
    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert 'mpqpgenerator' in content
    assert 'X-Script-Name' in content
    assert 'proxy_read_timeout' in content


def test_docker_compose_has_healthcheck():
    path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')
    with open(path) as f:
        content = f.read()
    assert 'healthcheck' in content
    assert 'pg_isready' in content
    assert 'condition: service_healthy' in content
