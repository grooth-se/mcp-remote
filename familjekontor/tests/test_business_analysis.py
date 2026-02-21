"""Tests for Phase 10H: AI Business Analysis Reports."""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.business_analysis_service import (
    generate_business_analysis,
    _template_profitability,
    _template_liquidity,
    _template_arap,
)


def _setup_company(db, with_accounts=False):
    company = Company(name='Analys AB', org_number='556700-0001', company_type='AB')
    db.session.add(company)
    db.session.commit()
    fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.commit()

    if with_accounts:
        # Create basic accounts for ratio calculations
        accounts = [
            Account(company_id=company.id, account_number='1930', name='Bank', account_type='asset'),
            Account(company_id=company.id, account_number='1510', name='Kundfordringar', account_type='asset'),
            Account(company_id=company.id, account_number='2440', name='Leverantörsskulder', account_type='liability'),
            Account(company_id=company.id, account_number='3010', name='Intäkter', account_type='revenue'),
            Account(company_id=company.id, account_number='4010', name='Varukostnad', account_type='expense'),
            Account(company_id=company.id, account_number='5010', name='Lokalhyra', account_type='expense'),
            Account(company_id=company.id, account_number='2081', name='Eget kapital', account_type='equity'),
        ]
        db.session.add_all(accounts)
        db.session.commit()

    return company, fy


# ---- Service tests ----

class TestGenerateBusinessAnalysis:
    def test_returns_structure(self, db):
        company, fy = _setup_company(db)
        result = generate_business_analysis(company.id, fy.id)
        assert result is not None
        assert 'company' in result
        assert 'fiscal_year' in result
        assert 'sections' in result
        assert 'has_ai' in result

    def test_invalid_company(self, db):
        result = generate_business_analysis(9999, 9999)
        assert result is None

    def test_has_sections(self, db):
        company, fy = _setup_company(db)
        result = generate_business_analysis(company.id, fy.id)
        # At least some sections should be present
        assert isinstance(result['sections'], list)

    def test_ai_flag_false_without_ollama(self, db):
        company, fy = _setup_company(db)
        with patch('app.utils.ai_client.is_ollama_available', return_value=False):
            result = generate_business_analysis(company.id, fy.id)
        assert result['has_ai'] is False

    def test_ai_flag_true_with_ollama(self, db):
        company, fy = _setup_company(db)
        with patch('app.utils.ai_client.is_ollama_available', return_value=True):
            with patch('app.utils.ai_client.generate_text', return_value='AI text'):
                result = generate_business_analysis(company.id, fy.id)
        assert result['has_ai'] is True

    def test_sections_have_required_keys(self, db):
        company, fy = _setup_company(db)
        result = generate_business_analysis(company.id, fy.id)
        for section in result['sections']:
            assert 'key' in section
            assert 'title' in section
            assert 'narrative' in section

    def test_company_in_result(self, db):
        company, fy = _setup_company(db)
        result = generate_business_analysis(company.id, fy.id)
        assert result['company'].name == 'Analys AB'

    def test_fiscal_year_in_result(self, db):
        company, fy = _setup_company(db)
        result = generate_business_analysis(company.id, fy.id)
        assert result['fiscal_year'].year == 2025


class TestTemplateFallbacks:
    def test_profitability_high_margin(self):
        text = _template_profitability(40, 15, 20)
        assert 'god lönsamhet' in text
        assert 'effektiv' in text

    def test_profitability_low_margin(self):
        text = _template_profitability(5, -3, 2)
        assert 'låg' in text
        assert 'Negativ' in text

    def test_profitability_medium_margin(self):
        text = _template_profitability(20, 5, 8)
        assert 'acceptabel' in text

    def test_liquidity_good(self):
        text = _template_liquidity(2.5, 1.5, 100000)
        assert 'god' in text
        assert 'Positivt' in text

    def test_liquidity_poor(self):
        text = _template_liquidity(0.8, 0.5, -50000)
        assert 'likviditetsrisk' in text
        assert 'Negativt' in text

    def test_liquidity_no_cashflow(self):
        text = _template_liquidity(1.5, 1.0, None)
        assert text  # Should still return text

    def test_arap_good_dso(self):
        text = _template_arap(25, 45)
        assert 'effektivt' in text

    def test_arap_high_dso(self):
        text = _template_arap(75, 30)
        assert 'högt' in text

    def test_arap_no_data(self):
        text = _template_arap(None, None)
        assert 'ej tillgängligt' in text


class TestComparisonSection:
    def test_no_prior_year(self, db):
        company, fy = _setup_company(db)
        result = generate_business_analysis(company.id, fy.id)
        comp = next((s for s in result['sections'] if s['key'] == 'comparison'), None)
        if comp:
            assert 'Ingen föregående period' in comp['narrative']


# ---- Route tests ----

class TestBusinessAnalysisRoute:
    def test_no_company(self, logged_in_client, db):
        resp = logged_in_client.get('/report-center/business-analysis', follow_redirects=True)
        assert resp.status_code == 200

    def test_renders(self, logged_in_client, db):
        company = Company(name='Analys AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/report-center/business-analysis')
        assert resp.status_code == 200
        assert 'Affärsanalys' in resp.get_data(as_text=True)

    def test_renders_with_fy_param(self, logged_in_client, db):
        company = Company(name='Analys AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/report-center/business-analysis?fiscal_year_id={fy.id}')
        assert resp.status_code == 200

    def test_pdf_no_weasyprint(self, logged_in_client, db):
        company = Company(name='Analys AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        # Mock weasyprint as unavailable
        with patch('app.services.business_analysis_service.get_business_analysis_pdf', return_value=None):
            resp = logged_in_client.get(
                f'/report-center/business-analysis/pdf?fiscal_year_id={fy.id}',
                follow_redirects=True
            )
            assert resp.status_code == 200

    def test_report_catalog_includes_analysis(self, db):
        from app.services.report_center_service import get_available_reports
        reports = get_available_reports()
        keys = [r['key'] for r in reports]
        assert 'business_analysis' in keys
