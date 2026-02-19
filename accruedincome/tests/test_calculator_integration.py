"""Tests for calculator integration path — load_from_dataframes() and GL summary."""

import os
import json
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from app.calculation.services.calculator import AccruedIncomeCalculator
from tests.conftest import (
    build_sample_api_response,
    SAMPLE_GL_SUMMARY,
)


def _build_minimal_dataframes():
    """Build minimal DataFrames that pass through the full calculator pipeline.

    Returns dict matching what IntegrationDataLoader.load() produces.
    """
    dfs = {}

    dfs['valutakurser'] = pd.DataFrame([{
        'SEK': 1.0, 'DKK': 1.52, 'EUR': 11.35,
        'GBP': 13.20, 'NOK': 0.98, 'USD': 10.50,
    }])

    dfs['projectadjustments'] = pd.DataFrame([
        {
            'Projektnummer': 'PROJ001',
            'Accured': True,
            'Contingency': 0.05,
            'Incomeadj': 0,
            'Costcalcadj': 0,
            'puradj': 0,
            'Closing': '2026-01-31',
        },
        {
            'Projektnummer': 'PROJ002',
            'Accured': True,
            'Contingency': 0.10,
            'Incomeadj': 5000,
            'Costcalcadj': 0,
            'puradj': 0,
            'Closing': '2026-01-31',
        },
    ])

    dfs['CO_proj_crossref'] = pd.DataFrame([
        {'Ordernummer': 1001, 'Projekt': 'PROJ001'},
        {'Ordernummer': 1002, 'Projekt': 'PROJ002'},
    ])

    dfs['projektuppf'] = pd.DataFrame([
        {
            'Projektnummer': 'PROJ001',
            'Benamning': 'Alpha',
            'Kundnamn': 'Customer A',
            'Forvan. intakt': 1500000.0,
            'Forvan. kostnad': 1000000.0,
            'Utf., intakt': 300000.0,
            'Utf., kostnad': 500000.0,
        },
        {
            'Projektnummer': 'PROJ002',
            'Benamning': 'Beta',
            'Kundnamn': 'Customer B',
            'Forvan. intakt': 600000.0,
            'Forvan. kostnad': 400000.0,
            'Utf., intakt': 100000.0,
            'Utf., kostnad': 200000.0,
        },
    ])

    dfs['inkoporderforteckning'] = pd.DataFrame([
        {
            'Projekt': 'PROJ001',
            'Benamning': 'Steel plates',
            'Artikelnummer': 'MAT001',
            'Belopp val.': 25000.0,
            'Valuta': 'EUR',
        },
    ])

    dfs['kundorderforteckning'] = pd.DataFrame([
        {
            'Ordernummer': 1001,
            'Restbelopp val.': 50000.0,
            'Valuta': 'EUR',
            'Projekt': 'PROJ001',
        },
    ])

    dfs['kontoplan'] = pd.DataFrame()
    dfs['verlista'] = pd.DataFrame()

    dfs['tiduppfoljning'] = pd.DataFrame([
        {'Projektnummer': 'PROJ001', 'Utfall': 500.0},
        {'Projektnummer': 'PROJ002', 'Utfall': 200.0},
    ])

    dfs['faktureringslogg'] = pd.DataFrame([
        {
            'Ordernummer': 1001,
            'Artikel - Artikelnummer': 'F100',
            'Belopp': 100000.0,
            'Belopp val.': 10000.0,
        },
    ])

    dfs['Accuredhistory'] = pd.DataFrame(columns=[
        'Projektnummer', 'closing', 'actcost CUR', 'actincome CUR',
        'accured income CUR', 'totalcost CUR', 'totalincome CUR'
    ])

    dfs['gl_summary'] = {
        'income_by_project': {'PROJ001': 350000.0, 'PROJ002': 120000.0},
        'cost_by_project': {'PROJ001': 480000.0, 'PROJ002': 190000.0},
    }

    return dfs


