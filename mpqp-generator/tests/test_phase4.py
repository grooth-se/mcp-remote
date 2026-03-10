"""Phase 4 tests: similarity engine, review workflow, reference selection."""
import os
import tempfile


# --- Similarity scoring tests ---

def test_metadata_score_exact_customer(app, db):
    from app.services.similarity_engine import _compute_metadata_score
    from app.models.project import Project, Customer

    c = Customer(name='Aker Solutions')
    db.session.add(c)
    db.session.flush()
    p = Project(project_number='P-001', folder_path='/tmp', customer_id=c.id,
                product_type='TTR', materials=['Inconel 625'], standards=['API 6A'])
    db.session.add(p)
    db.session.commit()

    score, breakdown = _compute_metadata_score(
        p, customer_id=c.id, product_type='TTR',
        materials=['Inconel 625'], standards=['API 6A']
    )
    assert score == 1.0  # Perfect match on all factors
    assert breakdown['customer'] == 1.0
    assert breakdown['product'] == 1.0
    assert breakdown['materials'] == 1.0
    assert breakdown['standards'] == 1.0


def test_metadata_score_no_match(app, db):
    from app.services.similarity_engine import _compute_metadata_score
    from app.models.project import Project, Customer

    c1 = Customer(name='Company A')
    c2 = Customer(name='Company B')
    db.session.add_all([c1, c2])
    db.session.flush()
    p = Project(project_number='P-002', folder_path='/tmp', customer_id=c1.id,
                product_type='VALVE', materials=['AISI 4130'], standards=['ASME VIII'])
    db.session.add(p)
    db.session.commit()

    score, breakdown = _compute_metadata_score(
        p, customer_id=c2.id, product_type='TTR',
        materials=['Inconel 625'], standards=['API 6A']
    )
    assert score == 0.0
    assert breakdown['customer'] == 0.0
    assert breakdown['product'] == 0.0


def test_metadata_score_same_category(app, db):
    from app.services.similarity_engine import _compute_metadata_score
    from app.models.project import Project

    p = Project(project_number='P-003', folder_path='/tmp', product_type='SCR')
    db.session.add(p)
    db.session.commit()

    # TTR and SCR are both "Riser" category
    score, breakdown = _compute_metadata_score(
        p, customer_id=None, product_type='TTR',
        materials=[], standards=[]
    )
    assert breakdown['product'] == 0.5  # Same category, different type
    assert score > 0


def test_metadata_score_partial_materials(app, db):
    from app.services.similarity_engine import _compute_metadata_score
    from app.models.project import Project

    p = Project(project_number='P-004', folder_path='/tmp',
                materials=['Inconel 625', 'F22', 'AISI 4130'])
    db.session.add(p)
    db.session.commit()

    score, breakdown = _compute_metadata_score(
        p, customer_id=None, product_type=None,
        materials=['Inconel 625', 'Super Duplex'], standards=[]
    )
    # 1 out of 2 new materials found in project
    assert breakdown['materials'] == 0.5


def test_metadata_score_case_insensitive(app, db):
    from app.services.similarity_engine import _compute_metadata_score
    from app.models.project import Project

    p = Project(project_number='P-005', folder_path='/tmp',
                materials=['inconel 625'], standards=['api 6a'])
    db.session.add(p)
    db.session.commit()

    score, breakdown = _compute_metadata_score(
        p, customer_id=None, product_type=None,
        materials=['INCONEL 625'], standards=['API 6A']
    )
    assert breakdown['materials'] == 1.0
    assert breakdown['standards'] == 1.0


# --- find_similar_projects tests ---

def test_find_similar_empty_db(app, db):
    from app.services.similarity_engine import find_similar_projects
    results = find_similar_projects(product_type='TTR')
    assert results == []


def test_find_similar_ranks_by_score(app, db):
    from app.services.similarity_engine import find_similar_projects
    from app.models.project import Project, Customer

    c = Customer(name='Best Match Co')
    db.session.add(c)
    db.session.flush()

    # Perfect match project
    p1 = Project(project_number='P-100', folder_path='/tmp', customer_id=c.id,
                 product_type='TTR', materials=['Inconel 625'], standards=['API 6A'])
    # Partial match
    p2 = Project(project_number='P-101', folder_path='/tmp',
                 product_type='SCR', materials=['F22'], standards=['ASME IX'])
    # No match
    p3 = Project(project_number='P-102', folder_path='/tmp',
                 product_type='VALVE', materials=['Bronze'], standards=['ISO 9001'])
    db.session.add_all([p1, p2, p3])
    db.session.commit()

    results = find_similar_projects(
        customer_id=c.id, product_type='TTR',
        materials=['Inconel 625'], standards=['API 6A']
    )

    assert len(results) == 3
    # Best match should be first
    assert results[0]['project'].id == p1.id
    assert results[0]['score'] > results[1]['score']
    assert results[1]['score'] >= results[2]['score']


