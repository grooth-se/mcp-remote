"""Tests for bank integration routes (Phase 4B)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.bank import BankAccount, BankTransaction
from app.services.bank_service import create_bank_account


@pytest.fixture
def bank_route_setup(db, logged_in_client):
    """Company with FY, bank account, transactions, and session set."""
    co = Company(name='BankRoute AB', org_number='556600-0110', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    cash = Account(company_id=co.id, account_number='1930',
                   name='Företagskonto', account_type='asset')
    expense = Account(company_id=co.id, account_number='5010',
                      name='Lokalhyra', account_type='expense')
    db.session.add_all([cash, expense])
    db.session.flush()

    ba = BankAccount(company_id=co.id, bank_name='SEB', account_number='11112222333')
    db.session.add(ba)
    db.session.flush()

    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 3, 15))
    db.session.add(v)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v.id, account_id=expense.id,
                        debit=Decimal('5000'), credit=Decimal('0')),
        VerificationRow(verification_id=v.id, account_id=cash.id,
                        debit=Decimal('0'), credit=Decimal('5000')),
    ])

    txn = BankTransaction(
        bank_account_id=ba.id, company_id=co.id,
        transaction_date=date(2025, 3, 15), description='Hyra',
        amount=Decimal('-5000'), status='unmatched',
    )
    db.session.add(txn)
    db.session.commit()

    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id

    return {'company': co, 'fy': fy, 'bank_account': ba,
            'verification': v, 'transaction': txn}


def test_index_page(bank_route_setup, logged_in_client):
    response = logged_in_client.get('/bank/')
    assert response.status_code == 200


def test_accounts_list(bank_route_setup, logged_in_client):
    response = logged_in_client.get('/bank/accounts')
    assert response.status_code == 200


def test_create_account(bank_route_setup, logged_in_client):
    response = logged_in_client.post('/bank/accounts/new', data={
        'bank_name': 'Nordea',
        'account_number': '99998888777',
        'clearing_number': '3300',
        'currency': 'SEK',
        'ledger_account': '1930',
    }, follow_redirects=True)
    assert response.status_code == 200

    from app.models.bank import BankAccount
    accs = BankAccount.query.filter_by(bank_name='Nordea').all()
    assert len(accs) == 1


def test_edit_account(bank_route_setup, logged_in_client):
    ba = bank_route_setup['bank_account']
    response = logged_in_client.post(f'/bank/accounts/{ba.id}/edit', data={
        'bank_name': 'SEB Updated',
        'account_number': '11112222333',
        'ledger_account': '1930',
    }, follow_redirects=True)
    assert response.status_code == 200


def test_import_page(bank_route_setup, logged_in_client):
    response = logged_in_client.get('/bank/import')
    assert response.status_code == 200


def test_reconciliation_page(bank_route_setup, logged_in_client):
    response = logged_in_client.get('/bank/reconciliation')
    assert response.status_code == 200


def test_redirect_without_company(logged_in_client):
    with logged_in_client.session_transaction() as sess:
        sess.pop('active_company_id', None)
    response = logged_in_client.get('/bank/')
    assert response.status_code == 302


def test_match_transaction(bank_route_setup, logged_in_client):
    txn = bank_route_setup['transaction']
    response = logged_in_client.get(f'/bank/transactions/{txn.id}/match')
    assert response.status_code == 200
