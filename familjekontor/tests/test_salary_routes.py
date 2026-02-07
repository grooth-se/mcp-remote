"""Tests for salary routes."""

from datetime import date
from decimal import Decimal
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.models.salary import Employee, SalaryRun
from app.services.salary_service import create_salary_run, approve_salary_run


@pytest.fixture
def salary_setup(db, admin_user):
    """Set up company, fiscal year, accounts, and employee for route tests."""
    company = Company(
        name='RouteTestAB',
        org_number='5566990088',
        company_type='AB',
        vat_period='monthly',
    )
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(
        company_id=company.id,
        year=2026,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.flush()

    for num, name, atype in [
        ('7010', 'Löner tjänstemän', 'expense'),
        ('7510', 'Arbetsgivaravgifter', 'expense'),
        ('7410', 'Pensionspremier', 'expense'),
        ('7090', 'Semesterlöneskuld', 'expense'),
        ('2710', 'Personalens källskatt', 'liability'),
        ('2730', 'Lagstadgade soc.avg', 'liability'),
        ('1930', 'Företagskonto', 'asset'),
        ('2920', 'Upplupna semesterlön', 'liability'),
        ('2950', 'Upplupna pension', 'liability'),
    ]:
        db.session.add(Account(
            company_id=company.id, account_number=num,
            name=name, account_type=atype,
        ))

    emp = Employee(
        company_id=company.id,
        personal_number='19900101-1234',
        first_name='Test',
        last_name='Person',
        employment_start=date(2025, 1, 1),
        monthly_salary=Decimal('40000'),
        tax_table='33',
        tax_column=1,
        pension_plan='ITP1',
    )
    db.session.add(emp)
    db.session.commit()
    return company, fy, emp


def _login_and_set_company(client, company):
    """Log in and set active company in session."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass123',
    }, follow_redirects=True)
    with client.session_transaction() as sess:
        sess['active_company_id'] = company.id


class TestSalaryIndex:
    def test_index_page(self, client, salary_setup):
        company, fy, emp = salary_setup
        _login_and_set_company(client, company)
        resp = client.get('/salary/')
        assert resp.status_code == 200
        assert 'Löneadministration' in resp.data.decode()


class TestEmployeeRoutes:
    def test_employees_list(self, client, salary_setup):
        company, _, _ = salary_setup
        _login_and_set_company(client, company)
        resp = client.get('/salary/employees')
        assert resp.status_code == 200
        assert 'Test Person' in resp.data.decode()

    def test_create_employee(self, client, salary_setup):
        company, _, _ = salary_setup
        _login_and_set_company(client, company)
        resp = client.post('/salary/employees/new', data={
            'personal_number': '19880202-5555',
            'first_name': 'Ny',
            'last_name': 'Anställd',
            'employment_start': '2026-01-01',
            'monthly_salary': '35000',
            'tax_table': '30',
            'tax_column': '1',
            'pension_plan': 'ITP2',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Ny Anställd' in resp.data.decode()

    def test_edit_employee(self, client, salary_setup):
        company, _, emp = salary_setup
        _login_and_set_company(client, company)
        resp = client.get(f'/salary/employees/{emp.id}/edit')
        assert resp.status_code == 200
        assert 'Test' in resp.data.decode()

    def test_deactivate_employee(self, client, db, salary_setup):
        company, _, emp = salary_setup
        _login_and_set_company(client, company)
        resp = client.post(f'/salary/employees/{emp.id}/deactivate',
                           follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(emp)
        assert emp.active is False


class TestSalaryRunRoutes:
    def test_create_run(self, client, salary_setup):
        company, fy, _ = salary_setup
        _login_and_set_company(client, company)
        resp = client.post('/salary/runs/new', data={
            'period_year': '2026',
            'period_month': '3',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'mars 2026' in resp.data.decode().lower()

    def test_view_run(self, client, db, salary_setup):
        company, fy, _ = salary_setup
        _login_and_set_company(client, company)
        run = create_salary_run(company.id, fy.id, 2026, 4)
        resp = client.get(f'/salary/runs/{run.id}')
        assert resp.status_code == 200
        assert 'Test Person' in resp.data.decode()

    def test_approve_run(self, client, db, salary_setup):
        company, fy, _ = salary_setup
        _login_and_set_company(client, company)
        run = create_salary_run(company.id, fy.id, 2026, 5)
        resp = client.post(f'/salary/runs/{run.id}/approve',
                           follow_redirects=True)
        assert resp.status_code == 200
        assert 'Godkänd' in resp.data.decode()

    def test_salary_slips(self, client, db, salary_setup):
        company, fy, _ = salary_setup
        _login_and_set_company(client, company)
        run = create_salary_run(company.id, fy.id, 2026, 6)
        resp = client.get(f'/salary/runs/{run.id}/slips')
        assert resp.status_code == 200
        assert 'Lönespecifikation' in resp.data.decode()
