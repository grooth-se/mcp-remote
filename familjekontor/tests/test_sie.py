"""Tests for SIE4 parser and handler."""

from datetime import date
from decimal import Decimal
from app.services.sie_handler import SIEParser, _account_type_from_number


def test_sie_parser_basic():
    content = """#FLAGGA 0
#PROGRAM "TestProgram" "1.0"
#FORMAT PC8
#GEN 20250101
#SIETYP 4
#FNAMN "Test AB"
#ORGNR 5566778899
#VALUTA SEK
#RAR 0 20250101 20251231
#KONTO 1930 "Företagskonto"
#KONTO 3000 "Försäljning"
#VER A 1 20250115 "Försäljning"
{
#TRANS 1930 {} 1000.00 20250115 ""
#TRANS 3000 {} -1000.00 20250115 ""
}
"""
    parser = SIEParser()
    data = parser.parse(content)

    assert data['fnamn'] == 'Test AB'
    assert data['orgnr'] == '5566778899'
    assert data['valuta'] == 'SEK'
    assert '1930' in data['konto']
    assert '3000' in data['konto']
    assert data['konto']['1930'] == 'Företagskonto'
    assert len(data['ver']) == 1
    assert len(data['ver'][0]['rows']) == 2
    assert data['ver'][0]['date'] == date(2025, 1, 15)


def test_sie_parser_fiscal_year():
    content = '#RAR 0 20250101 20251231\n#RAR -1 20240101 20241231\n'
    parser = SIEParser()
    data = parser.parse(content)

    assert 0 in data['rar']
    assert -1 in data['rar']
    assert data['rar'][0] == (date(2025, 1, 1), date(2025, 12, 31))


def test_sie_parser_balances():
    content = '#IB 0 1930 50000.00\n#UB 0 1930 75000.00\n#RES 0 3000 -100000.00\n'
    parser = SIEParser()
    data = parser.parse(content)

    assert data['ib'][(0, '1930')] == Decimal('50000.00')
    assert data['ub'][(0, '1930')] == Decimal('75000.00')
    assert data['res'][(0, '3000')] == Decimal('-100000.00')


def test_account_type_from_number():
    assert _account_type_from_number('1930') == 'asset'
    assert _account_type_from_number('2440') == 'liability'
    assert _account_type_from_number('2010') == 'equity'
    assert _account_type_from_number('3000') == 'revenue'
    assert _account_type_from_number('4000') == 'expense'
    assert _account_type_from_number('5010') == 'expense'
    assert _account_type_from_number('7010') == 'expense'
    assert _account_type_from_number('8110') == 'revenue'
    assert _account_type_from_number('8310') == 'expense'


def test_sie_parser_empty():
    parser = SIEParser()
    data = parser.parse('')
    assert data['ver'] == []
    assert data['konto'] == {}


def test_sie_parser_quoted_strings():
    content = '#FNAMN "Company With Spaces AB"\n#KONTO 1930 "Företagskonto/checkräkning"\n'
    parser = SIEParser()
    data = parser.parse(content)
    assert data['fnamn'] == 'Company With Spaces AB'
    assert data['konto']['1930'] == 'Företagskonto/checkräkning'
