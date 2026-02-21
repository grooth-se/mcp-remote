"""Tests for Phase 10C: Real Estate Register."""

import pytest
from datetime import date
from decimal import Decimal
from app.models.real_estate import RealEstate
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.services.real_estate_service import (
    get_real_estates, create_real_estate, update_real_estate,
    delete_real_estate, calculate_property_tax, get_rental_income_ytd,
    get_real_estate_summary,
)


@pytest.fixture
def company(db):
    c = Company(name='RE Test AB', org_number='556400-0001', company_type='AB')
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
def rent_account(db, company):
    a = Account(company_id=company.id, account_number='3910', name='Hyresintäkter', account_type='revenue')
    db.session.add(a)
    db.session.commit()
    return a


# ---- Model tests ----

class TestRealEstateModel:
    def test_create(self, db, company):
        prop = RealEstate(
            company_id=company.id, property_name='Kontoret',
            fastighetsbeteckning='Kungsholmen 1:2',
            taxeringsvarde=5000000, property_tax_rate=0.0075,
        )
        db.session.add(prop)
        db.session.commit()
        assert prop.id is not None
        assert prop.active is True

    def test_repr(self, db, company):
        prop = RealEstate(company_id=company.id, property_name='Villa')
        assert 'Villa' in repr(prop)

    def test_nullable_asset_id(self, db, company):
        prop = RealEstate(company_id=company.id, property_name='Test', asset_id=None)
        db.session.add(prop)
        db.session.commit()
        assert prop.asset_id is None


# ---- Service tests ----

class TestGetRealEstates:
    def test_active_only(self, db, company):
        p1 = RealEstate(company_id=company.id, property_name='Active', active=True)
        p2 = RealEstate(company_id=company.id, property_name='Inactive', active=False)
        db.session.add_all([p1, p2])
        db.session.commit()
        result = get_real_estates(company.id, active_only=True)
        assert len(result) == 1

    def test_get_all(self, db, company):
        p1 = RealEstate(company_id=company.id, property_name='A', active=True)
        p2 = RealEstate(company_id=company.id, property_name='B', active=False)
        db.session.add_all([p1, p2])
        db.session.commit()
        result = get_real_estates(company.id, active_only=False)
        assert len(result) == 2


class TestCreateRealEstate:
    def test_create(self, db, company):
        prop = create_real_estate(company.id, property_name='Kontoret', city='Stockholm')
        assert prop.id is not None
        assert prop.city == 'Stockholm'


class TestUpdateRealEstate:
    def test_update(self, db, company):
        prop = create_real_estate(company.id, property_name='Old')
        updated = update_real_estate(prop.id, property_name='New')
        assert updated.property_name == 'New'

    def test_update_nonexistent(self, db):
        result = update_real_estate(9999, property_name='X')
        assert result is None


class TestDeleteRealEstate:
    def test_soft_delete(self, db, company):
        prop = create_real_estate(company.id, property_name='Test')
        assert delete_real_estate(prop.id) is True
        refreshed = db.session.get(RealEstate, prop.id)
        assert refreshed.active is False

    def test_delete_nonexistent(self, db):
        assert delete_real_estate(9999) is False


class TestCalculatePropertyTax:
    def test_standard_rate(self, db, company):
        prop = RealEstate(
            company_id=company.id, property_name='Test',
            taxeringsvarde=2000000, property_tax_rate=Decimal('0.0075'),
        )
        tax = calculate_property_tax(prop)
        assert tax == Decimal('15000.00')

    def test_zero_value(self, db, company):
        prop = RealEstate(company_id=company.id, property_name='Test', taxeringsvarde=0)
        tax = calculate_property_tax(prop)
        assert tax == Decimal('0')

    def test_none_prop(self):
        assert calculate_property_tax(None) == Decimal('0')


