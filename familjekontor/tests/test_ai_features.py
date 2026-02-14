"""Tests for AI features (Phase 5F) — all external services mocked."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.utils.ai_client import (
    is_ollama_available, get_available_models,
    generate_text, generate_structured, get_ollama_status,
)
from app.services.ai_service import (
    analyze_invoice_text, suggest_account, batch_categorize,
    interpret_financial_query, generate_verksamhetsbeskrivning,
    generate_vasentliga_handelser, _regex_invoice_fallback,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_company(db):
    """Company with accounting data for AI query tests."""
    co = Company(name='AI Test AB', org_number='556600-0070', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    rev = Account(company_id=co.id, account_number='3010', name='Försäljning', account_type='revenue')
    exp = Account(company_id=co.id, account_number='5010', name='Lokalhyra', account_type='expense')
    cash = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')
    db.session.add_all([rev, exp, cash])
    db.session.flush()

    v1 = Verification(company_id=co.id, fiscal_year_id=fy.id,
                      verification_number=1, verification_date=date(2025, 3, 1))
    db.session.add(v1)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v1.id, account_id=cash.id, debit=Decimal('100000'), credit=Decimal('0')),
        VerificationRow(verification_id=v1.id, account_id=rev.id, debit=Decimal('0'), credit=Decimal('100000')),
    ])
    db.session.commit()
    return {'company': co, 'fy': fy}


# ---------------------------------------------------------------------------
# AI Client Tests
# ---------------------------------------------------------------------------

class TestAiClient:
    def test_ollama_disabled_by_default(self, app):
        """Ollama should be disabled in test config."""
        with app.app_context():
            assert is_ollama_available() is False

    def test_get_models_when_disabled(self, app):
        with app.app_context():
            assert get_available_models() == []

    def test_generate_text_when_disabled(self, app):
        with app.app_context():
            result = generate_text('test prompt')
            assert result is None

    def test_generate_structured_when_disabled(self, app):
        with app.app_context():
            result = generate_structured('test prompt')
            assert result is None

    @patch('app.utils.ai_client.current_app')
    def test_ollama_available_with_mock(self, mock_app):
        mock_app.config = {'OLLAMA_ENABLED': True, 'OLLAMA_HOST': 'http://localhost:11434'}

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            assert is_ollama_available() is True

    @patch('app.utils.ai_client.current_app')
    def test_ollama_unavailable_on_error(self, mock_app):
        mock_app.config = {'OLLAMA_ENABLED': True, 'OLLAMA_HOST': 'http://localhost:11434'}

        with patch('urllib.request.urlopen', side_effect=ConnectionError):
            assert is_ollama_available() is False

    def test_get_ollama_status(self, app):
        with app.app_context():
            status = get_ollama_status()
            assert status['enabled'] is False
            assert status['available'] is False
            assert 'host' in status
            assert 'model' in status

    @patch('app.utils.ai_client.current_app')
    def test_generate_text_with_mock(self, mock_app):
        mock_app.config = {
            'OLLAMA_ENABLED': True,
            'OLLAMA_HOST': 'http://localhost:11434',
            'OLLAMA_MODEL': 'llama3.2',
            'OLLAMA_TIMEOUT': 30,
        }

        response_data = b'{"response": "Hej! Jag hj\\u00e4lper dig."}'
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = generate_text('Hej')
            assert result is not None
            assert 'hjälper' in result

    @patch('app.utils.ai_client.current_app')
    def test_generate_structured_parses_json(self, mock_app):
        mock_app.config = {
            'OLLAMA_ENABLED': True,
            'OLLAMA_HOST': 'http://localhost:11434',
            'OLLAMA_MODEL': 'llama3.2',
            'OLLAMA_TIMEOUT': 30,
        }

        response_data = b'{"response": "```json\\n{\\"account_number\\": \\"5010\\", \\"confidence\\": 0.9}\\n```"}'
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = generate_structured('test')
            assert result is not None
            assert result['account_number'] == '5010'


# ---------------------------------------------------------------------------
# Invoice Analysis Tests
# ---------------------------------------------------------------------------

class TestInvoiceAnalysis:
    def test_regex_fallback_extracts_data(self, app):
        with app.app_context():
            text = """Faktura nr: F-2025-001
