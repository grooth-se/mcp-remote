"""Basic tests for Phase 1."""


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.json['status'] == 'ok'


def test_dashboard_requires_auth(client):
    resp = client.get('/')
    assert resp.status_code in (302, 401)


def test_dashboard_with_auth(logged_in_client):
    resp = logged_in_client.get('/')
    assert resp.status_code == 200
    assert b'Dashboard' in resp.data


def test_upload_page(logged_in_client):
    resp = logged_in_client.get('/upload/')
    assert resp.status_code == 200
    assert b'New Document Generation' in resp.data


def test_admin_page(logged_in_client):
    resp = logged_in_client.get('/admin/')
    assert resp.status_code == 200
    assert b'System Status' in resp.data


def test_jobs_page(logged_in_client):
    resp = logged_in_client.get('/generate/jobs')
    assert resp.status_code == 200


def test_projects_page(logged_in_client):
    resp = logged_in_client.get('/projects')
    assert resp.status_code == 200


def test_customer_model(app, db):
    from app.models.project import Customer
    c = Customer(name='Test Oil & Gas Corp', code='TOGC')
    db.session.add(c)
    db.session.commit()
    assert c.id is not None
    assert Customer.query.filter_by(name='Test Oil & Gas Corp').first() is not None


def test_project_model(app, db):
    from app.models.project import Customer, Project
    c = Customer(name='TestCo')
    db.session.add(c)
    db.session.flush()

    p = Project(
        project_number='P-2026-001',
        project_name='TTR System',
        customer_id=c.id,
        product_type='TTR',
        materials=['Inconel 625', 'F22'],
        standards=['API 6A', 'ASME IX'],
        folder_path='/projects/P-2026-001',
    )
    db.session.add(p)
    db.session.commit()
    assert p.id is not None
    assert p.materials == ['Inconel 625', 'F22']


def test_generation_job_model(app, db):
    from app.models.generation import GenerationJob
    job = GenerationJob(
        new_project_name='Test Project',
        product_type='SCR',
        status='pending',
    )
    db.session.add(job)
    db.session.commit()
    assert job.id is not None
    assert job.status_label == 'Pending'


def test_document_processor_pdf_missing_lib(app):
    """Test graceful handling when file doesn't exist."""
    from app.services.document_processor import extract_text
    result = extract_text('/nonexistent/file.pdf')
    assert 'error' in result or result['text'] == ''


def test_text_chunking():
    from app.utils.text_utils import chunk_text
    text = ' '.join(['word'] * 2000)
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    assert len(chunks) > 1


def test_llm_client_status(app):
    """Test Ollama status check returns valid structure."""
    from app.services.llm_client import check_ollama_status
    status = check_ollama_status()
    assert 'online' in status
    assert 'models' in status
    assert isinstance(status['models'], list)
