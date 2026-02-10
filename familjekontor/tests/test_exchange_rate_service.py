"""Tests for exchange rate service and model."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest

from app.models.exchange_rate import ExchangeRate
from app.services.exchange_rate_service import (
    fetch_rate_from_riksbanken,
    get_rate,
    get_latest_rate,
    save_manual_rate,
    save_rate_to_db,
)


# === Model tests ===

class TestExchangeRateModel:
    def test_create_exchange_rate(self, db):
        er = ExchangeRate(
            currency_code='EUR',
            rate_date=date(2026, 1, 15),
            rate=Decimal('11.2345'),
            inverse_rate=Decimal('0.089012'),
            source='riksbanken',
        )
        db.session.add(er)
        db.session.commit()

        saved = ExchangeRate.query.first()
        assert saved.currency_code == 'EUR'
        assert saved.rate == Decimal('11.2345')
        assert saved.source == 'riksbanken'

    def test_unique_constraint(self, db):
        er1 = ExchangeRate(currency_code='USD', rate_date=date(2026, 1, 15), rate=Decimal('10.5'))
        db.session.add(er1)
        db.session.commit()

        er2 = ExchangeRate(currency_code='USD', rate_date=date(2026, 1, 15), rate=Decimal('10.6'))
        db.session.add(er2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

    def test_different_dates_ok(self, db):
        er1 = ExchangeRate(currency_code='EUR', rate_date=date(2026, 1, 15), rate=Decimal('11.23'))
        er2 = ExchangeRate(currency_code='EUR', rate_date=date(2026, 1, 16), rate=Decimal('11.25'))
        db.session.add_all([er1, er2])
        db.session.commit()
        assert ExchangeRate.query.count() == 2


# === Riksbanken fetch tests (mocked) ===

class TestFetchFromRiksbanken:
    @patch('app.services.exchange_rate_service.requests.get')
    def test_fetch_success(self, mock_get):
        # API returns 1 SEK = 0.089 EUR → 1 EUR = 11.235955 SEK
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{'value': '0.089000'}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        rate, inverse = fetch_rate_from_riksbanken('EUR', date(2026, 1, 15))
        assert rate > Decimal('11')
        assert inverse == Decimal('0.089000')
        assert str(rate).startswith('11.235')

    @patch('app.services.exchange_rate_service.requests.get')
    def test_fetch_api_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.ConnectionError('Connection refused')

        with pytest.raises(ValueError, match='Kunde inte hämta kurs'):
            fetch_rate_from_riksbanken('EUR', date(2026, 1, 15))

    def test_unsupported_currency(self):
        with pytest.raises(ValueError, match='stöds inte'):
            fetch_rate_from_riksbanken('XYZ', date(2026, 1, 15))

    @patch('app.services.exchange_rate_service.requests.get')
    def test_rate_conversion(self, mock_get):
        # 1 SEK = 0.10 USD → 1 USD = 10.0 SEK
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{'value': '0.100000'}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        rate, inverse = fetch_rate_from_riksbanken('USD', date(2026, 1, 15))
        assert rate == Decimal('10.000000')


# === get_rate tests ===

class TestGetRate:
    def test_sek_returns_one(self, db):
        rate = get_rate('SEK', date(2026, 1, 15))
        assert rate == Decimal('1.0')

    def test_cache_hit(self, db):
        save_rate_to_db('EUR', date(2026, 1, 15), Decimal('11.23'), Decimal('0.089'), 'manual')
        rate = get_rate('EUR', date(2026, 1, 15))
        assert rate == Decimal('11.23')

    @patch('app.services.exchange_rate_service.fetch_rate_from_riksbanken')
    def test_cache_miss_fetches(self, mock_fetch, db):
        mock_fetch.return_value = (Decimal('11.50'), Decimal('0.087'))

        rate = get_rate('EUR', date(2026, 2, 1))
        assert rate == Decimal('11.50')
        # Should be saved to DB
        assert ExchangeRate.query.filter_by(currency_code='EUR', rate_date=date(2026, 2, 1)).first()

    def test_fallback_nearby_date(self, db):
        """When exact date not in DB and API fails, fall back to nearest date within 7 days."""
        save_rate_to_db('USD', date(2026, 1, 14), Decimal('10.50'), Decimal('0.095'), 'manual')

        with patch('app.services.exchange_rate_service.fetch_rate_from_riksbanken', side_effect=ValueError('API error')):
            rate = get_rate('USD', date(2026, 1, 15))
            assert rate == Decimal('10.50')

    def test_no_rate_found_raises(self, db):
        with patch('app.services.exchange_rate_service.fetch_rate_from_riksbanken', side_effect=ValueError('error')):
            with pytest.raises(ValueError, match='Ingen växelkurs'):
                get_rate('GBP', date(2020, 1, 1))


# === Manual rate save ===

class TestSaveManualRate:
    def test_save_manual(self, db):
        er = save_manual_rate('NOK', date(2026, 1, 15), Decimal('1.05'))
        assert er.source == 'manual'
        assert er.rate == Decimal('1.05')
        assert er.inverse_rate is not None

    def test_upsert_updates_existing(self, db):
        save_rate_to_db('EUR', date(2026, 1, 15), Decimal('11.0'), Decimal('0.09'), 'riksbanken')
        save_manual_rate('EUR', date(2026, 1, 15), Decimal('11.5'))

        rates = ExchangeRate.query.filter_by(currency_code='EUR', rate_date=date(2026, 1, 15)).all()
        assert len(rates) == 1
        assert rates[0].rate == Decimal('11.5')
        assert rates[0].source == 'manual'


# === get_latest_rate ===

class TestGetLatestRate:
    def test_sek_returns_one(self, db):
        assert get_latest_rate('SEK') == Decimal('1.0')

    def test_returns_most_recent(self, db):
        save_rate_to_db('EUR', date(2026, 1, 10), Decimal('11.0'), Decimal('0.09'), 'manual')
        save_rate_to_db('EUR', date(2026, 1, 15), Decimal('11.5'), Decimal('0.087'), 'manual')
        assert get_latest_rate('EUR') == Decimal('11.5')
