"""Phase 3 tests: project scanner, metadata extractor, batch indexing, admin routes."""
import os
import tempfile


# --- Project scanner tests ---

def test_scan_empty_directory(app, db):
    from app.services.project_scanner import scan_directory
    with tempfile.TemporaryDirectory() as tmpdir:
        result = scan_directory(tmpdir)
        assert result['projects_found'] == 0
        assert result['documents_found'] == 0
        assert not result.get('error')


def test_scan_nonexistent_directory(app, db):
    from app.services.project_scanner import scan_directory
    result = scan_directory('/nonexistent/path')
    assert 'error' in result


def test_scan_creates_projects_and_documents(app, db):
    from app.services.project_scanner import scan_directory
    from app.models.project import Project
    from app.models.document import Document

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake project structure
        proj_dir = os.path.join(tmpdir, 'P-2024-001 CustomerA TTR')
        os.makedirs(proj_dir)
        # Create a fake text file with .pdf extension (won't extract but will register)
        with open(os.path.join(proj_dir, 'MPQP_Rev1.pdf'), 'w') as f:
            f.write('fake pdf content')
        with open(os.path.join(proj_dir, 'ITP.pdf'), 'w') as f:
            f.write('fake itp')

        result = scan_directory(tmpdir, extract_text_flag=False)
        assert result['projects_found'] == 1
        assert result['projects_created'] == 1
        assert result['documents_found'] == 2
        assert result['documents_created'] == 2

        # Verify database records
        project = Project.query.filter_by(project_number='P-2024-001').first()
        assert project is not None
        assert project.product_type == 'TTR'

        docs = Document.query.filter_by(project_id=project.id).all()
        assert len(docs) == 2


def test_scan_dry_run(app, db):
    from app.services.project_scanner import scan_directory
    from app.models.project import Project

    with tempfile.TemporaryDirectory() as tmpdir:
        proj_dir = os.path.join(tmpdir, 'P-2025-010 TestCo SCR')
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, 'spec.pdf'), 'w') as f:
            f.write('content')

        result = scan_directory(tmpdir, dry_run=True)
        assert result['projects_found'] == 1
        assert result['documents_found'] == 1

        # No DB records should be created
        assert Project.query.count() == 0


def test_scan_skips_existing_projects(app, db):
    from app.services.project_scanner import scan_directory
    from app.models.project import Project

    with tempfile.TemporaryDirectory() as tmpdir:
        proj_dir = os.path.join(tmpdir, 'P-2024-050 Existing')
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, 'doc.pdf'), 'w') as f:
            f.write('content')

        # First scan creates
        result1 = scan_directory(tmpdir, extract_text_flag=False)
        assert result1['projects_created'] == 1

        # Second scan skips
        result2 = scan_directory(tmpdir, extract_text_flag=False)
        assert result2['projects_skipped'] == 1
        assert result2['projects_created'] == 0


def test_scan_recursive_documents(app, db):
    from app.services.project_scanner import scan_directory

    with tempfile.TemporaryDirectory() as tmpdir:
        proj_dir = os.path.join(tmpdir, 'P-2024-070 DeepScan')
        sub_dir = os.path.join(proj_dir, 'specs', 'customer')
        os.makedirs(sub_dir)
        with open(os.path.join(sub_dir, 'spec.pdf'), 'w') as f:
            f.write('nested doc')
        with open(os.path.join(proj_dir, 'mpqp.docx'), 'w') as f:
            f.write('root doc')

        result = scan_directory(tmpdir, extract_text_flag=False)
        assert result['documents_found'] == 2
        assert result['documents_created'] == 2


def test_scan_skips_hidden_and_temp_files(app, db):
    from app.services.project_scanner import scan_directory

    with tempfile.TemporaryDirectory() as tmpdir:
        proj_dir = os.path.join(tmpdir, 'P-2024-080 HiddenTest')
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, '.hidden.pdf'), 'w') as f:
            f.write('hidden')
        with open(os.path.join(proj_dir, '~$tempfile.docx'), 'w') as f:
            f.write('temp')
        with open(os.path.join(proj_dir, 'real.pdf'), 'w') as f:
            f.write('real')

        result = scan_directory(tmpdir, extract_text_flag=False)
        assert result['documents_found'] == 1  # Only real.pdf


# --- Document type guessing ---

def test_guess_document_type():
    from app.services.project_scanner import _guess_document_type
    assert _guess_document_type('/projects/P1/MPQP_Rev2.docx') == 'MPQP'
    assert _guess_document_type('/projects/P1/ITP_final.xlsx') == 'ITP'
    assert _guess_document_type('/projects/P1/MPS_001.pdf') == 'MPS'
    assert _guess_document_type('/projects/P1/specs/customer_spec.pdf') == 'SPEC'
    assert _guess_document_type('/projects/P1/random.pdf') == 'OTHER'