def test_find_similar_max_results(app, db):
    from app.services.similarity_engine import find_similar_projects
    from app.models.project import Project

    for i in range(20):
        db.session.add(Project(project_number=f'P-{i:03d}', folder_path='/tmp'))
    db.session.commit()

    results = find_similar_projects(max_results=5)
    assert len(results) == 5


# --- find_similar_for_job tests ---

def test_find_similar_for_job(app, db):
    from app.services.similarity_engine import find_similar_for_job
    from app.models.generation import GenerationJob
    from app.models.project import Project, Customer

    c = Customer(name='JobTest Co')
    db.session.add(c)
    db.session.flush()

    p = Project(project_number='P-200', folder_path='/tmp', customer_id=c.id,
                product_type='TTR', materials=['Inconel 625'])
    db.session.add(p)

    job = GenerationJob(
        new_project_name='Test Job',
        customer_id=c.id,
        product_type='TTR',
        extracted_requirements={'materials': ['Inconel 625'], 'standards': ['API 6A']},
        uploaded_documents=[],
    )
    db.session.add(job)
    db.session.commit()

    results = find_similar_for_job(job)
    assert len(results) >= 1
    assert results[0]['project_id'] == p.id
    assert 'score' in results[0]
    assert 'breakdown' in results[0]


# --- Route tests ---

def test_review_page_no_similar(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='Test', status='review')
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.get(f'/generate/review/{job.id}')
    assert resp.status_code == 200
    assert b'Similar Projects' in resp.data


def test_review_page_with_similar(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    from app.models.project import Project

    p = Project(project_number='P-REF-1', folder_path='/tmp', product_type='TTR')
    db.session.add(p)
    db.session.flush()

    job = GenerationJob(
        new_project_name='Test With Similar',
        status='review',
        similar_projects=[{
            'project_id': p.id,
            'project_number': 'P-REF-1',
            'project_name': 'Reference Project',
            'customer': 'Aker',
            'product_type': 'TTR',
            'materials': ['Inconel 625'],
            'standards': ['API 6A'],
            'score': 0.85,
            'metadata_score': 0.85,
            'vector_score': 0.0,
            'breakdown': {'customer': 1.0, 'product': 1.0, 'materials': 0.5, 'standards': 0.5},
        }],
    )
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.get(f'/generate/review/{job.id}')
    assert resp.status_code == 200
    assert b'P-REF-1' in resp.data
    assert b'85%' in resp.data


def test_select_references(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='Test Select', status='review',
                        similar_projects=[{
                            'project_id': 1, 'project_number': 'P-1', 'project_name': '',
                            'customer': '', 'product_type': '', 'materials': [], 'standards': [],
                            'score': 0.5, 'metadata_score': 0.5, 'vector_score': 0.0,
                            'breakdown': {'customer': 0, 'product': 0, 'materials': 0, 'standards': 0},
                        }])
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.post(
        f'/generate/select-references/{job.id}',
        data={'reference_projects': ['1'], 'csrf_token': _get_csrf(logged_in_client, f'/generate/review/{job.id}')},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db.session.refresh(job)
    assert job.selected_references == [1]


def test_status_page_shows_workflow(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='Workflow Test', status='pending')
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.get(f'/generate/status/{job.id}')
    assert resp.status_code == 200
    assert b'Workflow' in resp.data
    assert b'Extract Requirements' in resp.data
    assert b'Find Similar Projects' in resp.data


def test_find_similar_route(app, db, logged_in_client):
    from app.models.generation import GenerationJob
    job = GenerationJob(new_project_name='Similarity Test', status='pending',
                        uploaded_documents=[])
    db.session.add(job)
    db.session.commit()

    resp = logged_in_client.post(
        f'/generate/find-similar/{job.id}',
        data={'csrf_token': _get_csrf(logged_in_client, f'/generate/status/{job.id}')},
        follow_redirects=True,
    )
    assert resp.status_code == 200


# --- Helper ---

def _get_csrf(client, url='/generate/jobs'):
    import re
    resp = client.get(url)
    data = resp.data.decode()
    match = re.search(r'name="csrf_token" value="([^"]+)"', data)
    return match.group(1) if match else ''
