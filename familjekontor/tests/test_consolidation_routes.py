"""Tests for consolidation routes (Phase 4E)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.consolidation_service import create_consolidation_group, add_member


@pytest.fixture
def consol_route_setup(db, logged_in_client):
    """Two companies, FYs, accounts, verifications, session set."""
    co1 = Company(name='ConsolRoute Moder', org_number='556600-0130', company_type='AB')
    co2 = Company(name='ConsolRoute Dotter', org_number='556600-0131', company_type='AB')
    db.session.add_all([co1, co2])
    db.session.flush()

    fy1 = FiscalYear(company_id=co1.id, year=2025, start_date=date(2025, 1, 1),
                     end_date=date(2025, 12, 31), status='open')
    fy2 = FiscalYear(company_id=co2.id, year=2025, start_date=date(2025, 1, 1),
                     end_date=date(2025, 12, 31), status='open')
    db.session.add_all([fy1, fy2])
    db.session.flush()

    for co, fy in [(co1, fy1), (co2, fy2)]:
        rev = Account(company_id=co.id, account_number='3010',
                      name='Försäljning', account_type='revenue')
        cash = Account(company_id=co.id, account_number='1930',
                       name='Företagskonto', account_type='asset')
        db.session.add_all([rev, cash])
        db.session.flush()

        v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                         verification_number=1, verification_date=date(2025, 3, 1))
        db.session.add(v)
        db.session.flush()
        db.session.add_all([
            VerificationRow(verification_id=v.id, account_id=cash.id,
                            debit=Decimal('100000'), credit=Decimal('0')),
            VerificationRow(verification_id=v.id, account_id=rev.id,
                            debit=Decimal('0'), credit=Decimal('100000')),
        ])

    db.session.commit()

    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co1.id

    return {'co1': co1, 'co2': co2, 'fy1': fy1, 'fy2': fy2}


def test_index_page(consol_route_setup, logged_in_client):
    response = logged_in_client.get('/consolidation/')
    assert response.status_code == 200


def test_create_group(consol_route_setup, logged_in_client):
    co1 = consol_route_setup['co1']
    response = logged_in_client.post('/consolidation/groups/new', data={
        'name': 'Testkoncern',
        'parent_company_id': co1.id,
        'description': 'Test',
    }, follow_redirects=True)
    assert response.status_code == 200


def test_view_group(consol_route_setup, logged_in_client):
    co1 = consol_route_setup['co1']
    group = create_consolidation_group('ViewTest', co1.id)
    response = logged_in_client.get(f'/consolidation/groups/{group.id}')
    assert response.status_code == 200


def test_add_member(consol_route_setup, logged_in_client):
    co1 = consol_route_setup['co1']
    co2 = consol_route_setup['co2']
    group = create_consolidation_group('MemberTest', co1.id)

    response = logged_in_client.post(
        f'/consolidation/groups/{group.id}/add-member',
        data={'company_id': co2.id, 'ownership_pct': 100},
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_remove_member(consol_route_setup, logged_in_client):
    co1 = consol_route_setup['co1']
    co2 = consol_route_setup['co2']
    group = create_consolidation_group('RemoveTest', co1.id)
    add_member(group.id, co2.id, 100)

    response = logged_in_client.post(
        f'/consolidation/groups/{group.id}/remove-member/{co2.id}',
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_report_page(consol_route_setup, logged_in_client):
    co1 = consol_route_setup['co1']
    co2 = consol_route_setup['co2']
    group = create_consolidation_group('ReportTest', co1.id)
    add_member(group.id, co1.id, 100)
    add_member(group.id, co2.id, 100)

    response = logged_in_client.get(
        f'/consolidation/groups/{group.id}/report?year=2025&type=pnl'
    )
    assert response.status_code == 200


def test_redirect_without_company(logged_in_client):
    """Consolidation requires active company for access control."""
    with logged_in_client.session_transaction() as sess:
        sess.pop('active_company_id', None)
    response = logged_in_client.get('/consolidation/')
    assert response.status_code == 302
