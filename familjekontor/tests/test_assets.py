"""Tests for Phase 5B: Asset Management (Anläggningstillgångar)."""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.models.asset import FixedAsset, DepreciationRun, DepreciationEntry, ASSET_CATEGORY_DEFAULTS
from app.services.asset_service import (
    create_asset, update_asset, get_assets, get_asset,
    get_accumulated_depreciation, calculate_monthly_depreciation,
    generate_depreciation_run, post_depreciation_run, dispose_asset,
    get_depreciation_schedule, get_asset_note_data,
)


def _setup_company(logged_in_client):
    co = Company(name='Asset Test AB', org_number='556000-6600', company_type='AB')
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
    """Add required BAS accounts."""
    accts = [
        Account(company_id=company.id, account_number='1220', name='Inventarier', account_type='asset', active=True),
        Account(company_id=company.id, account_number='1229', name='Ack avskr inventarier', account_type='asset', active=True),
        Account(company_id=company.id, account_number='7832', name='Avskr inventarier', account_type='expense', active=True),
        Account(company_id=company.id, account_number='1930', name='Företagskonto', account_type='asset', active=True),
        Account(company_id=company.id, account_number='3973', name='Vinst avyttring', account_type='revenue', active=True),
        Account(company_id=company.id, account_number='7973', name='Förlust avyttring', account_type='expense', active=True),
    ]
    db.session.add_all(accts)
    db.session.commit()
    return accts


def _create_test_asset(company, data_overrides=None):
    """Create an asset with defaults."""
    data = {
        'name': 'Kontorsmöbler',
        'asset_category': 'inventarier',
        'purchase_date': date(2024, 1, 15),
        'purchase_amount': 60000,
        'depreciation_method': 'straight_line',
        'useful_life_months': 60,
        'residual_value': 0,
    }
    if data_overrides:
        data.update(data_overrides)
    return create_asset(company.id, data)


# ---------------------------------------------------------------------------
# Service: create_asset
# ---------------------------------------------------------------------------

