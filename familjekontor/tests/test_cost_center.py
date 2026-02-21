"""Tests for Phase 10B: Cost Center Management UI."""

import pytest
from datetime import date
from decimal import Decimal
from app.models.cost_center import CostCenter
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.cost_center_service import (
    get_cost_centers, create_cost_center, update_cost_center,
    delete_cost_center, get_cost_center_pnl, get_all_cost_centers_pnl,
)


@pytest.fixture
def company(db):
    c = Company(name='CC Test AB', org_number='556300-0001', company_type='AB')
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def fiscal_year(db, company):
    fy = FiscalYear(
        company_id=company.id, year=2026,
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.commit()
    return fy


@pytest.fixture
def accounts(db, company):
    accts = {}
    for num, name, atype in [
        ('3010', 'Försäljning', 'revenue'),
        ('4000', 'Inköp', 'expense'),
        ('5010', 'Lokalhyra', 'expense'),
    ]:
        a = Account(company_id=company.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        accts[num] = a
    db.session.commit()
    return accts


_ver_counter = [0]

def _create_verification_with_cc(db, company, fy, acct, debit, credit, cost_center):
    """Helper to create a verification with a cost center on the row."""
    _ver_counter[0] += 1
    v = Verification(
        company_id=company.id, fiscal_year_id=fy.id,
        verification_number=_ver_counter[0], verification_date=date(2026, 6, 15),
        description='Test',
    )
    db.session.add(v)
    db.session.flush()
    row = VerificationRow(
        verification_id=v.id, account_id=acct.id,
        debit=debit, credit=credit,
        description='Test row', cost_center=cost_center,
    )
    db.session.add(row)
    db.session.commit()
    return v


# ---- Model tests ----

class TestCostCenterModel:
    def test_create_cost_center(self, db, company):
        cc = CostCenter(company_id=company.id, code='IT', name='IT-avdelningen')
        db.session.add(cc)
        db.session.commit()
        assert cc.id is not None
        assert cc.active is True

    def test_repr(self, db, company):
        cc = CostCenter(company_id=company.id, code='MKT', name='Marknadsföring')
        assert 'MKT' in repr(cc)


# ---- Service tests ----

class TestGetCostCenters:
    def test_get_active_only(self, db, company):
        cc1 = CostCenter(company_id=company.id, code='A', name='Active', active=True)
        cc2 = CostCenter(company_id=company.id, code='B', name='Inactive', active=False)
        db.session.add_all([cc1, cc2])
        db.session.commit()
        result = get_cost_centers(company.id, active_only=True)
        assert len(result) == 1
        assert result[0].code == 'A'

    def test_get_all(self, db, company):
        cc1 = CostCenter(company_id=company.id, code='A', name='Active', active=True)
        cc2 = CostCenter(company_id=company.id, code='B', name='Inactive', active=False)
        db.session.add_all([cc1, cc2])
        db.session.commit()
        result = get_cost_centers(company.id, active_only=False)
        assert len(result) == 2


class TestCreateCostCenter:
    def test_create_success(self, db, company):
        cc = create_cost_center(company.id, 'IT', 'IT-avdelningen')
        assert cc.id is not None
        assert cc.code == 'IT'
        assert cc.name == 'IT-avdelningen'

    def test_create_strips_whitespace(self, db, company):
        cc = create_cost_center(company.id, '  HR  ', '  Personal  ')
        assert cc.code == 'HR'
        assert cc.name == 'Personal'


class TestUpdateCostCenter:
    def test_update_name(self, db, company):
        cc = create_cost_center(company.id, 'IT', 'IT')
        updated = update_cost_center(cc.id, name='IT-avdelningen')
        assert updated.name == 'IT-avdelningen'

    def test_update_nonexistent(self, db):
        result = update_cost_center(9999, name='Test')
        assert result is None


class TestDeleteCostCenter:
    def test_soft_delete(self, db, company):
        cc = create_cost_center(company.id, 'IT', 'IT')
        assert cc.active is True
        result = delete_cost_center(cc.id)
        assert result is True
        refreshed = db.session.get(CostCenter, cc.id)
        assert refreshed.active is False


class TestCostCenterPnl:
    def test_pnl_with_data(self, db, company, fiscal_year, accounts):
        # Revenue row
        _create_verification_with_cc(
            db, company, fiscal_year, accounts['3010'],
            Decimal('0'), Decimal('10000'), 'IT'
        )
        # Expense row
        _create_verification_with_cc(
            db, company, fiscal_year, accounts['5010'],
            Decimal('3000'), Decimal('0'), 'IT'
        )

        pnl = get_cost_center_pnl(company.id, fiscal_year.id, 'IT')
        assert pnl['total_revenue'] == 10000.0
        assert pnl['total_expenses'] == 3000.0
        assert pnl['result'] == 7000.0
        assert len(pnl['revenue_lines']) == 1
        assert len(pnl['expense_lines']) == 1

    def test_pnl_empty(self, db, company, fiscal_year, accounts):
        pnl = get_cost_center_pnl(company.id, fiscal_year.id, 'NONE')
        assert pnl['total_revenue'] == 0.0
        assert pnl['total_expenses'] == 0.0
        assert pnl['result'] == 0.0


class TestAllCostCentersPnl:
    def test_summary(self, db, company, fiscal_year, accounts):
        create_cost_center(company.id, 'IT', 'IT')
        create_cost_center(company.id, 'HR', 'HR')

        _create_verification_with_cc(
            db, company, fiscal_year, accounts['3010'],
            Decimal('0'), Decimal('5000'), 'IT'
        )

        summaries = get_all_cost_centers_pnl(company.id, fiscal_year.id)
        assert len(summaries) == 2
        it_summary = [s for s in summaries if s['code'] == 'IT'][0]
        assert it_summary['revenue'] == 5000.0


# ---- Route tests ----

class TestCostCenterRoutes:
    def _setup_company(self, db, logged_in_client):
        company = Company(name='Route CC AB', org_number='556333-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id
        return company

    def test_cost_centers_index(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        CostCenter(company_id=company.id, code='IT', name='IT')
        db.session.add(CostCenter(company_id=company.id, code='IT', name='IT'))
        db.session.commit()
        resp = logged_in_client.get('/accounting/cost-centers')
        assert resp.status_code == 200
        assert b'IT' in resp.data

    def test_create_cost_center_route(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        resp = logged_in_client.post('/accounting/cost-centers/new',
                                      data={'code': 'MKT', 'name': 'Marknad'},
                                      follow_redirects=True)
        assert resp.status_code == 200
        assert CostCenter.query.filter_by(company_id=company.id, code='MKT').first()

    def test_edit_cost_center_route(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        cc = CostCenter(company_id=company.id, code='IT', name='IT')
        db.session.add(cc)
        db.session.commit()
        resp = logged_in_client.post(f'/accounting/cost-centers/{cc.id}/edit',
                                      data={'code': 'IT', 'name': 'IT-avdelningen'},
                                      follow_redirects=True)
        assert resp.status_code == 200
        updated = db.session.get(CostCenter, cc.id)
        assert updated.name == 'IT-avdelningen'

    def test_delete_cost_center_route(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        cc = CostCenter(company_id=company.id, code='IT', name='IT')
        db.session.add(cc)
        db.session.commit()
        resp = logged_in_client.post(f'/accounting/cost-centers/{cc.id}/delete',
                                      follow_redirects=True)
        assert resp.status_code == 200
        assert db.session.get(CostCenter, cc.id).active is False

    def test_cost_center_report_route(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        fy = FiscalYear(company_id=company.id, year=2026,
                        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                        status='open')
        db.session.add(fy)
        db.session.commit()
        resp = logged_in_client.get(f'/accounting/cost-centers/report?fiscal_year_id={fy.id}')
        assert resp.status_code == 200

    def test_cost_center_drilldown_route(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        fy = FiscalYear(company_id=company.id, year=2026,
                        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                        status='open')
        db.session.add(fy)
        db.session.commit()
        resp = logged_in_client.get(f'/accounting/cost-centers/IT/drilldown?fiscal_year_id={fy.id}')
        assert resp.status_code == 200

    def test_create_cost_center_missing_fields(self, logged_in_client, db):
        self._setup_company(db, logged_in_client)
        resp = logged_in_client.post('/accounting/cost-centers/new',
                                      data={'code': '', 'name': ''},
                                      follow_redirects=True)
        assert resp.status_code == 200
        assert 'Kod och namn'.encode() in resp.data

    def test_edit_wrong_company(self, logged_in_client, db):
        c1 = Company(name='A', org_number='556444-0001', company_type='AB')
        c2 = Company(name='B', org_number='556444-0002', company_type='AB')
        db.session.add_all([c1, c2])
        db.session.commit()
        cc = CostCenter(company_id=c2.id, code='IT', name='IT')
        db.session.add(cc)
        db.session.commit()
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = c1.id
        resp = logged_in_client.get(f'/accounting/cost-centers/{cc.id}/edit',
                                     follow_redirects=True)
        assert resp.status_code == 200
        assert 'hittades inte'.encode() in resp.data

    def test_new_form_get(self, logged_in_client, db):
        self._setup_company(db, logged_in_client)
        resp = logged_in_client.get('/accounting/cost-centers/new')
        assert resp.status_code == 200
        assert b'Nytt' in resp.data

    def test_edit_form_get(self, logged_in_client, db):
        company = self._setup_company(db, logged_in_client)
        cc = CostCenter(company_id=company.id, code='IT', name='IT')
        db.session.add(cc)
        db.session.commit()
        resp = logged_in_client.get(f'/accounting/cost-centers/{cc.id}/edit')
        assert resp.status_code == 200
        assert b'IT' in resp.data

    def test_delete_nonexistent(self, logged_in_client, db):
        self._setup_company(db, logged_in_client)
        resp = logged_in_client.post('/accounting/cost-centers/9999/delete',
                                      follow_redirects=True)
        assert resp.status_code == 200