def test_guess_product_type():
    from app.services.project_scanner import _guess_product_type
    assert _guess_product_type('P-2024-001 Aker TTR System') == 'TTR'
    assert _guess_product_type('P-2024-002 SCR Connection') == 'SCR'
    assert _guess_product_type('P-2024-003 Valve Assembly') == 'VALVE'
    assert _guess_product_type('P-2024-004 Unknown Product') == ''


def test_extract_project_number():
    from app.services.project_scanner import _extract_project_number
    assert _extract_project_number('P-2024-001 Customer TTR') == 'P-2024-001'
    assert _extract_project_number('2023-42 Something') == '2023-42'
    assert _extract_project_number('0116_145_Bonga TFMC Kongsberg') == '0116_145'
    assert _extract_project_number('0002-101 Snorre FMC') == '0002-101'
    assert _extract_project_number('NoNumber') is None


def test_guess_customer_name():
    from app.services.project_scanner import _guess_customer_name
    name = _guess_customer_name('P-2024-001 Aker Solutions TTR', 'P-2024-001')
    assert name is not None
    assert 'Aker' in name


# --- Metadata extractor (unit tests, no LLM needed) ---

def test_merge_project_metadata():
    from app.services.metadata_extractor import _merge_project_metadata
    metas = [
        {
            'customer_name': 'Aker Solutions',
            'product_type': 'TTR',
            'materials': ['Inconel 625', 'F22'],
            'standards': ['API 6A'],
        },
        {
            'customer_name': 'Aker Solutions',
            'product_type': 'TTR',
            'materials': ['F22', 'AISI 4130'],
            'standards': ['API 6A', 'ASME IX'],
            'testing_requirements': ['RT', 'UT'],
        },
    ]
    merged = _merge_project_metadata(metas)
    assert merged['customer_name'] == 'Aker Solutions'
    assert merged['product_type'] == 'TTR'
    assert set(merged['materials']) == {'Inconel 625', 'F22', 'AISI 4130'}
    assert set(merged['standards']) == {'API 6A', 'ASME IX'}
    assert 'RT' in merged['testing_requirements']


def test_merge_metadata_deduplicates():
    from app.services.metadata_extractor import _merge_project_metadata
    metas = [
        {'materials': ['Inconel 625'], 'standards': ['API 6A']},
        {'materials': ['Inconel 625'], 'standards': ['API 6A']},
    ]
    merged = _merge_project_metadata(metas)
    assert merged['materials'] == ['Inconel 625']
    assert merged['standards'] == ['API 6A']


def test_merge_metadata_invalid_product_type():
    from app.services.metadata_extractor import _merge_project_metadata
    metas = [{'product_type': 'INVALID'}]
    merged = _merge_project_metadata(metas)
    assert merged['product_type'] is None


# --- Admin route tests ---

def test_admin_scan_page(logged_in_client):
    resp = logged_in_client.get('/admin/scan')
    assert resp.status_code == 200
    assert b'Scan Historical Projects' in resp.data


def test_admin_scan_nonexistent_path(logged_in_client):
    resp = logged_in_client.post('/admin/scan', data={
        'scan_path': '/nonexistent/path/here',
        'csrf_token': _get_csrf(logged_in_client),
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'not found' in resp.data.lower() or b'danger' in resp.data.lower()


def test_admin_scan_empty_path(logged_in_client):
    resp = logged_in_client.post('/admin/scan', data={
        'scan_path': '',
        'csrf_token': _get_csrf(logged_in_client),
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_admin_scan_real_directory(app, db, logged_in_client):
    """Scan a temp directory through the admin route."""
    with tempfile.TemporaryDirectory() as tmpdir:
        proj_dir = os.path.join(tmpdir, 'P-2024-099 RouteTest FLANGE')
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, 'spec.pdf'), 'w') as f:
            f.write('test content')

        resp = logged_in_client.post('/admin/scan', data={
            'scan_path': tmpdir,
            'extract_text': '',
            'csrf_token': _get_csrf(logged_in_client),
        })
        assert resp.status_code == 200
        assert b'Scan Results' in resp.data


# --- Helper ---

def _get_csrf(client):
    """Extract CSRF token from a page."""
    resp = client.get('/admin/scan')
    data = resp.data.decode()
    import re
    match = re.search(r'name="csrf_token" value="([^"]+)"', data)
    return match.group(1) if match else ''
