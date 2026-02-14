"""Tests for Phase 5A: Årsredovisning (Annual Report) — K2."""
from datetime import date

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.salary import Employee
from app.models.annual_report import AnnualReport
from app.services.annual_report_service import (
    get_or_create_report, save_report, get_multi_year_overview,
    get_average_employees, finalize_report, reopen_report,
    get_k2_boilerplate, K2_BOILERPLATE,
)


def _setup_company(logged_in_client, company_type='AB'):
    """Create company and set as active."""
    co = Company(name='ÅR Test AB', org_number='556000-5500', company_type=company_type)
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


def _setup_fy(company, year=2024):
    """Create a fiscal year."""
    fy = FiscalYear(company_id=company.id, year=year,
                    start_date=date(year, 1, 1), end_date=date(year, 12, 31))
    db.session.add(fy)
    db.session.commit()
    return fy


def _add_accounts_and_transactions(company, fy):
    """Add revenue and expense accounts with transactions."""
    rev = Account(company_id=company.id, account_number='3010',
                  name='Försäljning', account_type='revenue', active=True)
    exp = Account(company_id=company.id, account_number='5010',
                  name='Lokalhyra', account_type='expense', active=True)
    bank = Account(company_id=company.id, account_number='1930',
                   name='Företagskonto', account_type='asset', active=True)
    db.session.add_all([rev, exp, bank])
    db.session.commit()

    # Revenue verification
    ver1 = Verification(company_id=company.id, fiscal_year_id=fy.id,
                        verification_number=1, verification_date=date(fy.year, 3, 15),
                        description='Faktura', verification_type='customer')
    db.session.add(ver1)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=ver1.id, account_id=bank.id,
                        debit=100000, credit=0),
        VerificationRow(verification_id=ver1.id, account_id=rev.id,
                        debit=0, credit=100000),
    ])

    # Expense verification
    ver2 = Verification(company_id=company.id, fiscal_year_id=fy.id,
                        verification_number=2, verification_date=date(fy.year, 6, 1),
                        description='Hyra', verification_type='supplier')
    db.session.add(ver2)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=ver2.id, account_id=exp.id,
                        debit=30000, credit=0),
        VerificationRow(verification_id=ver2.id, account_id=bank.id,
                        debit=0, credit=30000),
    ])
    db.session.commit()
    return rev, exp, bank


def _add_employees(company, fy):
    """Add employees for testing average count."""
    e1 = Employee(company_id=company.id, personal_number='19800101-1234',
                  first_name='Anna', last_name='Svensson',
                  employment_start=date(2020, 1, 1), monthly_salary=35000,
                  tax_table='33', tax_column=1, pension_plan='ITP1')
    e2 = Employee(company_id=company.id, personal_number='19850515-5678',
                  first_name='Erik', last_name='Johansson',
                  employment_start=date(2022, 6, 1), monthly_salary=40000,
                  tax_table='33', tax_column=1, pension_plan='ITP1')
    # Employee who ended mid-year (still overlaps FY)
    e3 = Employee(company_id=company.id, personal_number='19900301-9012',
                  first_name='Lisa', last_name='Karlsson',
                  employment_start=date(2021, 1, 1),
                  employment_end=date(fy.year, 6, 30),
                  monthly_salary=32000, tax_table='33', tax_column=1,
                  pension_plan='ITP1')
    db.session.add_all([e1, e2, e3])
    db.session.commit()
    return [e1, e2, e3]


# ---------------------------------------------------------------------------
# Service: get_or_create_report
# ---------------------------------------------------------------------------

class TestGetOrCreate:
    def test_create_new_report(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)

        report = get_or_create_report(co.id, fy.id)
        assert report is not None
        assert report.status == 'draft'
        assert report.company_id == co.id
        assert report.fiscal_year_id == fy.id
        assert 'K2' in report.redovisningsprinciper

    def test_get_existing_report(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)

        r1 = get_or_create_report(co.id, fy.id)
        r2 = get_or_create_report(co.id, fy.id)
        assert r1.id == r2.id


# ---------------------------------------------------------------------------
# Service: save_report
# ---------------------------------------------------------------------------