Org.nr: 556700-1234
Datum: 2025-03-15
Förfallodatum: 2025-04-15
Totalt att betala: 12 500,00 kr
Varav moms: 2 500,00 kr"""

            result = _regex_invoice_fallback(text)
            assert result is not None
            assert result.get('invoice_number') == 'F-2025-001'
            assert result.get('supplier_org_number') == '556700-1234'
            assert result.get('invoice_date') == '2025-03-15'
            assert result.get('due_date') == '2025-04-15'

    def test_regex_fallback_empty_text(self, app):
        with app.app_context():
            assert _regex_invoice_fallback('') is None
            assert _regex_invoice_fallback(None) is None

    def test_analyze_invoice_uses_regex_when_ai_disabled(self, app):
        with app.app_context():
            text = 'Fakturanr: 12345\n556600-0001\nTotalt: 5000 kr'
            result = analyze_invoice_text(text)
            assert result is not None
            assert 'invoice_number' in result

    def test_analyze_invoice_no_text(self, app):
        with app.app_context():
            result = analyze_invoice_text('')
            assert result is None


# ---------------------------------------------------------------------------
# Account Suggestion Tests
# ---------------------------------------------------------------------------

class TestAccountSuggestion:
    def test_suggest_rent(self, app):
        with app.app_context():
            result = suggest_account('Lokalhyra kontor mars')
            assert result is not None
            assert result['account_number'] == '5010'

    def test_suggest_insurance(self, app):
        with app.app_context():
            result = suggest_account('Företagsförsäkring 2025')
            assert result is not None
            assert result['account_number'] == '6310'

    def test_suggest_phone(self, app):
        with app.app_context():
            result = suggest_account('Telefoni Telia mobilabonnemang')
            assert result is not None
            assert result['account_number'] == '5060'

    def test_suggest_software(self, app):
        with app.app_context():
            result = suggest_account('Microsoft 365 licens')
            assert result is not None
            assert result['account_number'] == '5420'

    def test_suggest_unknown_returns_none(self, app):
        with app.app_context():
            result = suggest_account('xyzabc123')
            assert result is None

    def test_suggest_empty_returns_none(self, app):
        with app.app_context():
            result = suggest_account('')
            assert result is None

    def test_batch_categorize(self, app):
        with app.app_context():
            txns = [
                {'description': 'Lokalhyra januari', 'amount': -15000},
                {'description': 'Ränteintäkt', 'amount': 500},
                {'description': 'Unknown xyz', 'amount': -100},
            ]
            results = batch_categorize(txns)
            assert len(results) == 3
            assert results[0] is not None
            assert results[0]['account_number'] == '5010'
            assert results[1] is not None
            assert results[1]['account_number'] == '8310'
            assert results[2] is None


# ---------------------------------------------------------------------------
# NL Query Tests
# ---------------------------------------------------------------------------

class TestNLQuery:
    def test_query_about_pnl(self, app):
        with app.app_context():
            result = interpret_financial_query('Vad är årets resultat?')
            assert result['query_type'] == 'pnl'
            assert 'Resultaträkning' in result['answer']

    def test_query_about_balance(self, app):
        with app.app_context():
            result = interpret_financial_query('Hur ser balansräkningen ut?')
            assert result['query_type'] == 'balance'

    def test_query_about_vat(self, app):
        with app.app_context():
            result = interpret_financial_query('Hur mycket moms?')
            assert result['query_type'] == 'vat'

    def test_query_about_tax(self, app):
        with app.app_context():
            result = interpret_financial_query('Hur mycket bolagsskatt?')
            assert result['query_type'] == 'tax'

    def test_query_about_salary(self, app):
        with app.app_context():
            result = interpret_financial_query('Hur mycket löner?')
            assert result['query_type'] == 'salary'

    def test_query_about_invoices(self, app):
        with app.app_context():
            result = interpret_financial_query('Vilka fakturor?')
            assert result['query_type'] == 'invoices'

    def test_general_query(self, app):
        with app.app_context():
            result = interpret_financial_query('Berätta något')
            assert result['query_type'] == 'general'

    def test_empty_query(self, app):
        with app.app_context():
            result = interpret_financial_query('')
            assert result['query_type'] == 'empty'

    def test_query_with_company_data(self, app):
        with app.app_context():
            data = {'revenue': 500000, 'net_income': 100000}
            result = interpret_financial_query('Vad är vinsten?', company_data=data)
            assert result['query_type'] == 'pnl'
            assert '100' in result['answer']


# ---------------------------------------------------------------------------
# Annual Report Text Generation Tests
# ---------------------------------------------------------------------------

class TestAnnualReportText:
    def test_verksamhetsbeskrivning_fallback(self, app):
        with app.app_context():
            result = generate_verksamhetsbeskrivning(
                'Test AB', 2025,
                {'revenue': 1000000, 'net_income': 150000}
            )
            assert 'Test AB' in result
            assert '2025' in result
            assert 'positivt' in result

    def test_verksamhetsbeskrivning_negative_result(self, app):
        with app.app_context():
            result = generate_verksamhetsbeskrivning(
                'Förlust AB', 2025,
                {'revenue': 500000, 'net_income': -50000}
            )
            assert 'negativt' in result

    def test_vasentliga_handelser_fallback(self, app):
        with app.app_context():
            result = generate_vasentliga_handelser(
                'Test AB', 2025,
                {'revenue': 1000000}
            )
            assert '2025' in result


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestAIRoutes:
    def test_ai_index(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/ai/')
        assert resp.status_code == 200
        assert 'AI Assistent' in resp.data.decode()

    def test_ai_status_page(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/ai/status')
        assert resp.status_code == 200
        assert 'Ollama' in resp.data.decode()

    def test_ai_query_endpoint(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/ai/query',
                                     json={'query': 'Vad är resultatet?'},
                                     content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'answer' in data
        assert data['query_type'] == 'pnl'

    def test_ai_suggest_account_endpoint(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/ai/suggest-account',
                                     json={'description': 'Lokalhyra mars'},
                                     content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['account_number'] == '5010'

    def test_ai_suggest_account_unknown(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/ai/suggest-account',
                                     json={'description': 'xyzabc'},
                                     content_type='application/json')
        assert resp.status_code == 404

    def test_ai_analyze_invoice(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/ai/analyze-invoice',
                                     json={'text': 'Fakturanr: 123\n556600-0001'},
                                     content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'invoice_number' in data

    def test_ai_analyze_invoice_empty(self, logged_in_client, ai_company):
        co = ai_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/ai/analyze-invoice',
                                     json={'text': ''},
                                     content_type='application/json')
        assert resp.status_code == 400
