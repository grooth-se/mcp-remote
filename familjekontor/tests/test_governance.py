"""Tests for Phase 5C: Governance & Shareholder Management."""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.models.governance import (
    BoardMember, ShareClass, Shareholder, ShareholderHolding,
    DividendDecision, AGMMinutes, BOARD_ROLE_LABELS,
)
from app.services.governance_service import (
    create_board_member, update_board_member, end_appointment,
    get_board_members, get_board_for_annual_report,
    create_share_class, get_share_classes,
    create_shareholder, get_shareholders,
    add_holding, get_ownership_summary, get_share_register,
    create_dividend_decision, pay_dividend, get_dividends,
    create_agm_minutes, get_agm_history, get_agm,
)


def _setup_company(logged_in_client):
    co = Company(name='Governance Test AB', org_number='556000-7700', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


def _setup_fy(company, year=2024):
    fy = FiscalYear(company_id=company.id, year=year,
                    start_date=date(year, 1, 1), end_date=date(year, 12, 31))
    db.session.add(fy)
    db.session.commit()
    return fy


def _add_accounts(company):
    accts = [
        Account(company_id=company.id, account_number='2898', name='Outtagen utdelning',
                account_type='liability', active=True),
        Account(company_id=company.id, account_number='1930', name='Företagskonto',
                account_type='asset', active=True),
    ]
    db.session.add_all(accts)
    db.session.commit()
    return accts


# ---------------------------------------------------------------------------
# Board Members
# ---------------------------------------------------------------------------

class TestCreateBoardMember:
    def test_create_basic(self, logged_in_client):
        co = _setup_company(logged_in_client)
        data = {
            'name': 'Anna Svensson',
            'role': 'ordforande',
            'appointed_date': date(2024, 6, 1),
        }
        member = create_board_member(co.id, data, created_by=1)
        assert member.id is not None
        assert member.name == 'Anna Svensson'
        assert member.role == 'ordforande'
        assert member.role_label == 'Ordförande'
        assert member.is_active is True

    def test_create_with_all_fields(self, logged_in_client):
        co = _setup_company(logged_in_client)
        data = {
            'name': 'Erik Johansson',
            'personal_number': '19800515-1234',
            'role': 'ledamot',
            'title': 'CFO',
            'appointed_date': date(2023, 1, 1),
            'end_date': None,
            'appointed_by': 'Årsstämma 2023',
            'email': 'erik@test.se',
            'phone': '0701234567',
        }
        member = create_board_member(co.id, data)
        assert member.personal_number == '19800515-1234'
        assert member.email == 'erik@test.se'


class TestUpdateBoardMember:
    def test_update_name_and_role(self, logged_in_client):
        co = _setup_company(logged_in_client)
        member = create_board_member(co.id, {
            'name': 'Test Person', 'role': 'ledamot', 'appointed_date': date(2024, 1, 1)
        })
        updated = update_board_member(member.id, {'name': 'Updated Name', 'role': 'suppleant'})
        assert updated.name == 'Updated Name'
        assert updated.role == 'suppleant'

    def test_update_nonexistent_raises(self, logged_in_client):
        _setup_company(logged_in_client)
        try:
            update_board_member(99999, {'name': 'Test'})
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass


class TestEndAppointment:
    def test_end_appointment(self, logged_in_client):
        co = _setup_company(logged_in_client)
        member = create_board_member(co.id, {
            'name': 'Leaving Member', 'role': 'ledamot', 'appointed_date': date(2024, 1, 1)
        })
        assert member.is_active is True
        result = end_appointment(member.id, date(2024, 12, 31))
        assert result.end_date == date(2024, 12, 31)
        assert result.is_active is False


class TestGetBoardMembers:
    def test_active_only(self, logged_in_client):
        co = _setup_company(logged_in_client)
        create_board_member(co.id, {
            'name': 'Active', 'role': 'ordforande', 'appointed_date': date(2024, 1, 1)
        })
        m2 = create_board_member(co.id, {
            'name': 'Left', 'role': 'ledamot', 'appointed_date': date(2020, 1, 1)
        })
        end_appointment(m2.id, date(2023, 12, 31))

        active = get_board_members(co.id, active_only=True)
        assert len(active) == 1
        assert active[0].name == 'Active'

        all_members = get_board_members(co.id, active_only=False)
        assert len(all_members) == 2

    def test_for_annual_report(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)

        # Active during 2024
        create_board_member(co.id, {
            'name': 'During FY', 'role': 'ordforande', 'appointed_date': date(2023, 1, 1)
        })
        # Left before 2024
        m2 = create_board_member(co.id, {
            'name': 'Before FY', 'role': 'ledamot', 'appointed_date': date(2020, 1, 1)
        })
        end_appointment(m2.id, date(2022, 12, 31))
        # Appointed after 2024
        create_board_member(co.id, {
            'name': 'After FY', 'role': 'suppleant', 'appointed_date': date(2025, 3, 1)
        })

        members = get_board_for_annual_report(co.id, fy.id)
        assert len(members) == 1
        assert members[0].name == 'During FY'


# ---------------------------------------------------------------------------
# Share Classes
# ---------------------------------------------------------------------------

class TestShareClasses:
    def test_create_share_class(self, logged_in_client):
        co = _setup_company(logged_in_client)
        sc = create_share_class(co.id, {
            'name': 'A',
            'votes_per_share': 10,
            'par_value': 100,
            'total_shares': 1000,
        })
        assert sc.id is not None
        assert sc.name == 'A'
        assert sc.votes_per_share == 10

    def test_get_share_classes(self, logged_in_client):
        co = _setup_company(logged_in_client)
        create_share_class(co.id, {'name': 'B', 'total_shares': 500})
        create_share_class(co.id, {'name': 'A', 'total_shares': 1000})
        classes = get_share_classes(co.id)
        assert len(classes) == 2
        assert classes[0].name == 'A'  # Sorted by name


# ---------------------------------------------------------------------------
# Shareholders
# ---------------------------------------------------------------------------

class TestShareholders:
    def test_create_shareholder(self, logged_in_client):
        co = _setup_company(logged_in_client)
        sh = create_shareholder(co.id, {
            'name': 'Carl Familj',
            'personal_or_org_number': '19700101-1234',
        })
        assert sh.id is not None
        assert sh.name == 'Carl Familj'
        assert sh.is_company is False

    def test_create_company_shareholder(self, logged_in_client):
        co = _setup_company(logged_in_client)
        sh = create_shareholder(co.id, {
            'name': 'Holding AB',
            'personal_or_org_number': '556001-1234',
            'is_company': True,
        })
        assert sh.is_company is True


# ---------------------------------------------------------------------------
# Holdings & Ownership
# ---------------------------------------------------------------------------

class TestHoldings:
    def test_add_holding(self, logged_in_client):
        co = _setup_company(logged_in_client)
        sc = create_share_class(co.id, {'name': 'A', 'total_shares': 1000})
        sh = create_shareholder(co.id, {'name': 'Anna Ägare'})

        holding = add_holding(sh.id, {
            'share_class_id': sc.id,
            'shares': 600,
            'acquired_date': date(2020, 1, 1),
            'acquisition_type': 'grundande',
            'price_per_share': 100,
        })
        assert holding.shares == 600
        assert holding.acquisition_label == 'Grundande'

    def test_add_holding_invalid_shareholder(self, logged_in_client):
        _setup_company(logged_in_client)
        try:
            add_holding(99999, {
                'share_class_id': 1, 'shares': 100,
                'acquired_date': date(2024, 1, 1),
            })
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass


class TestOwnershipSummary:
    def test_ownership_calculation(self, logged_in_client):
        co = _setup_company(logged_in_client)
        sc_a = create_share_class(co.id, {'name': 'A', 'votes_per_share': 10, 'total_shares': 1000})
        sc_b = create_share_class(co.id, {'name': 'B', 'votes_per_share': 1, 'total_shares': 5000})

        sh1 = create_shareholder(co.id, {'name': 'Ägare 1'})
        sh2 = create_shareholder(co.id, {'name': 'Ägare 2'})

        add_holding(sh1.id, {'share_class_id': sc_a.id, 'shares': 600, 'acquired_date': date(2020, 1, 1)})
        add_holding(sh1.id, {'share_class_id': sc_b.id, 'shares': 2000, 'acquired_date': date(2020, 1, 1)})
        add_holding(sh2.id, {'share_class_id': sc_a.id, 'shares': 400, 'acquired_date': date(2020, 1, 1)})
        add_holding(sh2.id, {'share_class_id': sc_b.id, 'shares': 3000, 'acquired_date': date(2020, 1, 1)})

        summary = get_ownership_summary(co.id)
        assert len(summary) == 2

        # sh2 has 3400 shares total, sh1 has 2600
        assert summary[0]['shareholder'].name == 'Ägare 2'  # most shares
        assert summary[0]['total_shares'] == 3400
        assert summary[0]['pct'] == round(3400 / 6000 * 100, 2)

        # Votes: sh1 = 600*10 + 2000*1 = 8000, sh2 = 400*10 + 3000*1 = 7000
        sh1_row = [s for s in summary if s['shareholder'].name == 'Ägare 1'][0]
        assert sh1_row['total_votes'] == 8000

    def test_empty_ownership(self, logged_in_client):
        co = _setup_company(logged_in_client)
        summary = get_ownership_summary(co.id)
        assert summary == []


class TestShareRegister:
    def test_register(self, logged_in_client):
        co = _setup_company(logged_in_client)
        sc = create_share_class(co.id, {'name': 'A', 'total_shares': 1000})
        sh = create_shareholder(co.id, {'name': 'Anna'})
        add_holding(sh.id, {'share_class_id': sc.id, 'shares': 500, 'acquired_date': date(2020, 1, 1)})

        register = get_share_register(co.id)
        assert len(register) == 1
        assert register[0]['shareholder'].name == 'Anna'
        assert register[0]['shares'] == 500


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

class TestDividends:
    def test_create_dividend_decision(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)

        div = create_dividend_decision(co.id, {
            'fiscal_year_id': fy.id,
            'decision_date': date(2025, 5, 15),
            'total_amount': 100000,
            'amount_per_share': 100,
        })
        assert div.id is not None
        assert div.status == 'beslutad'
        assert float(div.total_amount) == 100000.0

    def test_pay_dividend(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_accounts(co)

        div = create_dividend_decision(co.id, {
            'fiscal_year_id': fy.id,
            'decision_date': date(2025, 5, 15),
            'total_amount': 50000,
            'payment_date': date(2025, 6, 1),
        })

        result = pay_dividend(div.id, fy.id, created_by=1)
        assert result.status == 'betald'
        assert result.verification_id is not None

    def test_pay_already_paid_raises(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_accounts(co)

        div = create_dividend_decision(co.id, {
            'fiscal_year_id': fy.id,
            'decision_date': date(2025, 5, 15),
            'total_amount': 50000,
        })
        pay_dividend(div.id, fy.id)

        try:
            pay_dividend(div.id, fy.id)
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass

    def test_get_dividends(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)

        create_dividend_decision(co.id, {
            'fiscal_year_id': fy.id, 'decision_date': date(2025, 3, 1), 'total_amount': 10000
        })
        create_dividend_decision(co.id, {
            'fiscal_year_id': fy.id, 'decision_date': date(2025, 5, 1), 'total_amount': 20000
        })

        divs = get_dividends(co.id)
        assert len(divs) == 2
        # Most recent first
        assert float(divs[0].total_amount) == 20000.0


# ---------------------------------------------------------------------------
# AGM Minutes
# ---------------------------------------------------------------------------

class TestAGMMinutes:
    def test_create_agm(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)

        agm = create_agm_minutes(co.id, {
            'meeting_date': date(2025, 5, 15),
            'meeting_type': 'arsstamma',
            'fiscal_year_id': fy.id,
            'chairman': 'Anna Svensson',
            'minutes_taker': 'Erik Johansson',
            'resolutions': 'Fastställande av resultat- och balansräkning.',
            'attendees': 'Anna Svensson\nErik Johansson',
        })
        assert agm.id is not None
        assert agm.meeting_type_label == 'Årsstämma'
        assert agm.chairman == 'Anna Svensson'

    def test_create_extra_stamma(self, logged_in_client):
        co = _setup_company(logged_in_client)
        agm = create_agm_minutes(co.id, {
            'meeting_date': date(2025, 10, 1),
            'meeting_type': 'extra_stamma',
        })
        assert agm.meeting_type_label == 'Extra bolagsstämma'

    def test_get_agm_history(self, logged_in_client):
        co = _setup_company(logged_in_client)
        create_agm_minutes(co.id, {'meeting_date': date(2024, 5, 1), 'meeting_type': 'arsstamma'})
        create_agm_minutes(co.id, {'meeting_date': date(2025, 5, 1), 'meeting_type': 'arsstamma'})

        history = get_agm_history(co.id)
        assert len(history) == 2
        assert history[0].meeting_date == date(2025, 5, 1)  # Most recent first

    def test_get_single_agm(self, logged_in_client):
        co = _setup_company(logged_in_client)
        agm = create_agm_minutes(co.id, {'meeting_date': date(2025, 5, 1)})
        fetched = get_agm(agm.id)
        assert fetched.id == agm.id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestBoardRoutes:
    def test_board_list(self, logged_in_client):
        co = _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/board')
        assert resp.status_code == 200
        assert 'Styrelse' in resp.data.decode()

    def test_board_new_get(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/board/new')
        assert resp.status_code == 200
        assert 'Ny styrelseledamot' in resp.data.decode()

    def test_board_new_post(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.post('/governance/board/new', data={
            'name': 'Board Test',
            'role': 'ledamot',
            'appointed_date': '2024-01-01',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Board Test' in resp.data.decode()

    def test_board_edit(self, logged_in_client):
        co = _setup_company(logged_in_client)
        member = create_board_member(co.id, {
            'name': 'Edit Me', 'role': 'ledamot', 'appointed_date': date(2024, 1, 1)
        })
        resp = logged_in_client.get(f'/governance/board/{member.id}/edit')
        assert resp.status_code == 200
        assert 'Edit Me' in resp.data.decode()

    def test_board_end(self, logged_in_client):
        co = _setup_company(logged_in_client)
        member = create_board_member(co.id, {
            'name': 'End Me', 'role': 'ledamot', 'appointed_date': date(2024, 1, 1)
        })
        resp = logged_in_client.post(f'/governance/board/{member.id}/end', data={
            'end_date': '2024-12-31',
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestShareRoutes:
    def test_shares_page(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/shares')
        assert resp.status_code == 200
        assert 'Aktiebok' in resp.data.decode()

    def test_share_class_new(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.post('/governance/shares/classes/new', data={
            'name': 'A',
            'votes_per_share': '10',
            'total_shares': '1000',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Aktieslag' in resp.data.decode()

    def test_shareholder_new(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.post('/governance/shares/shareholders/new', data={
            'name': 'Test Ägare',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_holding_new_get(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/shares/holdings/new')
        assert resp.status_code == 200
        assert 'aktieinnehav' in resp.data.decode().lower()

    def test_share_register(self, logged_in_client):
        co = _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/shares/register')
        assert resp.status_code == 200
        assert 'Aktiebok' in resp.data.decode()


class TestDividendRoutes:
    def test_dividends_page(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/dividends')
        assert resp.status_code == 200
        assert 'Utdelningar' in resp.data.decode()

    def test_dividend_new_get(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        resp = logged_in_client.get('/governance/dividends/new')
        assert resp.status_code == 200
        assert 'utdelningsbeslut' in resp.data.decode().lower()

    def test_dividend_pay_route(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)

        div = create_dividend_decision(co.id, {
            'fiscal_year_id': fy.id,
            'decision_date': date(2025, 5, 15),
            'total_amount': 25000,
        })
        resp = logged_in_client.post(f'/governance/dividends/{div.id}/pay',
                                      follow_redirects=True)
        assert resp.status_code == 200


class TestAGMRoutes:
    def test_agm_list(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/governance/agm')
        assert resp.status_code == 200
        assert 'Bolagsstämmor' in resp.data.decode()

    def test_agm_new_get(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        resp = logged_in_client.get('/governance/agm/new')
        assert resp.status_code == 200
        assert 'bolagsstämma' in resp.data.decode().lower()

    def test_agm_new_post(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        resp = logged_in_client.post('/governance/agm/new', data={
            'meeting_date': '2025-05-15',
            'meeting_type': 'arsstamma',
            'fiscal_year_id': str(fy.id),
            'chairman': 'Anna Svensson',
            'minutes_taker': 'Erik Johansson',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_agm_view(self, logged_in_client):
        co = _setup_company(logged_in_client)
        agm = create_agm_minutes(co.id, {
            'meeting_date': date(2025, 5, 15),
            'meeting_type': 'arsstamma',
            'resolutions': 'Godkänt resultat.',
        })
        resp = logged_in_client.get(f'/governance/agm/{agm.id}')
        assert resp.status_code == 200
        assert 'Godkänt resultat' in resp.data.decode()


# ---------------------------------------------------------------------------
# Annual Report Integration
# ---------------------------------------------------------------------------

class TestAnnualReportIntegration:
    def test_board_members_in_report(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)

        create_board_member(co.id, {
            'name': 'VD Person', 'role': 'vd', 'appointed_date': date(2023, 1, 1)
        })
        create_board_member(co.id, {
            'name': 'Ordf Person', 'role': 'ordforande', 'appointed_date': date(2023, 1, 1)
        })

        members = get_board_for_annual_report(co.id, fy.id)
        assert len(members) == 2
        # Sorted by role then name
        names = [m.name for m in members]
        assert 'VD Person' in names
        assert 'Ordf Person' in names