class TestLoadFromDataframes:
    """Tests for load_from_dataframes()."""

    def test_sets_dataframes(self, app):
        """Stores DataFrames on calculator instance."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            dfs = _build_minimal_dataframes()
            calc.load_from_dataframes(dfs)

        assert 'projektuppf' in calc.dataframes
        assert 'valutakurser' in calc.dataframes
        assert len(calc.dataframes['projektuppf']) == 2

    def test_extracts_gl_summary(self, app):
        """Extracts gl_summary from dataframes dict into _gl_summary."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            dfs = _build_minimal_dataframes()
            calc.load_from_dataframes(dfs)

        assert calc._gl_summary is not None
        assert 'income_by_project' in calc._gl_summary
        assert 'gl_summary' not in calc.dataframes

    def test_no_gl_summary(self, app):
        """Works without gl_summary key."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            dfs = _build_minimal_dataframes()
            del dfs['gl_summary']
            calc.load_from_dataframes(dfs)

        assert calc._gl_summary is None


class TestExtractActualFromGLIntegration:
    """Tests for extract_actual_from_gl() with pre-aggregated data."""

    def test_uses_gl_summary(self, app):
        """Uses pre-aggregated GL data when available."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            dfs = _build_minimal_dataframes()
            calc.load_from_dataframes(dfs)

            # Simulate pipeline up to extract_actual_from_gl
            calc.revaluate_purchase_orders()
            calc.apply_project_adjustments()
            calc.calculate_basic_metrics()
            calc.extract_actual_from_gl()

        df = calc.dataframes['projektuppf']
        # PROJ001 should have income=350000, cost=480000 from GL summary
        proj001 = df.loc['PROJ001']
        assert proj001['act income'] == 350000.0
        assert proj001['act cost'] == 480000.0

        proj002 = df.loc['PROJ002']
        assert proj002['act income'] == 120000.0
        assert proj002['act cost'] == 190000.0

    def test_missing_project_in_gl_gets_zero(self, app):
        """Projects not in GL summary get 0 for income/cost."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            dfs = _build_minimal_dataframes()
            # Remove PROJ002 from GL summary
            dfs['gl_summary']['income_by_project'] = {'PROJ001': 350000.0}
            dfs['gl_summary']['cost_by_project'] = {'PROJ001': 480000.0}
            calc.load_from_dataframes(dfs)

            calc.revaluate_purchase_orders()
            calc.apply_project_adjustments()
            calc.calculate_basic_metrics()
            calc.extract_actual_from_gl()

        df = calc.dataframes['projektuppf']
        proj002 = df.loc['PROJ002']
        assert proj002['act income'] == 0
        assert proj002['act cost'] == 0

    def test_falls_back_to_verlista(self, app):
        """Falls back to raw verlista when no GL summary."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            dfs = _build_minimal_dataframes()
            del dfs['gl_summary']

            # Provide verlista data for fallback path
            dfs['verlista'] = pd.DataFrame([
                {'Konto': 3010, 'Proj.': 'PROJ001', 'Debet': 0, 'Kredit': 100000},
                {'Konto': 4010, 'Proj.': 'PROJ001', 'Debet': 80000, 'Kredit': 0},
            ])
            calc.load_from_dataframes(dfs)

            calc.revaluate_purchase_orders()
            calc.apply_project_adjustments()
            calc.calculate_basic_metrics()
            calc.extract_actual_from_gl()

        df = calc.dataframes['projektuppf']
        proj001 = df.loc['PROJ001']
        assert proj001['act income'] == 100000.0  # credit - debit
        assert proj001['act cost'] == 80000.0      # debit - credit


class TestRunWithDataframes:
    """Tests for run(dataframes=...) full pipeline."""

    def test_run_with_dataframes(self, app, db):
        """Full pipeline runs with pre-built DataFrames."""
        with app.app_context():
            output_folder = str(app.config['OUTPUT_FOLDER'])
            calc = AccruedIncomeCalculator({}, output_folder)
            dfs = _build_minimal_dataframes()

            result_df, closing_date = calc.run(dataframes=dfs)

        assert result_df is not None
        assert len(result_df) == 2
        assert closing_date == '2026-01-31'
        assert 'accured income CUR' in result_df.columns
        assert 'contingency CUR' in result_df.columns

    def test_run_produces_valid_results(self, app, db):
        """Results have expected structure and values."""
        with app.app_context():
            output_folder = str(app.config['OUTPUT_FOLDER'])
            calc = AccruedIncomeCalculator({}, output_folder)
            dfs = _build_minimal_dataframes()

            result_df, _ = calc.run(dataframes=dfs)

        # Both projects should be present (index = project number)
        assert 'PROJ001' in result_df.index
        assert 'PROJ002' in result_df.index

        # GL values should come from gl_summary
        assert result_df.loc['PROJ001', 'act income'] == 350000.0
        assert result_df.loc['PROJ001', 'act cost'] == 480000.0

    def test_run_creates_output_files(self, app, db):
        """Run creates Excel report and history files."""
        with app.app_context():
            output_folder = str(app.config['OUTPUT_FOLDER'])
            calc = AccruedIncomeCalculator({}, output_folder)
            dfs = _build_minimal_dataframes()

            _, closing_date = calc.run(dataframes=dfs)

            report_path = os.path.join(output_folder, f'{closing_date}_report.xlsx')
            history_path = os.path.join(output_folder, f'{closing_date}_accuredhistory.xlsx')
            assert os.path.exists(report_path)
            assert os.path.exists(history_path)

    def test_run_without_dataframes_uses_files(self, app):
        """run() without dataframes arg calls load_files()."""
        with app.app_context():
            calc = AccruedIncomeCalculator({}, '/tmp/test')
            with patch.object(calc, 'load_files') as mock_load:
                mock_load.side_effect = Exception('Expected: load_files called')
                with pytest.raises(Exception, match='load_files called'):
                    calc.run()
