"""Validation utilities for Swedish business data."""

from datetime import date


def validate_org_number(org_number: str) -> bool:
    """Validate Swedish organization number using Luhn algorithm.

    Format: NNNNNN-NNNN (10 digits, optionally with hyphen).
    """
    cleaned = org_number.replace('-', '').replace(' ', '')
    if len(cleaned) != 10 or not cleaned.isdigit():
        return False

    # Luhn check on last 10 digits
    digits = [int(d) for d in cleaned]
    checksum = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def validate_verification_balance(rows) -> bool:
    """Check that total debits equal total credits in a verification."""
    total_debit = sum(r.get('debit', 0) or 0 for r in rows)
    total_credit = sum(r.get('credit', 0) or 0 for r in rows)
    return abs(total_debit - total_credit) < 0.01


def validate_date_in_fiscal_year(check_date: date, start_date: date, end_date: date) -> bool:
    """Check that a date falls within a fiscal year."""
    return start_date <= check_date <= end_date


def format_org_number(org_number: str) -> str:
    """Format org number as NNNNNN-NNNN."""
    cleaned = org_number.replace('-', '').replace(' ', '')
    if len(cleaned) == 10:
        return f'{cleaned[:6]}-{cleaned[6:]}'
    return org_number