class TestRentalIncomeYtd:
    def test_with_income(self, db, company, fiscal_year, rent_account):
        v = Verification(
            company_id=company.id, fiscal_year_id=fiscal_year.id,
            verification_number=1, verification_date=date(2026, 3, 1),
            description='Hyra mars',
        )
        db.session.add(v)
        db.session.flush()
        row = VerificationRow(
            verification_id=v.id, account_id=rent_account.id,
            debit=Decimal('0'), credit=Decimal('25000'),
            description='Hyresintäkt',
        )
        db.session.add(row)
        db.session.commit()

        income = get_rental_income_ytd(company.id, fiscal_year.id, '3910')
        assert income == Decimal('25000')

    def test_no_income(self, db, company, fiscal_year, rent_account):
        income = get_rental_income_ytd(company.id, fiscal_year.id, '3910')
        assert income == Decimal('0')


class TestRealEstateSummary:
    def test_summary(self, db, company, fiscal_year, rent_account):
        create_real_estate(company.id, property_name='Kontor', taxeringsvarde=1000000,
                          property_tax_rate=0.0075, city='Stockholm')
        summaries = get_real_estate_summary(company.id, fiscal_year.id)
        assert len(summaries) == 1
        assert summaries[0]['property_name'] == 'Kontor'
        assert summaries[0]['property_tax'] == 7500.0


# ---- Route tests ----

class TestRealEstateRoutes:
    def _setup(self, db, logged_in_client):
        company = Company(name='RE Route AB', org_number='556500-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id
        return company

    def test_index(self, logged_in_client, db):
        self._setup(db, logged_in_client)
        resp = logged_in_client.get('/assets/real-estate/')
        assert resp.status_code == 200

    def test_new_get(self, logged_in_client, db):
        self._setup(db, logged_in_client)
        resp = logged_in_client.get('/assets/real-estate/new')
        assert resp.status_code == 200

    def test_create_and_view(self, logged_in_client, db):
        company = self._setup(db, logged_in_client)
        resp = logged_in_client.post('/assets/real-estate/new', data={
            'property_name': 'Testvillan',
            'fastighetsbeteckning': 'Kungsholmen 1:1',
            'city': 'Stockholm',
            'taxeringsvarde': '2000000',
            'property_tax_rate': '0.0075',
            'rent_account': '3910',
            'asset_id': '0',
        }, follow_redirects=True)
        assert resp.status_code == 200
        prop = RealEstate.query.filter_by(company_id=company.id).first()
        assert prop is not None

        # View
        resp = logged_in_client.get(f'/assets/real-estate/{prop.id}')
        assert resp.status_code == 200
        assert b'Testvillan' in resp.data

    def test_edit(self, logged_in_client, db):
        company = self._setup(db, logged_in_client)
        prop = RealEstate(company_id=company.id, property_name='Old')
        db.session.add(prop)
        db.session.commit()
        resp = logged_in_client.post(f'/assets/real-estate/{prop.id}/edit', data={
            'property_name': 'New',
            'asset_id': '0',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_delete(self, logged_in_client, db):
        company = self._setup(db, logged_in_client)
        prop = RealEstate(company_id=company.id, property_name='ToDelete')
        db.session.add(prop)
        db.session.commit()
        resp = logged_in_client.post(f'/assets/real-estate/{prop.id}/delete',
                                      follow_redirects=True)
        assert resp.status_code == 200
        assert db.session.get(RealEstate, prop.id).active is False

    def test_view_wrong_company(self, logged_in_client, db):
        c1 = Company(name='A', org_number='556600-0001', company_type='AB')
        c2 = Company(name='B', org_number='556600-0002', company_type='AB')
        db.session.add_all([c1, c2])
        db.session.commit()
        prop = RealEstate(company_id=c2.id, property_name='Other')
        db.session.add(prop)
        db.session.commit()
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = c1.id
        resp = logged_in_client.get(f'/assets/real-estate/{prop.id}', follow_redirects=True)
        assert resp.status_code == 200
        assert 'hittades inte'.encode() in resp.data
