"""Tests for Phase 10A: Supplier Learning / Account Mapping."""

import pytest
from app.models.invoice import Supplier, SupplierInvoice
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.company import Company
from app.services.ai_service import (
    suggest_account, record_supplier_mapping, get_supplier_mappings,
    delete_supplier_mapping, _check_supplier_mappings,
)


@pytest.fixture
def company(db):
    c = Company(name='Test AB', org_number='556000-0001', company_type='AB')
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def supplier(db, company):
    s = Supplier(company_id=company.id, name='Kontorsbolaget AB', org_number='556111-1111')
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def fiscal_year(db, company):
    from datetime import date
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
        ('4000', 'Inköp', 'expense'),
        ('2440', 'Leverantörsskulder', 'liability'),
        ('2640', 'Ingående moms', 'liability'),
        ('5010', 'Lokalhyra', 'expense'),
    ]:
        a = Account(company_id=company.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        accts[num] = a
    db.session.commit()
    return accts


# ---- Model tests ----

class TestSupplierLearnMapping:
    def test_learn_mapping_creates_new(self, db, supplier):
        supplier.learn_mapping('kontorsmaterial', '6110')
        db.session.commit()
        s = db.session.get(Supplier, supplier.id)
        assert s.learned_mappings == {'kontorsmaterial': '6110'}

    def test_learn_mapping_adds_to_existing(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010'}
        db.session.commit()
        supplier.learn_mapping('el', '5020')
        db.session.commit()
        s = db.session.get(Supplier, supplier.id)
        assert s.learned_mappings == {'hyra': '5010', 'el': '5020'}

    def test_learn_mapping_overwrites_existing_key(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010'}
        db.session.commit()
        supplier.learn_mapping('hyra', '5011')
        db.session.commit()
        s = db.session.get(Supplier, supplier.id)
        assert s.learned_mappings['hyra'] == '5011'

    def test_learn_mapping_strips_and_lowercases(self, db, supplier):
        supplier.learn_mapping('  HYRA  ', '5010')
        db.session.commit()
        assert 'hyra' in supplier.learned_mappings

    def test_learn_mapping_empty_description_ignored(self, db, supplier):
        supplier.learn_mapping('', '5010')
        db.session.commit()
        assert supplier.learned_mappings is None


# ---- Service tests ----

class TestRecordSupplierMapping:
    def test_record_mapping_success(self, db, supplier):
        result = record_supplier_mapping(supplier.id, 'kontorsmat', '6110')
        assert result is True
        s = db.session.get(Supplier, supplier.id)
        assert s.learned_mappings['kontorsmat'] == '6110'

    def test_record_mapping_invalid_supplier(self, db):
        result = record_supplier_mapping(9999, 'test', '4000')
        assert result is False


class TestGetSupplierMappings:
    def test_get_mappings_returns_dict(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010', 'el': '5020'}
        db.session.commit()
        mappings = get_supplier_mappings(supplier.id)
        assert mappings == {'hyra': '5010', 'el': '5020'}

    def test_get_mappings_empty(self, db, supplier):
        mappings = get_supplier_mappings(supplier.id)
        assert mappings == {}

    def test_get_mappings_invalid_supplier(self, db):
        mappings = get_supplier_mappings(9999)
        assert mappings == {}


class TestDeleteSupplierMapping:
    def test_delete_mapping_success(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010', 'el': '5020'}
        db.session.commit()
        result = delete_supplier_mapping(supplier.id, 'hyra')
        assert result is True
        s = db.session.get(Supplier, supplier.id)
        assert 'hyra' not in s.learned_mappings
        assert 'el' in s.learned_mappings

    def test_delete_last_mapping_sets_none(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010'}
        db.session.commit()
        result = delete_supplier_mapping(supplier.id, 'hyra')
        assert result is True
        s = db.session.get(Supplier, supplier.id)
        assert s.learned_mappings is None

    def test_delete_mapping_not_found(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010'}
        db.session.commit()
        result = delete_supplier_mapping(supplier.id, 'missing')
        assert result is False


class TestCheckSupplierMappings:
    def test_exact_match(self, db, supplier):
        supplier.learned_mappings = {'kontorsmaterial': '6110'}
        db.session.commit()
        result = _check_supplier_mappings(supplier.id, 'kontorsmaterial')
        assert result is not None
        assert result['account_number'] == '6110'
        assert result['confidence'] == 0.95

    def test_substring_match(self, db, supplier):
        supplier.learned_mappings = {'kontor': '6110'}
        db.session.commit()
        result = _check_supplier_mappings(supplier.id, 'kontorsmaterial papper')
        assert result is not None
        assert result['account_number'] == '6110'
        assert result['confidence'] == 0.90

    def test_no_match(self, db, supplier):
        supplier.learned_mappings = {'hyra': '5010'}
        db.session.commit()
        result = _check_supplier_mappings(supplier.id, 'helt annan sak')
        assert result is None


class TestSuggestAccountWithSupplier:
    def test_supplier_mapping_takes_priority(self, db, supplier):
        """Supplier learned mapping should override ACCOUNT_PATTERNS."""
        supplier.learned_mappings = {'hyra kontor': '5015'}
        db.session.commit()
        result = suggest_account('hyra kontor', supplier_id=supplier.id)
        assert result['account_number'] == '5015'
        assert result['confidence'] == 0.95

    def test_falls_through_to_patterns(self, db, supplier):
        """Without matching supplier mapping, should fall through to patterns."""
        supplier.learned_mappings = {'annan sak': '4000'}
        db.session.commit()
        result = suggest_account('hyra', supplier_id=supplier.id)
        assert result['account_number'] == '5010'
        assert result['confidence'] == 0.8


# ---- Route tests ----

class TestSupplierMappingsRoute:
    def test_view_mappings(self, logged_in_client, db):
        company = Company(name='Route AB', org_number='556222-2222', company_type='AB')
        db.session.add(company)
        db.session.commit()
        supplier = Supplier(company_id=company.id, name='Lev AB',
                           learned_mappings={'hyra': '5010'})
        db.session.add(supplier)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/invoices/suppliers/{supplier.id}/mappings')
        assert resp.status_code == 200
        assert b'hyra' in resp.data
        assert b'5010' in resp.data

    def test_view_mappings_empty(self, logged_in_client, db):
        company = Company(name='Route AB', org_number='556222-2222', company_type='AB')
        db.session.add(company)
        db.session.commit()
        supplier = Supplier(company_id=company.id, name='Lev AB')
        db.session.add(supplier)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/invoices/suppliers/{supplier.id}/mappings')
        assert resp.status_code == 200
        assert 'Inga mappningar'.encode() in resp.data

    def test_delete_mapping_route(self, logged_in_client, db):
        company = Company(name='Route AB', org_number='556222-2222', company_type='AB')
        db.session.add(company)
        db.session.commit()
        supplier = Supplier(company_id=company.id, name='Lev AB',
                           learned_mappings={'hyra': '5010', 'el': '5020'})
        db.session.add(supplier)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.post(
            f'/invoices/suppliers/{supplier.id}/mappings/delete',
            data={'description_key': 'hyra'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        s = db.session.get(Supplier, supplier.id)
        assert 'hyra' not in s.learned_mappings

    def test_view_wrong_company(self, logged_in_client, db):
        c1 = Company(name='Company A', org_number='556111-0001', company_type='AB')
        c2 = Company(name='Company B', org_number='556111-0002', company_type='AB')
        db.session.add_all([c1, c2])
        db.session.commit()
        supplier = Supplier(company_id=c2.id, name='Lev AB')
        db.session.add(supplier)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = c1.id

        resp = logged_in_client.get(
            f'/invoices/suppliers/{supplier.id}/mappings',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'hittades inte'.encode() in resp.data
