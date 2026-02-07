"""Tests for validation utilities."""

from datetime import date
from app.utils.validators import (
    validate_org_number, validate_verification_balance,
    validate_date_in_fiscal_year, format_org_number,
)


def test_valid_org_numbers():
    assert validate_org_number('5566778899') is True
    assert validate_org_number('556677-8899') is True


def test_invalid_org_numbers():
    assert validate_org_number('123') is False
    assert validate_org_number('abcdefghij') is False
    assert validate_org_number('') is False


def test_verification_balance_valid():
    rows = [
        {'debit': 1000, 'credit': 0},
        {'debit': 0, 'credit': 1000},
    ]
    assert validate_verification_balance(rows) is True


def test_verification_balance_invalid():
    rows = [
        {'debit': 1000, 'credit': 0},
        {'debit': 0, 'credit': 500},
    ]
    assert validate_verification_balance(rows) is False


def test_date_in_fiscal_year():
    start = date(2025, 1, 1)
    end = date(2025, 12, 31)
    assert validate_date_in_fiscal_year(date(2025, 6, 15), start, end) is True
    assert validate_date_in_fiscal_year(date(2024, 12, 31), start, end) is False
    assert validate_date_in_fiscal_year(date(2026, 1, 1), start, end) is False


def test_format_org_number():
    assert format_org_number('5566778899') == '556677-8899'
    assert format_org_number('556677-8899') == '556677-8899'
