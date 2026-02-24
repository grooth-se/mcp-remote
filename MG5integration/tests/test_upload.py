"""Tests for Excel upload routes."""

import io
import os
import shutil
import tempfile

import pytest
from app.models.accounting import Account


@pytest.fixture
def upload_dir(app):
    """Create a temporary upload directory and configure the app to use it."""
    tmpdir = tempfile.mkdtemp()
    app.config['EXCEL_EXPORTS_FOLDER'] = tmpdir
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


def _make_xlsx_bytes(fixtures_dir, name='kontoplan.xlsx'):
    """Read a real fixture file and return its bytes."""
    path = os.path.join(fixtures_dir, name)
    with open(path, 'rb') as f:
        return f.read()


# --- Single upload ---

def test_upload_single_valid(client, db, upload_dir, fixtures_dir):
    """Upload a valid xlsx file for a known table key."""
    data = _make_xlsx_bytes(fixtures_dir, 'kontoplan.xlsx')
    resp = client.post('/admin/upload', data={
        'table_key': 'kontoplan',
        'file': (io.BytesIO(data), 'kontoplan.xlsx'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b'records imported' in resp.data
    assert Account.query.count() > 0


def test_upload_single_invalid_key(client, db, upload_dir, fixtures_dir):
    """Reject upload with unknown table key."""
    data = _make_xlsx_bytes(fixtures_dir, 'kontoplan.xlsx')
    resp = client.post('/admin/upload', data={
        'table_key': 'nonexistent',
        'file': (io.BytesIO(data), 'kontoplan.xlsx'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Invalid table key' in resp.data


def test_upload_single_no_file(client, db, upload_dir):
    """Reject upload with no file selected."""
    resp = client.post('/admin/upload', data={
        'table_key': 'kontoplan',
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b'No file selected' in resp.data


def test_upload_single_non_xlsx(client, db, upload_dir):
    """Reject non-xlsx files."""
    resp = client.post('/admin/upload', data={
        'table_key': 'kontoplan',
        'file': (io.BytesIO(b'not excel'), 'data.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Only .xlsx files' in resp.data


def test_upload_single_replaces_not_duplicates(client, db, upload_dir, fixtures_dir):
    """Uploading the same file twice replaces data, not duplicates it."""
    data = _make_xlsx_bytes(fixtures_dir, 'kontoplan.xlsx')
    client.post('/admin/upload', data={
        'table_key': 'kontoplan',
        'file': (io.BytesIO(data), 'kontoplan.xlsx'),
    }, content_type='multipart/form-data', follow_redirects=True)
    count_first = Account.query.count()

    client.post('/admin/upload', data={
        'table_key': 'kontoplan',
        'file': (io.BytesIO(data), 'kontoplan.xlsx'),
    }, content_type='multipart/form-data', follow_redirects=True)
    count_second = Account.query.count()

    assert count_second == count_first


# --- Multi upload ---

def test_upload_multiple_auto_detect(client, db, upload_dir, fixtures_dir):
    """Upload multiple files and auto-detect by filename."""
    konto_data = _make_xlsx_bytes(fixtures_dir, 'kontoplan.xlsx')
    proj_data = _make_xlsx_bytes(fixtures_dir, 'projektuppf.xlsx')
    resp = client.post('/admin/upload-multiple', data={
        'files': [
            (io.BytesIO(konto_data), 'kontoplan.xlsx'),
            (io.BytesIO(proj_data), 'projektuppf.xlsx'),
        ],
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b'records imported' in resp.data


def test_upload_multiple_unrecognized(client, db, upload_dir):
    """Unrecognized filenames are reported as errors."""
    resp = client.post('/admin/upload-multiple', data={
        'files': [
            (io.BytesIO(b'dummy'), 'random_file.xlsx'),
        ],
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b'unrecognized filename' in resp.data


# --- Dashboard ---

def test_dashboard_shows_upload_forms(client, db):
    """Dashboard renders upload UI elements."""
    resp = client.get('/admin/')
    assert resp.status_code == 200
    assert b'Upload Excel Files' in resp.data
    assert b'upload-multiple' in resp.data
    assert b'upload' in resp.data


def test_dashboard_shows_file_status(client, db, fixtures_dir, app):
    """Dashboard shows file status when source files exist."""
    # TestingConfig points EXCEL_EXPORTS_FOLDER to fixtures_dir which has files
    app.config['EXCEL_EXPORTS_FOLDER'] = fixtures_dir
    resp = client.get('/admin/')
    assert resp.status_code == 200
    # Should show green badges for files that exist
    assert b'bi-check-circle' in resp.data


def test_full_import_still_works(client, db, fixtures_dir, app):
    """The existing full import button still works."""
    app.config['EXCEL_EXPORTS_FOLDER'] = fixtures_dir
    resp = client.post('/admin/import', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Import completed' in resp.data
