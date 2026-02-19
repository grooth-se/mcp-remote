"""Tests for IntegrationDataLoader — API to DataFrame conversion."""

import json
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from app.calculation.services.integration_loader import IntegrationDataLoader
from app.models import FactProjectMonthly
from tests.conftest import (
    build_sample_api_response,
    SAMPLE_EXCHANGE_RATES,
    SAMPLE_PROJECTS,
    SAMPLE_ADJUSTMENTS,
    SAMPLE_CO_MAP,
    SAMPLE_CUSTOMER_ORDERS,
    SAMPLE_PURCHASE_ORDERS,
    SAMPLE_TIME_TRACKING,
    SAMPLE_INVOICES,
    SAMPLE_GL_SUMMARY,
)


class TestHealthCheck:
    """Tests for check_health()."""

    def test_health_ok(self, app):
        """Health check returns ok when API is reachable."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                'status': 'ok', 'total_records': 100
            }).encode()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch('urllib.request.urlopen', return_value=mock_response):
                loader = IntegrationDataLoader('http://test:5001')
                result = loader.check_health()

            assert result['ok'] is True
            assert result['detail']['status'] == 'ok'

    def test_health_offline(self, app):
        """Health check returns not ok when API is unreachable."""
        with app.app_context():
            with patch('urllib.request.urlopen', side_effect=Exception('Connection refused')):
                loader = IntegrationDataLoader('http://test:5001')
                result = loader.check_health()

            assert result['ok'] is False
            assert 'Connection refused' in result['detail']


class TestFetchApiData:
    """Tests for fetch_api_data()."""

    def test_fetch_success(self, app):
        """Fetches and parses JSON from API."""
        with app.app_context():
            api_data = build_sample_api_response()
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(api_data).encode()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch('urllib.request.urlopen', return_value=mock_response):
                loader = IntegrationDataLoader('http://test:5001')
                result = loader.fetch_api_data()

            assert 'projects' in result
            assert 'gl_summary' in result
            assert len(result['projects']) == 2

    def test_fetch_connection_error(self, app):
        """Raises ConnectionError when API is unreachable."""
        with app.app_context():
            import urllib.error
            with patch('urllib.request.urlopen',
                       side_effect=urllib.error.URLError('Connection refused')):
                loader = IntegrationDataLoader('http://test:5001')
                with pytest.raises(ConnectionError, match='Could not connect'):
                    loader.fetch_api_data()


class TestBuildExchangeRates:
    """Tests for _build_exchange_rates()."""

    def test_with_rates(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_exchange_rates(SAMPLE_EXCHANGE_RATES)

        assert len(df) == 1
        assert df['SEK'].iloc[0] == 1.0
        assert df['EUR'].iloc[0] == 11.35
        assert df['DKK'].iloc[0] == 1.52
        assert df['GBP'].iloc[0] == 13.20
        assert df['NOK'].iloc[0] == 0.98
        assert df['USD'].iloc[0] == 10.50

    def test_with_no_rates(self, app):
        """Returns default rates when API has no data."""
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_exchange_rates(None)

        assert len(df) == 1
        assert df['SEK'].iloc[0] == 1.0
        assert df['EUR'].iloc[0] == 1.0


class TestBuildAdjustments:
    """Tests for _build_adjustments()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_adjustments(SAMPLE_ADJUSTMENTS)

        assert list(df.columns) == [
            'Projektnummer', 'Accured', 'Contingency',
            'Incomeadj', 'Costcalcadj', 'puradj', 'Closing'
        ]
        assert len(df) == 2
        assert df.iloc[0]['Projektnummer'] == 'PROJ001'
        assert df.iloc[0]['Accured'] == True
        assert df.iloc[0]['Contingency'] == 0.05
        assert df.iloc[1]['Incomeadj'] == 5000

    def test_empty_adjustments(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_adjustments([])

        assert len(df) == 0
        assert 'Projektnummer' in df.columns


class TestBuildCOProjectMap:
    """Tests for _build_co_project_map()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_co_project_map(SAMPLE_CO_MAP)

        assert list(df.columns) == ['Ordernummer', 'Projekt']
        assert len(df) == 2
        assert df.iloc[0]['Ordernummer'] == 1001
        assert df.iloc[0]['Projekt'] == 'PROJ001'


class TestBuildProjects:
    """Tests for _build_projects()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_projects(SAMPLE_PROJECTS)

        assert 'Projektnummer' in df.columns
        assert 'Benamning' in df.columns
        assert 'Kundnamn' in df.columns
        assert 'Forvan. intakt' in df.columns
        assert 'Forvan. kostnad' in df.columns
        assert 'Utf., intakt' in df.columns
        assert 'Utf., kostnad' in df.columns
        assert len(df) == 2

    def test_values(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_projects(SAMPLE_PROJECTS)

        row = df.iloc[0]
        assert row['Projektnummer'] == 'PROJ001'
        assert row['Benamning'] == 'Test Project Alpha'
        assert row['Forvan. intakt'] == 1500000.0
        assert row['Forvan. kostnad'] == 1000000.0
        assert row['Utf., intakt'] == 300000.0
        assert row['Utf., kostnad'] == 500000.0


class TestBuildPurchaseOrders:
    """Tests for _build_purchase_orders()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_purchase_orders(SAMPLE_PURCHASE_ORDERS)

        assert 'Projekt' in df.columns
        assert 'Benamning' in df.columns
        assert 'Artikelnummer' in df.columns
        assert 'Belopp val.' in df.columns
        assert 'Valuta' in df.columns
        assert len(df) == 1
        assert df.iloc[0]['Valuta'] == 'EUR'
        assert df.iloc[0]['Belopp val.'] == 25000.0


class TestBuildCustomerOrders:
    """Tests for _build_customer_orders()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_customer_orders(SAMPLE_CUSTOMER_ORDERS)

        assert 'Ordernummer' in df.columns
        assert 'Restbelopp val.' in df.columns
        assert 'Valuta' in df.columns
        assert 'Projekt' in df.columns
        assert len(df) == 1
        assert df.iloc[0]['Restbelopp val.'] == 50000.0
        assert df.iloc[0]['Valuta'] == 'EUR'


class TestBuildTimeTracking:
    """Tests for _build_time_tracking()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_time_tracking(SAMPLE_TIME_TRACKING)

        assert list(df.columns) == ['Projektnummer', 'Utfall']
        assert len(df) == 2
        assert df.iloc[0]['Utfall'] == 500.0
        assert df.iloc[1]['Utfall'] == 200.0


class TestBuildInvoiceLog:
    """Tests for _build_invoice_log()."""

    def test_column_mapping(self, app):
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_invoice_log(SAMPLE_INVOICES)

        assert 'Ordernummer' in df.columns
        assert 'Artikel - Artikelnummer' in df.columns
        assert 'Belopp' in df.columns
        assert 'Belopp val.' in df.columns
        assert len(df) == 1
        assert df.iloc[0]['Artikel - Artikelnummer'] == 'F100'


class TestBuildAccruedHistory:
    """Tests for _build_accrued_history() from DB."""

    def test_empty_history(self, app, db):
        """Returns empty DataFrame with expected columns when no history."""
        with app.app_context():
            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_accrued_history()

        assert len(df) == 0
        assert 'Projektnummer' in df.columns
        assert 'closing' in df.columns
        assert 'accured income CUR' in df.columns

    def test_history_from_db(self, app, db):
        """Builds history DataFrame from FactProjectMonthly records."""
        with app.app_context():
            record = FactProjectMonthly(
                closing_date='2025-12-31',
                project_number='PROJ001',
                project_name='Alpha',
                customer_name='Customer A',
                expected_income=1500000,
                expected_cost=1000000,
                actual_income=350000,
                actual_cost=480000,
                accrued_income_cur=75000,
                contingency_cur=3750,
                total_income_cur=900000,
                total_cost_cur=750000,
                actual_income_cur=350000,
                actual_cost_cur=480000,
                include_in_accrued=True,
                contingency_factor=0.05,
            )
            db.session.add(record)
            db.session.commit()

            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_accrued_history()

        assert len(df) == 1
        assert df.iloc[0]['Projektnummer'] == 'PROJ001'
        assert df.iloc[0]['closing'] == '2025-12-31'
        assert df.iloc[0]['act income'] == 350000
        assert df.iloc[0]['accured income CUR'] == 75000
        assert df.iloc[0]['incl'] == True

    def test_multiple_periods(self, app, db):
        """Builds history with multiple closing dates."""
        with app.app_context():
            for date in ['2025-10-31', '2025-11-30', '2025-12-31']:
                db.session.add(FactProjectMonthly(
                    closing_date=date,
                    project_number='PROJ001',
                    project_name='Alpha',
                    accrued_income_cur=50000,
                ))
            db.session.commit()

            loader = IntegrationDataLoader('http://test:5001')
            df = loader._build_accrued_history()

        assert len(df) == 3
        # Should be ordered by closing_date
        assert df.iloc[0]['closing'] == '2025-10-31'
        assert df.iloc[2]['closing'] == '2025-12-31'


class TestFullLoad:
    """Tests for load() — full API fetch and conversion."""

    def test_load_returns_all_dataframes(self, app, db):
        """load() returns dict with all expected DataFrame keys."""
        with app.app_context():
            api_data = build_sample_api_response()
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(api_data).encode()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch('urllib.request.urlopen', return_value=mock_response):
                loader = IntegrationDataLoader('http://test:5001')
                dfs = loader.load()

        expected_keys = {
            'valutakurser', 'projectadjustments', 'CO_proj_crossref',
            'projektuppf', 'inkoporderforteckning', 'kundorderforteckning',
            'kontoplan', 'verlista', 'tiduppfoljning', 'faktureringslogg',
            'Accuredhistory', 'gl_summary',
        }
        assert set(dfs.keys()) == expected_keys

    def test_load_gl_summary_is_dict(self, app, db):
        """gl_summary is passed through as a dict, not a DataFrame."""
        with app.app_context():
            api_data = build_sample_api_response()
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(api_data).encode()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch('urllib.request.urlopen', return_value=mock_response):
                loader = IntegrationDataLoader('http://test:5001')
                dfs = loader.load()

        assert isinstance(dfs['gl_summary'], dict)
        assert 'income_by_project' in dfs['gl_summary']
        assert dfs['gl_summary']['income_by_project']['PROJ001'] == 350000.0

    def test_load_kontoplan_empty(self, app, db):
        """kontoplan is an empty DataFrame (not used in calculation)."""
        with app.app_context():
            api_data = build_sample_api_response()
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(api_data).encode()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch('urllib.request.urlopen', return_value=mock_response):
                loader = IntegrationDataLoader('http://test:5001')
                dfs = loader.load()

        assert isinstance(dfs['kontoplan'], pd.DataFrame)
        assert len(dfs['kontoplan']) == 0

    def test_load_connection_error(self, app, db):
        """load() raises ConnectionError on network failure."""
        with app.app_context():
            import urllib.error
            with patch('urllib.request.urlopen',
                       side_effect=urllib.error.URLError('refused')):
                loader = IntegrationDataLoader('http://test:5001')
                with pytest.raises(ConnectionError):
                    loader.load()