class TestSaveReport:
    def test_save_all_fields(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        report = get_or_create_report(co.id, fy.id)

        data = {
            'verksamhet': 'Bolaget bedriver konsultverksamhet.',
            'vasentliga_handelser': 'Ny storkund.',
            'handelser_efter_fy': 'Inga väsentliga händelser.',
            'framtida_utveckling': 'Fortsatt tillväxt.',
            'resultatdisposition': 'Balanseras i ny räkning.',
            'redovisningsprinciper': 'K2-principer.',
            'extra_noter': 'Extra not 1---Extra not 2',
            'board_members': 'Anna Svensson\nErik Johansson',
            'signing_location': 'Stockholm',
            'signing_date': date(2025, 3, 15),
        }
        result = save_report(report.id, data)
        assert result.verksamhet == 'Bolaget bedriver konsultverksamhet.'
        assert result.signing_location == 'Stockholm'
        assert result.board_members == 'Anna Svensson\nErik Johansson'

    def test_save_partial_fields(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        report = get_or_create_report(co.id, fy.id)

        save_report(report.id, {'verksamhet': 'Bara verksamhet.'})
        refreshed = db.session.get(AnnualReport, report.id)
        assert refreshed.verksamhet == 'Bara verksamhet.'
        assert refreshed.vasentliga_handelser is None


# ---------------------------------------------------------------------------
# Service: multi_year_overview
# ---------------------------------------------------------------------------

class TestMultiYearOverview:
    def test_multi_year_with_data(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy1 = _setup_fy(co, 2023)
        fy2 = _setup_fy(co, 2024)
        _add_accounts_and_transactions(co, fy2)

        overview = get_multi_year_overview(co.id, fy2.id, num_years=2)
        assert len(overview) == 2
        # First entry is 2024 (most recent)
        assert overview[0]['year'] == 2024
        assert overview[0]['revenue'] == 100000.0

    def test_multi_year_single_fy(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)

        overview = get_multi_year_overview(co.id, fy.id, num_years=3)
        assert len(overview) == 1
        assert overview[0]['year'] == fy.year


# ---------------------------------------------------------------------------
# Service: average employees
# ---------------------------------------------------------------------------

class TestAverageEmployees:
    def test_average_employees_active(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_employees(co, fy)

        count = get_average_employees(co.id, fy.id)
        assert count == 3  # All 3 overlap the FY

    def test_average_employees_partial(self, logged_in_client):
        """Employee who ended before FY should not count."""
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        e = Employee(company_id=co.id, personal_number='19700101-0001',
                     first_name='Old', last_name='Worker',
                     employment_start=date(2010, 1, 1),
                     employment_end=date(2023, 6, 30),
                     monthly_salary=30000, tax_table='33', tax_column=1,
                     pension_plan='ITP1')
        db.session.add(e)
        db.session.commit()

        count = get_average_employees(co.id, fy.id)
        assert count == 0  # Ended before FY 2024

    def test_average_employees_none(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)

        count = get_average_employees(co.id, fy.id)
        assert count == 0


# ---------------------------------------------------------------------------
# Service: finalize / reopen
# ---------------------------------------------------------------------------

class TestFinalizeReopen:
    def test_finalize_sets_final(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        report = get_or_create_report(co.id, fy.id)

        result = finalize_report(report.id)
        assert result.status == 'final'

    def test_reopen_sets_draft(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        report = get_or_create_report(co.id, fy.id)
        finalize_report(report.id)

        result = reopen_report(report.id)
        assert result.status == 'draft'


# ---------------------------------------------------------------------------
# K2 boilerplate
# ---------------------------------------------------------------------------

class TestK2Boilerplate:
    def test_k2_boilerplate_content(self, app):
        text = get_k2_boilerplate()
        assert 'K2' in text
        assert 'årsredovisningslagen' in text
        assert 'BFNAR 2016:10' in text


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_index_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)

        response = logged_in_client.get('/annual-report/')
        assert response.status_code == 200
        assert 'Årsredovisning' in response.data.decode()

    def test_edit_page(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)

        response = logged_in_client.get(f'/annual-report/edit/{fy.id}')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'Förvaltningsberättelse' in html

        # Should have created a report
        report = AnnualReport.query.filter_by(
            company_id=co.id, fiscal_year_id=fy.id).first()
        assert report is not None

    def test_readonly_cannot_edit(self, readonly_client):
        """Readonly user should be redirected when trying to edit."""
        co = Company(name='RO Test AB', org_number='556000-5510', company_type='AB')
        db.session.add(co)
        db.session.commit()
        fy = _setup_fy(co)

        with readonly_client.session_transaction() as sess:
            sess['active_company_id'] = co.id

        response = readonly_client.get(f'/annual-report/edit/{fy.id}')
        assert response.status_code == 302  # Redirected
