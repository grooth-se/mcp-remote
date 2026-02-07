"""Multi-currency support with manual exchange rates."""

SUPPORTED_CURRENCIES = {
    'SEK': {'name': 'Svensk krona', 'symbol': 'kr', 'decimals': 2},
    'NOK': {'name': 'Norsk krone', 'symbol': 'kr', 'decimals': 2},
    'EUR': {'name': 'Euro', 'symbol': '€', 'decimals': 2},
    'USD': {'name': 'US Dollar', 'symbol': '$', 'decimals': 2},
}


def currency_choices():
    """Return list of (code, label) for WTForms SelectField."""
    return [(code, f'{code} - {info["name"]}') for code, info in SUPPORTED_CURRENCIES.items()]


def convert_to_sek(amount, currency, exchange_rate):
    """Convert foreign amount to SEK using the given exchange rate."""
    if currency == 'SEK':
        return amount
    return round(amount * exchange_rate, 2)


def format_currency(amount, currency='SEK'):
    """Format amount with currency symbol."""
    info = SUPPORTED_CURRENCIES.get(currency, SUPPORTED_CURRENCIES['SEK'])
    formatted = f'{amount:,.{info["decimals"]}f}'
    if currency == 'SEK':
        return f'{formatted} kr'
    return f'{info["symbol"]}{formatted}'