class TestCreateAsset:
    def test_create_basic(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        asset = _create_test_asset(co)
        assert asset is not None
        assert asset.name == 'Kontorsmöbler'
        assert asset.asset_number.startswith('AT-')
        assert asset.status == 'active'
        assert asset.asset_account == '1220'
        assert asset.depreciation_account == '1229'
        assert asset.expense_account == '7832'
        assert asset.useful_life_months == 60

    def test_create_with_custom_accounts(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        asset = _create_test_asset(co, {
            'asset_account': '1250',
            'depreciation_account': '1259',
            'expense_account': '7835',
            'asset_category': 'datorer',
        })
        assert asset.asset_account == '1250'
        assert asset.useful_life_months == 60  # overridden from datorer default (36)

    def test_create_auto_number_sequence(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        a1 = _create_test_asset(co)
        a2 = _create_test_asset(co, {'name': 'Skrivbord'})
        # Should get sequential numbers
        n1 = int(a1.asset_number.split('-')[-1])
        n2 = int(a2.asset_number.split('-')[-1])
        assert n2 == n1 + 1

    def test_create_invalid_category(self, logged_in_client):
        co = _setup_company(logged_in_client)
        try:
            _create_test_asset(co, {'asset_category': 'invalid'})
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Service: update_asset
# ---------------------------------------------------------------------------

class TestUpdateAsset:
    def test_update_fields(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co)

        updated = update_asset(asset.id, {'name': 'Uppdaterad', 'supplier_name': 'IKEA'})
        assert updated.name == 'Uppdaterad'
        assert updated.supplier_name == 'IKEA'


# ---------------------------------------------------------------------------
# Service: calculate_monthly_depreciation
# ---------------------------------------------------------------------------

class TestDepreciationCalc:
    def test_straight_line(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co, {
            'purchase_amount': 60000,
            'useful_life_months': 60,
            'residual_value': 0,
        })

        monthly = calculate_monthly_depreciation(asset)
        assert monthly == Decimal('1000.00')

    def test_straight_line_with_residual(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co, {
            'purchase_amount': 60000,
            'useful_life_months': 60,
            'residual_value': 6000,
        })

        monthly = calculate_monthly_depreciation(asset)
        assert monthly == Decimal('900.00')  # (60000 - 6000) / 60

    def test_declining_balance(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co, {
            'purchase_amount': 60000,
            'useful_life_months': 60,
            'residual_value': 0,
            'depreciation_method': 'declining_balance',
        })

        monthly = calculate_monthly_depreciation(asset)
        # Rate = 2/60 = 0.0333..., 60000 * 0.0333 = 2000
        assert monthly == Decimal('2000.00')

    def test_disposed_asset_zero(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co)
        asset.status = 'disposed'
        db.session.commit()

        monthly = calculate_monthly_depreciation(asset)
        assert monthly == Decimal('0')


# ---------------------------------------------------------------------------
# Service: generate + post depreciation run
# ---------------------------------------------------------------------------

class TestDepreciationRun:
    def test_generate_run(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        _create_test_asset(co)

        run = generate_depreciation_run(co.id, fy.id, date(2024, 1, 31))
        assert run.status == 'pending'
        assert float(run.total_amount) == 1000.0
        assert len(run.entries) == 1

    def test_generate_run_skips_not_started(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        _create_test_asset(co, {'depreciation_start': date(2024, 6, 1)})

        run = generate_depreciation_run(co.id, fy.id, date(2024, 1, 31))
        assert float(run.total_amount) == 0

    def test_post_run_creates_verification(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        _create_test_asset(co)

        run = generate_depreciation_run(co.id, fy.id, date(2024, 1, 31))
        posted = post_depreciation_run(run.id)
        assert posted.status == 'posted'
        assert posted.verification_id is not None

    def test_post_run_already_posted(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        _create_test_asset(co)

        run = generate_depreciation_run(co.id, fy.id, date(2024, 1, 31))
        post_depreciation_run(run.id)

        try:
            post_depreciation_run(run.id)
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass

    def test_fully_depreciated_status(self, logged_in_client):
        """Asset should be marked fully_depreciated when book value reaches residual."""
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        # Very short useful life
        asset = _create_test_asset(co, {
            'purchase_amount': 1000,
            'useful_life_months': 1,
            'residual_value': 0,
        })

        run = generate_depreciation_run(co.id, fy.id, date(2024, 1, 31))
        post_depreciation_run(run.id)

        refreshed = db.session.get(FixedAsset, asset.id)
        assert refreshed.status == 'fully_depreciated'


# ---------------------------------------------------------------------------
# Service: dispose_asset
# ---------------------------------------------------------------------------

class TestDisposeAsset:
    def test_dispose_with_gain(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        asset = _create_test_asset(co, {'purchase_amount': 10000})

        # Dispose for more than book value (no depreciation yet)
        disposed = dispose_asset(asset.id, date(2024, 6, 1), 12000, fy.id)
        assert disposed.status == 'disposed'
        assert disposed.disposal_verification_id is not None

    def test_dispose_with_loss(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        asset = _create_test_asset(co, {'purchase_amount': 10000})

        disposed = dispose_asset(asset.id, date(2024, 6, 1), 5000, fy.id)
        assert disposed.status == 'disposed'
        assert float(disposed.disposal_amount) == 5000

    def test_dispose_already_disposed(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        asset = _create_test_asset(co, {'purchase_amount': 10000})
        dispose_asset(asset.id, date(2024, 6, 1), 5000, fy.id)

        try:
            dispose_asset(asset.id, date(2024, 7, 1), 0, fy.id)
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass

    def test_dispose_zero_proceeds(self, logged_in_client):
        """Scrapping with no sale proceeds."""
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        asset = _create_test_asset(co, {'purchase_amount': 5000})

        disposed = dispose_asset(asset.id, date(2024, 6, 1), 0, fy.id)
        assert disposed.status == 'disposed'


# ---------------------------------------------------------------------------
# Service: depreciation schedule
# ---------------------------------------------------------------------------

class TestDepreciationSchedule:
    def test_schedule_straight_line(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co, {
            'purchase_amount': 12000,
            'useful_life_months': 12,
            'residual_value': 0,
        })

        schedule = get_depreciation_schedule(asset.id)
        assert len(schedule) == 12
        assert schedule[0]['depreciation'] == 1000.0
        assert schedule[-1]['book_value'] == 0.0

    def test_schedule_with_residual(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co, {
            'purchase_amount': 12000,
            'useful_life_months': 12,
            'residual_value': 2000,
        })

        schedule = get_depreciation_schedule(asset.id)
        # Should stop when book value reaches residual
        last = schedule[-1]
        assert last['book_value'] >= 2000.0 - 0.01


# ---------------------------------------------------------------------------
# Service: asset note data
# ---------------------------------------------------------------------------

class TestAssetNote:
    def test_asset_note_data(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_accounts(co)

        # Asset purchased during FY
        _create_test_asset(co, {
            'purchase_date': date(2024, 3, 1),
            'purchase_amount': 50000,
        })

        note = get_asset_note_data(co.id, fy.id)
        assert 'Inventarier, verktyg och installationer' in note
        data = note['Inventarier, verktyg och installationer']
        assert data['purchases'] == 50000.0

    def test_asset_note_opening_balance(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co, 2023)
        fy2024 = _setup_fy(co, 2024)
        _add_accounts(co)

        # Asset purchased before FY 2024
        _create_test_asset(co, {
            'purchase_date': date(2023, 6, 1),
            'purchase_amount': 30000,
        })

        note = get_asset_note_data(co.id, fy2024.id)
        data = note['Inventarier, verktyg och installationer']
        assert data['opening'] == 30000.0
        assert data['purchases'] == 0

    def test_asset_note_empty(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)

        note = get_asset_note_data(co.id, fy.id)
        assert note == {}


# ---------------------------------------------------------------------------
# Service: get_assets filtering
# ---------------------------------------------------------------------------

class TestGetAssets:
    def test_filter_by_status(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        _create_test_asset(co, {'name': 'Active 1'})
        a2 = _create_test_asset(co, {'name': 'Active 2', 'purchase_amount': 5000})
        dispose_asset(a2.id, date(2024, 6, 1), 0, fy.id)

        active = get_assets(co.id, status='active')
        assert len(active) == 1
        assert active[0].name == 'Active 1'

        disposed = get_assets(co.id, status='disposed')
        assert len(disposed) == 1

    def test_filter_by_category(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        _create_test_asset(co, {'asset_category': 'inventarier'})
        _create_test_asset(co, {'name': 'Laptop', 'asset_category': 'datorer'})

        inv = get_assets(co.id, category='inventarier')
        assert len(inv) == 1
        dat = get_assets(co.id, category='datorer')
        assert len(dat) == 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_index_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        response = logged_in_client.get('/assets/')
        assert response.status_code == 200
        assert 'Anläggningstillgångar' in response.data.decode()

    def test_new_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        response = logged_in_client.get('/assets/new')
        assert response.status_code == 200
        assert 'Ny anläggningstillgång' in response.data.decode()

    def test_view_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co)

        response = logged_in_client.get(f'/assets/{asset.id}')
        assert response.status_code == 200
        assert 'Kontorsmöbler' in response.data.decode()

    def test_depreciation_list(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        response = logged_in_client.get('/assets/depreciation')
        assert response.status_code == 200
        assert 'Avskrivningskörningar' in response.data.decode()

    def test_depreciation_new_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        response = logged_in_client.get('/assets/depreciation/new')
        assert response.status_code == 200

    def test_dispose_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        asset = _create_test_asset(co)

        response = logged_in_client.get(f'/assets/{asset.id}/dispose')
        assert response.status_code == 200
        assert 'Avyttra' in response.data.decode()

    def test_readonly_cannot_create(self, readonly_client):
        co = Company(name='RO Test AB', org_number='556000-6610', company_type='AB')
        db.session.add(co)
        db.session.commit()
        _setup_fy(co)

        with readonly_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        response = readonly_client.get('/assets/new')
        assert response.status_code == 302  # Redirected
