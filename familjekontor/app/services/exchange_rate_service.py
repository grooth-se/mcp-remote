"""Exchange rate service — fetch rates from Riksbanken and manage DB cache."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
import requests

from app.extensions import db
from app.models.exchange_rate import ExchangeRate

logger = logging.getLogger(__name__)

# Riksbanken SWEA API series IDs (1 SEK = X foreign)
RIKSBANKEN_SERIES = {
    'EUR': 'SEKEURPMI',
    'USD': 'SEKUSDPMI',
    'NOK': 'SEKNOKPMI',
    'DKK': 'SEKDKKPMI',
    'GBP': 'SEKGBPPMI',
}

RIKSBANKEN_BASE_URL = 'https://api.riksbank.se/swea/v1/Observations'


def fetch_rate_from_riksbanken(currency_code, rate_date):
    """Fetch exchange rate from Riksbanken SWEA API.

    The API returns 1 SEK = X foreign (inverse_rate).
    We store rate as 1 foreign = X SEK.
    Returns (rate, inverse_rate) or raises ValueError.
    """
    series_id = RIKSBANKEN_SERIES.get(currency_code.upper())
    if not series_id:
        raise ValueError(f'Valuta {currency_code} stöds inte av Riksbanken')

    date_str = rate_date.strftime('%Y-%m-%d')
    url = f'{RIKSBANKEN_BASE_URL}/{series_id}/{date_str}'

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            raise ValueError(f'Ingen kurs från Riksbanken för {currency_code} {date_str}')

        # API returns list of observations
        obs = data[0] if isinstance(data, list) else data
        api_value = Decimal(str(obs['value']))

        if api_value <= 0:
            raise ValueError(f'Ogiltig kurs från Riksbanken: {api_value}')

        # API returns 1 foreign = X SEK (e.g. 1 EUR = 10.65 SEK)
        rate = api_value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        inverse_rate = (Decimal('1') / api_value).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)

        return rate, inverse_rate

    except requests.RequestException as e:
        logger.warning(f'Riksbanken API error for {currency_code} {date_str}: {e}')
        raise ValueError(f'Kunde inte hämta kurs från Riksbanken: {e}')


def get_rate(currency_code, rate_date):
    """Get exchange rate for currency on date (1 foreign = X SEK).

    Checks DB cache first, then fetches from Riksbanken.
    Falls back to nearest date within 7 days if exact date not available.
    Returns Decimal('1.0') for SEK.
    """
    if currency_code == 'SEK':
        return Decimal('1.0')

    # Check DB cache
    cached = ExchangeRate.query.filter_by(
        currency_code=currency_code, rate_date=rate_date
    ).first()
    if cached:
        return Decimal(str(cached.rate))

    # Try fetching from Riksbanken
    try:
        rate, inverse_rate = fetch_rate_from_riksbanken(currency_code, rate_date)
        save_rate_to_db(currency_code, rate_date, rate, inverse_rate, source='riksbanken')
        return rate
    except ValueError:
        pass

    # Fallback: find nearest rate within 7 days
    for delta in range(1, 8):
        for d in [rate_date - timedelta(days=delta), rate_date + timedelta(days=delta)]:
            cached = ExchangeRate.query.filter_by(
                currency_code=currency_code, rate_date=d
            ).first()
            if cached:
                return Decimal(str(cached.rate))

    raise ValueError(f'Ingen växelkurs hittades för {currency_code} nära {rate_date}')


def get_latest_rate(currency_code):
    """Get the most recent rate for a currency."""
    if currency_code == 'SEK':
        return Decimal('1.0')

    cached = ExchangeRate.query.filter_by(
        currency_code=currency_code
    ).order_by(ExchangeRate.rate_date.desc()).first()

    if cached:
        return Decimal(str(cached.rate))

    # Try today
    return get_rate(currency_code, date.today())


def save_manual_rate(currency_code, rate_date, rate):
    """Save a manually entered exchange rate."""
    rate = Decimal(str(rate))
    inverse_rate = (Decimal('1') / rate).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    return save_rate_to_db(currency_code, rate_date, rate, inverse_rate, source='manual')


def save_rate_to_db(currency_code, rate_date, rate, inverse_rate, source='riksbanken'):
    """Save rate to DB, updating if already exists."""
    existing = ExchangeRate.query.filter_by(
        currency_code=currency_code, rate_date=rate_date
    ).first()

    if existing:
        existing.rate = rate
        existing.inverse_rate = inverse_rate
        existing.source = source
    else:
        existing = ExchangeRate(
            currency_code=currency_code,
            rate_date=rate_date,
            rate=rate,
            inverse_rate=inverse_rate,
            source=source,
        )
        db.session.add(existing)

    db.session.commit()
    return existing


def fetch_rates_for_range(currency_code, start_date, end_date):
    """Fetch rates for a date range from Riksbanken."""
    fetched = 0
    current = start_date
    while current <= end_date:
        # Skip weekends
        if current.weekday() < 5:
            try:
                rate, inverse_rate = fetch_rate_from_riksbanken(currency_code, current)
                save_rate_to_db(currency_code, current, rate, inverse_rate, source='riksbanken')
                fetched += 1
            except ValueError:
                pass
        current += timedelta(days=1)
    return fetched
