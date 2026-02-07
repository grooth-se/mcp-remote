"""Tests for report service."""

import pytest
from datetime import date
from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.services.accounting_service import create_verification
from app.services.report_service import get_profit_and_loss, get_balance_sheet, get_general_ledger


@pytest.fixture
def company_with_data(db):
    company = Company(name='Test AB', org_number='5566778899', company_type='AB')
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(company_id=company.id, year=2025,
                    start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add(fy)
    db.session.flush()

    accounts = {
        'bank': Account(company_id=company.id, account_number='1930', name='Bank', account_type='asset'),
        'sales': Account(company_id=company.id, account_number='3000', name='Försäljning', account_type='revenue'),
        'cost': Account(company_id=company.id, account_number='4000', name='Inköp', account_type='expense'),
        'rent': Account(company_id=company.id, account_number='5010', name='Hyra', account_type='expense'),
        'equity': Account(company_id=company.id, account_number='2010', name='Eget kapital', account_type='equity'),
    }
    for acc in accounts.values():
        db.session.add(acc)
    db.session.flush()

    # Sale: bank 50000 / sales 50000
    create_verification(company.id, fy.id, date(2025, 1, 10), 'Försäljning', [
        {'account_id': accounts['bank'].id, 'debit': 50000, 'credit': 0},
        {'account_id': accounts['sales'].id, 'debit': 0, 'credit': 50000},
    ])

    # Purchase: cost 10000 / bank 10000
    create_verification(company.id, fy.id, date(2025, 2, 1), 'Inköp', [
        {'account_id': accounts['cost'].id, 'debit': 10000, 'credit': 0},
        {'account_id': accounts['bank'].id, 'debit': 0, 'credit': 10000},
    ])

    # Rent: rent 5000 / bank 5000
    create_verification(company.id, fy.id, date(2025, 3, 1), 'Hyra', [
        {'account_id': accounts['rent'].id, 'debit': 5000, 'credit': 0},
        {'account_id': accounts['bank'].id, 'debit': 0, 'credit': 5000},
    ])

    return {'company': company, 'fiscal_year': fy, 'accounts': accounts}


def test_profit_and_loss(company_with_data):
    data = company_with_data
    pnl = get_profit_and_loss(data['company'].id, data['fiscal_year'].id)

    assert pnl['sections']['Nettoomsättning']['total'] == 50000
    assert pnl['sections']['Kostnad sålda varor']['total'] == 10000
    assert pnl['gross_profit'] == 40000  # 50000 - 10000
    assert pnl['sections']['Övriga externa kostnader']['total'] == 5000
    assert pnl['operating_result'] == 35000  # 40000 - 5000


def test_balance_sheet(company_with_data):
    data = company_with_data
    bs = get_balance_sheet(data['company'].id, data['fiscal_year'].id)

    # Bank: 50000 - 10000 - 5000 = 35000
    assert bs['total_assets'] == 35000


def test_general_ledger(company_with_data):
    data = company_with_data
    ledger = get_general_ledger(data['company'].id, data['fiscal_year'].id)

    assert len(ledger) > 0
    # Bank account should have 3 entries
    bank_key = [k for k in ledger.keys() if '1930' in k][0]
    assert len(ledger[bank_key]['entries']) == 3


def test_general_ledger_filtered(company_with_data):
    data = company_with_data
    ledger = get_general_ledger(data['company'].id, data['fiscal_year'].id, '1930')

    assert len(ledger) == 1
    bank_key = list(ledger.keys())[0]
    assert '1930' in bank_key
