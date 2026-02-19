"""Tests for upload and calculation routes — integration source path."""

import json
import os
import pickle
import pytest
from unittest.mock import patch, MagicMock

from app.extensions import db as _db
from app.models import UploadSession


class TestIntegrationHealthRoute:
    """Tests for GET /upload/integration-health."""

    def test_health_returns_json(self, client, app):
        """Returns JSON with ok/detail keys."""
        with patch('app.upload.routes.IntegrationDataLoader') as MockLoader:
            instance = MockLoader.return_value
            instance.check_health.return_value = {
                'ok': True, 'detail': {'status': 'ok'}
            }
            resp = client.get('/upload/integration-health')

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['ok'] is True

    def test_health_offline(self, client, app):
        """Returns ok=False when API is unreachable."""
        with patch('app.upload.routes.IntegrationDataLoader') as MockLoader:
            instance = MockLoader.return_value
            instance.check_health.return_value = {
                'ok': False, 'detail': 'Connection refused'
            }
            resp = client.get('/upload/integration-health')

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['ok'] is False


class TestFromIntegrationRoute:
    """Tests for POST /upload/from-integration."""

    def _mock_loader_load(self):
        """Return minimal DataFrames dict for mocking."""
        import pandas as pd
        return {
            'valutakurser': pd.DataFrame([{'SEK': 1.0, 'EUR': 11.35,
                                            'DKK': 1.52, 'GBP': 13.2,
                                            'NOK': 0.98, 'USD': 10.5}]),
            'projectadjustments': pd.DataFrame(columns=['Projektnummer']),
            'CO_proj_crossref': pd.DataFrame(columns=['Ordernummer', 'Projekt']),
            'projektuppf': pd.DataFrame(columns=['Projektnummer']),
            'inkoporderforteckning': pd.DataFrame(columns=['Projekt']),
            'kundorderforteckning': pd.DataFrame(columns=['Ordernummer']),
            'kontoplan': pd.DataFrame(),
            'verlista': pd.DataFrame(),
            'tiduppfoljning': pd.DataFrame(columns=['Projektnummer', 'Utfall']),
            'faktureringslogg': pd.DataFrame(columns=['Ordernummer']),
            'Accuredhistory': pd.DataFrame(),
            'gl_summary': {'income_by_project': {}, 'cost_by_project': {}},
        }

    def test_creates_session(self, client, app):
        """Creates an UploadSession with source=integration."""
        with patch('app.upload.routes.IntegrationDataLoader') as MockLoader:
            instance = MockLoader.return_value
            instance.load.return_value = self._mock_loader_load()

            resp = client.post('/upload/from-integration', follow_redirects=False)

        assert resp.status_code == 302  # Redirect to calculation

        with app.app_context():
            session = UploadSession.query.first()
            assert session is not None
            files = json.loads(session.files_json)
            assert files['source'] == 'integration'
            assert session.status == 'validated'

    def test_stores_pickle(self, client, app):
        """Stores pickled DataFrames for later calculation."""
        with patch('app.upload.routes.IntegrationDataLoader') as MockLoader:
            instance = MockLoader.return_value
            instance.load.return_value = self._mock_loader_load()

            client.post('/upload/from-integration')

        with app.app_context():
            session = UploadSession.query.first()
            upload_folder = os.path.join(
                str(app.config['UPLOAD_FOLDER']), session.session_id
            )
            pickle_path = os.path.join(upload_folder, 'integration_data.pkl')
            assert os.path.exists(pickle_path)

            with open(pickle_path, 'rb') as f:
                data = pickle.load(f)
            assert 'projektuppf' in data

    def test_connection_error_redirects(self, client, app):
        """ConnectionError flashes message and redirects to upload page."""
        with patch('app.upload.routes.IntegrationDataLoader') as MockLoader:
            instance = MockLoader.return_value
            instance.load.side_effect = ConnectionError('Connection refused')

            resp = client.post('/upload/from-integration', follow_redirects=True)

        assert resp.status_code == 200
        assert b'Could not connect' in resp.data

    def test_generic_error_redirects(self, client, app):
        """Generic error flashes message and redirects."""
        with patch('app.upload.routes.IntegrationDataLoader') as MockLoader:
            instance = MockLoader.return_value
            instance.load.side_effect = ValueError('Bad data')

            resp = client.post('/upload/from-integration', follow_redirects=True)

        assert resp.status_code == 200
        assert b'Error loading integration data' in resp.data


