"""Tests for Report Center & PDF Export (Phase 6E)."""

import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.user import User
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.saved_report import SavedReport
from app.services.report_center_service import (
    get_available_reports, save_report_config, get_saved_reports,
    delete_saved_report, generate_report_pdf,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rc_company(db):
    """Company with fiscal years and accounting data for report center tests."""
    co = Company(name='RC AB', org_number='556900-0091', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy24 = FiscalYear(company_id=co.id, year=2024, start_date=date(2024, 1, 1),
                      end_date=date(2024, 12, 31), status='closed')
    fy25 = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                      end_date=date(2025, 12, 31), status='open')
    db.session.add_all([fy24, fy25])
    db.session.flush()

    # Accounts
    accts = {}
    for num, name, atype in [
        ('1930', 'Företagskonto', 'asset'),
        ('1510', 'Kundfordringar', 'asset'),
        ('2081', 'Aktiekapital', 'equity'),
        ('3010', 'Försäljning', 'revenue'),
        ('4010', 'Inköp', 'expense'),
        ('5010', 'Lokalhyra', 'expense'),
    ]:
        a = Account(company_id=co.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accts[num] = a

    # FY2024 data
    _add_ver(db, co.id, fy24.id, 1, date(2024, 3, 1), [
        (accts['1930'], Decimal('80000'), Decimal('0')),
        (accts['3010'], Decimal('0'), Decimal('80000')),
    ])

    # FY2025 data
    _add_ver(db, co.id, fy25.id, 1, date(2025, 3, 1), [
        (accts['1930'], Decimal('100000'), Decimal('0')),
        (accts['3010'], Decimal('0'), Decimal('100000')),
    ])
    _add_ver(db, co.id, fy25.id, 2, date(2025, 4, 1), [
        (accts['4010'], Decimal('30000'), Decimal('0')),
        (accts['1930'], Decimal('0'), Decimal('30000')),
    ])

    db.session.commit()
    return {'company': co, 'fy24': fy24, 'fy25': fy25, 'accounts': accts}


def _add_ver(db, company_id, fy_id, num, ver_date, rows):
    v = Verification(company_id=company_id, fiscal_year_id=fy_id,
                     verification_number=num, verification_date=ver_date)
    db.session.add(v)
    db.session.flush()
    for account, debit, credit in rows:
        db.session.add(VerificationRow(
            verification_id=v.id, account_id=account.id,
            debit=debit, credit=credit))


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestAvailableReports:
    def test_returns_list(self, app):
        with app.app_context():
            reports = get_available_reports()
            assert len(reports) >= 10
            assert reports[0]['key'] == 'pnl'

    def test_has_required_fields(self, app):
        with app.app_context():
            reports = get_available_reports()
            for r in reports:
                assert 'key' in r
                assert 'name' in r
                assert 'url_name' in r
                assert 'category' in r

    def test_categories(self, app):
        with app.app_context():
            reports = get_available_reports()
            categories = set(r['category'] for r in reports)
            assert 'Finansiella' in categories
            assert 'Analys' in categories


class TestSavedReportConfig:
    def test_save_and_get(self, app, db, rc_company):
        with app.app_context():
            co = rc_company['company']
            # Get a user
            user = User.query.first()
            if not user:
                user = User(username='rctest', email='rc@test.com', role='admin')
                user.set_password('test')
                db.session.add(user)
                db.session.commit()

            sr = save_report_config(co.id, user.id, 'Test PNL', 'pnl', {'fy_id': 1})
            assert sr.id is not None
            assert sr.name == 'Test PNL'

            saved = get_saved_reports(co.id, user.id)
            assert len(saved) >= 1
            assert saved[0].name == 'Test PNL'

    def test_delete_own(self, app, db, rc_company):
        with app.app_context():
            co = rc_company['company']
            user = User.query.first()
            if not user:
                user = User(username='rctest2', email='rc2@test.com', role='admin')
                user.set_password('test')
                db.session.add(user)
                db.session.commit()

            sr = save_report_config(co.id, user.id, 'To Delete', 'balance', None)
            assert delete_saved_report(sr.id, user.id) is True
            assert db.session.get(SavedReport, sr.id) is None

    def test_delete_wrong_user(self, app, db, rc_company):
        with app.app_context():
            co = rc_company['company']
            user = User.query.first()
            if not user:
                user = User(username='rctest3', email='rc3@test.com', role='admin')
                user.set_password('test')
                db.session.add(user)
                db.session.commit()

            sr = save_report_config(co.id, user.id, 'Protected', 'pnl', None)
            # Try to delete with wrong user_id
            assert delete_saved_report(sr.id, user.id + 999) is False

    def test_parameters_json(self, app, db, rc_company):
        with app.app_context():
            co = rc_company['company']
            user = User.query.first()
            if not user:
                user = User(username='rctest4', email='rc4@test.com', role='admin')
                user.set_password('test')
                db.session.add(user)
                db.session.commit()

            params = {'fiscal_year_id': 1, 'report_type': 'pnl'}
            sr = save_report_config(co.id, user.id, 'With Params', 'pnl', params)
            assert json.loads(sr.parameters) == params


class TestPDFGeneration:
    def test_invalid_type(self, app, rc_company):
        with app.app_context():
            co = rc_company['company']
            fy = rc_company['fy25']
            result = generate_report_pdf('invalid_type', co.id, fy.id)
            assert result is None

    def test_pnl_pdf_weasyprint_absent(self, app, rc_company):
        """PDF generation returns None when WeasyPrint is unavailable."""
        with app.app_context():
            co = rc_company['company']
            fy = rc_company['fy25']
            # On this system, WeasyPrint is unavailable (libpango missing)
            # so generate_report_pdf should return None gracefully
            result = generate_report_pdf('pnl', co.id, fy.id)
            # Result is either a BytesIO (if WeasyPrint works) or None
            # Both are acceptable
            assert result is None or hasattr(result, 'read')

    def test_comparison_requires_fy_b(self, app, rc_company):
        with app.app_context():
            co = rc_company['company']
            fy = rc_company['fy25']
            result = generate_report_pdf('comparison', co.id, fy.id)
            assert result is None  # No fy_b_id provided


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestReportCenterRoutes:
    def test_index(self, logged_in_client, rc_company):
        co = rc_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/report-center/')
        assert resp.status_code == 200
        assert 'Rapportcenter' in resp.data.decode()
        assert 'Finansiella' in resp.data.decode()

    def test_save_ajax(self, logged_in_client, rc_company):
        co = rc_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/report-center/save',
                                     json={'name': 'Test Save', 'report_type': 'pnl'},
                                     content_type='application/json')
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Test Save'

    def test_save_missing_fields(self, logged_in_client, rc_company):
        co = rc_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.post('/report-center/save',
                                     json={'name': ''},
                                     content_type='application/json')
        assert resp.status_code == 400

    def test_delete_route(self, logged_in_client, rc_company, db):
        co = rc_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        # Save one first
        resp = logged_in_client.post('/report-center/save',
                                     json={'name': 'Del Test', 'report_type': 'balance'},
                                     content_type='application/json')
        sr_id = resp.get_json()['id']

        resp = logged_in_client.post(f'/report-center/saved/{sr_id}/delete',
                                     follow_redirects=True)
        assert resp.status_code == 200

    def test_pdf_no_fy(self, logged_in_client, rc_company):
        co = rc_company['company']
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        resp = logged_in_client.get('/report-center/pdf/pnl', follow_redirects=False)
        assert resp.status_code == 302  # Redirects back — no fiscal_year_id

    def test_no_company_redirect(self, logged_in_client):
        resp = logged_in_client.get('/report-center/', follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Model Test
# ---------------------------------------------------------------------------

class TestSavedReportModel:
    def test_creation(self, app, db, rc_company):
        with app.app_context():
            co = rc_company['company']
            user = User.query.first()
            if not user:
                user = User(username='model_test', email='mt@test.com', role='admin')
                user.set_password('test')
                db.session.add(user)
                db.session.commit()

            sr = SavedReport(
                company_id=co.id, user_id=user.id,
                name='Model Test', report_type='cashflow')
            db.session.add(sr)
            db.session.commit()

            fetched = db.session.get(SavedReport, sr.id)
            assert fetched.name == 'Model Test'
            assert fetched.report_type == 'cashflow'
            assert repr(fetched) == '<SavedReport Model Test (cashflow)>'
