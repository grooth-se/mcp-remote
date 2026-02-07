"""Tests for accounting service."""

import pytest
from datetime import date
from decimal import Decimal
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification
from app.services.accounting_service import (
    create_verification, get_next_verification_number, get_trial_balance,
)


@pytest.fixture
def company_with_accounts(db):
    company = Company(name='Test AB', org_number='5566778899', company_type='AB')
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(company_id=company.id, year=2025,
                    start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add(fy)
    db.session.flush()

    acc_bank = Account(company_id=company.id, account_number='1930', name='Bank', account_type='asset')
    acc_sales = Account(company_id=company.id, account_number='3000', name='Försäljning', account_type='revenue')
    acc_cost = Account(company_id=company.id, account_number='4000', name='Inköp', account_type='expense')
    acc_supplier = Account(company_id=company.id, account_number='2440', name='Leverantörsskulder', account_type='liability')
    db.session.add_all([acc_bank, acc_sales, acc_cost, acc_supplier])
    db.session.commit()

    return {
        'company': company,
        'fiscal_year': fy,
        'bank': acc_bank,
        'sales': acc_sales,
        'cost': acc_cost,
        'supplier': acc_supplier,
    }


def test_create_verification(company_with_accounts):
    data = company_with_accounts
    rows = [
        {'account_id': data['bank'].id, 'debit': 10000, 'credit': 0},
        {'account_id': data['sales'].id, 'debit': 0, 'credit': 10000},
    ]
    ver = create_verification(
        company_id=data['company'].id,
        fiscal_year_id=data['fiscal_year'].id,
        verification_date=date(2025, 1, 15),
        description='Försäljning kontant',
        rows=rows,
    )
    assert ver.verification_number == 1
    assert ver.is_balanced
    assert len(ver.rows) == 2


def test_create_unbalanced_verification(company_with_accounts):
    data = company_with_accounts
    rows = [
        {'account_id': data['bank'].id, 'debit': 10000, 'credit': 0},
        {'account_id': data['sales'].id, 'debit': 0, 'credit': 5000},
    ]
    with pytest.raises(ValueError, match='balanserar inte'):
        create_verification(
            company_id=data['company'].id,
            fiscal_year_id=data['fiscal_year'].id,
            verification_date=date(2025, 1, 15),
            description='Obalanserad',
            rows=rows,
        )


def test_auto_numbering(company_with_accounts):
    data = company_with_accounts
    rows = [
        {'account_id': data['bank'].id, 'debit': 1000, 'credit': 0},
        {'account_id': data['sales'].id, 'debit': 0, 'credit': 1000},
    ]
    ver1 = create_verification(data['company'].id, data['fiscal_year'].id,
                                date(2025, 1, 10), 'V1', rows)
    ver2 = create_verification(data['company'].id, data['fiscal_year'].id,
                                date(2025, 1, 11), 'V2', rows)
    assert ver1.verification_number == 1
    assert ver2.verification_number == 2


def test_trial_balance(company_with_accounts):
    data = company_with_accounts

    # Create two verifications
    rows1 = [
        {'account_id': data['bank'].id, 'debit': 10000, 'credit': 0},
        {'account_id': data['sales'].id, 'debit': 0, 'credit': 10000},
    ]
    rows2 = [
        {'account_id': data['cost'].id, 'debit': 3000, 'credit': 0},
        {'account_id': data['bank'].id, 'debit': 0, 'credit': 3000},
    ]
    create_verification(data['company'].id, data['fiscal_year'].id,
                        date(2025, 1, 10), 'Sale', rows1)
    create_verification(data['company'].id, data['fiscal_year'].id,
                        date(2025, 1, 15), 'Purchase', rows2)

    balance = get_trial_balance(data['company'].id, data['fiscal_year'].id)
    assert len(balance) == 3  # bank, sales, cost

    bank_entry = next(b for b in balance if b['account_number'] == '1930')
    assert bank_entry['total_debit'] == 10000
    assert bank_entry['total_credit'] == 3000
    assert bank_entry['balance'] == 7000