class TestCalculationRunIntegration:
    """Tests for POST /calculation/run with integration sessions."""

    def _create_integration_session(self, app):
        """Helper: create an integration session with pickled data."""
        import uuid
        import pandas as pd

        session_id = str(uuid.uuid4())

        dfs = {
            'valutakurser': pd.DataFrame([{
                'SEK': 1.0, 'DKK': 1.52, 'EUR': 11.35,
                'GBP': 13.20, 'NOK': 0.98, 'USD': 10.50,
            }]),
            'projectadjustments': pd.DataFrame([{
                'Projektnummer': 'PROJ001',
                'Accured': True,
                'Contingency': 0.05,
                'Incomeadj': 0,
                'Costcalcadj': 0,
                'puradj': 0,
                'Closing': '2026-01-31',
            }]),
            'CO_proj_crossref': pd.DataFrame([
                {'Ordernummer': 1001, 'Projekt': 'PROJ001'},
            ]),
            'projektuppf': pd.DataFrame([{
                'Projektnummer': 'PROJ001',
                'Benamning': 'Alpha',
                'Kundnamn': 'Customer A',
                'Forvan. intakt': 1500000.0,
                'Forvan. kostnad': 1000000.0,
                'Utf., intakt': 300000.0,
                'Utf., kostnad': 500000.0,
            }]),
            'inkoporderforteckning': pd.DataFrame([{
                'Projekt': 'PROJ001',
                'Benamning': 'Steel',
                'Artikelnummer': 'MAT001',
                'Belopp val.': 25000.0,
                'Valuta': 'EUR',
            }]),
            'kundorderforteckning': pd.DataFrame([{
                'Ordernummer': 1001,
                'Restbelopp val.': 50000.0,
                'Valuta': 'EUR',
                'Projekt': 'PROJ001',
            }]),
            'kontoplan': pd.DataFrame(),
            'verlista': pd.DataFrame(),
            'tiduppfoljning': pd.DataFrame([
                {'Projektnummer': 'PROJ001', 'Utfall': 500.0},
            ]),
            'faktureringslogg': pd.DataFrame([{
                'Ordernummer': 1001,
                'Artikel - Artikelnummer': 'F100',
                'Belopp': 100000.0,
                'Belopp val.': 10000.0,
            }]),
            'Accuredhistory': pd.DataFrame(columns=[
                'Projektnummer', 'closing', 'actcost CUR', 'actincome CUR',
                'accured income CUR', 'totalcost CUR', 'totalincome CUR'
            ]),
            'gl_summary': {
                'income_by_project': {'PROJ001': 350000.0},
                'cost_by_project': {'PROJ001': 480000.0},
            },
        }

        upload_folder = os.path.join(
            str(app.config['UPLOAD_FOLDER']), session_id
        )
        os.makedirs(upload_folder, exist_ok=True)
        pickle_path = os.path.join(upload_folder, 'integration_data.pkl')
        with open(pickle_path, 'wb') as f:
            pickle.dump(dfs, f)

        session = UploadSession(
            session_id=session_id,
            files_json=json.dumps({'source': 'integration'}),
            status='validated'
        )
        _db.session.add(session)
        _db.session.commit()
        return session_id

    def test_run_integration_session(self, client, app, db):
        """Running calculation with integration session uses DataFrames."""
        with app.app_context():
            session_id = self._create_integration_session(app)

            resp = client.post('/calculation/run', data={
                'session_id': session_id,
            })

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'success'
        assert data['closing_date'] == '2026-01-31'
        assert data['project_count'] == 1
        assert 'total_accrued' in data
        assert 'total_contingency' in data

    def test_run_updates_session_status(self, client, app, db):
        """Running sets session status to 'calculated'."""
        with app.app_context():
            session_id = self._create_integration_session(app)
            client.post('/calculation/run', data={'session_id': session_id})

            session = UploadSession.query.filter_by(
                session_id=session_id).first()
            assert session.status == 'calculated'
            assert session.closing_date == '2026-01-31'

    def test_store_integration_session(self, client, app, db):
        """Storing integration results persists to FactProjectMonthly."""
        with app.app_context():
            session_id = self._create_integration_session(app)

            # First run
            client.post('/calculation/run', data={'session_id': session_id})

            # Then store
            resp = client.post('/calculation/store',
                               data={'session_id': session_id},
                               follow_redirects=False)

        assert resp.status_code == 302  # Redirect to reports

        with app.app_context():
            from app.models import FactProjectMonthly
            records = FactProjectMonthly.query.filter_by(
                closing_date='2026-01-31').all()
            assert len(records) == 1
            assert records[0].project_number == 'PROJ001'
            assert records[0].actual_income == 350000.0


class TestIsIntegrationSession:
    """Tests for _is_integration_session() helper."""

    def test_integration_session(self, app, db):
        """Detects integration source."""
        from app.calculation.routes import _is_integration_session
        with app.app_context():
            session = UploadSession(
                session_id='test-1',
                files_json=json.dumps({'source': 'integration'}),
                status='validated'
            )
            assert _is_integration_session(session) is True

    def test_file_session(self, app, db):
        """Non-integration session returns False."""
        from app.calculation.routes import _is_integration_session
        with app.app_context():
            session = UploadSession(
                session_id='test-2',
                files_json=json.dumps({
                    'valutakurser': '/path/to/file.xlsx'
                }),
                status='validated'
            )
            assert _is_integration_session(session) is False

    def test_invalid_json(self, app, db):
        """Invalid JSON returns False."""
        from app.calculation.routes import _is_integration_session
        with app.app_context():
            session = UploadSession(
                session_id='test-3',
                files_json='not json',
                status='validated'
            )
            assert _is_integration_session(session) is False

    def test_none_json(self, app, db):
        """None files_json returns False."""
        from app.calculation.routes import _is_integration_session
        with app.app_context():
            session = UploadSession(
                session_id='test-4',
                files_json=None,
                status='validated'
            )
            assert _is_integration_session(session) is False
