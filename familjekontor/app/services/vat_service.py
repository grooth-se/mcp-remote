"""VAT service for reverse charge / export determination and EU VAT validation."""

import re

EU_COUNTRIES = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
    'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
    'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE',
}

# Country-specific VAT number patterns (format-only validation)
VAT_PATTERNS = {
    'AT': r'^ATU\d{8}$',
    'BE': r'^BE0?\d{9,10}$',
    'BG': r'^BG\d{9,10}$',
    'HR': r'^HR\d{11}$',
    'CY': r'^CY\d{8}[A-Z]$',
    'CZ': r'^CZ\d{8,10}$',
    'DK': r'^DK\d{8}$',
    'EE': r'^EE\d{9}$',
    'FI': r'^FI\d{8}$',
    'FR': r'^FR[A-Z0-9]{2}\d{9}$',
    'DE': r'^DE\d{9}$',
    'GR': r'^EL\d{9}$',
    'HU': r'^HU\d{8}$',
    'IE': r'^IE\d{7}[A-Z]{1,2}$',
    'IT': r'^IT\d{11}$',
    'LV': r'^LV\d{11}$',
    'LT': r'^LT\d{9,12}$',
    'LU': r'^LU\d{8}$',
    'MT': r'^MT\d{8}$',
    'NL': r'^NL\d{9}B\d{2}$',
    'PL': r'^PL\d{10}$',
    'PT': r'^PT\d{9}$',
    'RO': r'^RO\d{2,10}$',
    'SK': r'^SK\d{10}$',
    'SI': r'^SI\d{8}$',
    'ES': r'^ES[A-Z0-9]\d{7}[A-Z0-9]$',
    'SE': r'^SE\d{12}$',
}


def get_vat_type_for_customer(country, vat_number=None):
    """Determine VAT type based on customer country and VAT number.

    Returns: 'standard', 'reverse_charge', or 'export'.
    """
    if not country:
        return 'standard'

    country = country.upper().strip()

    # Swedish customer → standard VAT
    if country == 'SE':
        return 'standard'

    # EU customer with valid VAT number → reverse charge
    if country in EU_COUNTRIES and vat_number:
        return 'reverse_charge'

    # EU customer without VAT number → standard (cannot claim reverse charge)
    if country in EU_COUNTRIES and not vat_number:
        return 'standard'

    # Non-EU customer → export (VAT-free)
    return 'export'


def validate_eu_vat_number(vat_number, country=None):
    """Validate EU VAT number format (no external VIES API call).

    Returns dict with 'valid' bool and 'message' string.
    """
    if not vat_number:
        return {'valid': False, 'message': 'Inget momsnummer angivet'}

    vat_clean = vat_number.strip().upper().replace(' ', '').replace('-', '')

    # Try to detect country from prefix
    if not country:
        # First 2 chars might be country code
        prefix = vat_clean[:2]
        if prefix == 'EL':
            country = 'GR'
        elif prefix in VAT_PATTERNS:
            country = prefix
        else:
            return {'valid': False, 'message': 'Kunde inte identifiera land från momsnummer'}

    country = country.upper().strip()

    if country not in VAT_PATTERNS:
        return {'valid': False, 'message': f'Inget mönster definierat för {country}'}

    pattern = VAT_PATTERNS[country]
    if re.match(pattern, vat_clean):
        return {'valid': True, 'message': 'Giltigt format'}
    else:
        return {'valid': False, 'message': f'Ogiltigt format för {country}'}


def get_vat_display_text(vat_type):
    """Get statutory text to display on invoice based on VAT type.

    Returns text string or None for standard VAT.
    """
    if vat_type == 'reverse_charge':
        return 'Omvänd skattskyldighet - Köparen är skyldig att redovisa moms'
    elif vat_type == 'export':
        return 'Momsfri export'
    return None


def compute_invoice_vat(amount_excl_vat, vat_rate, vat_type):
    """Compute VAT amount for an invoice, considering vat_type.

    Returns Decimal VAT amount (0 for reverse_charge/export).
    """
    from decimal import Decimal

    if not amount_excl_vat:
        return Decimal('0')

    amount = Decimal(str(amount_excl_vat))

    if vat_type in ('reverse_charge', 'export'):
        return Decimal('0')

    rate = Decimal(str(vat_rate or 25))
    return (amount * rate / Decimal('100')).quantize(Decimal('0.01'))
