"""Tests for salary_service functions."""

from datetime import date
from decimal import Decimal
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.models.salary import Employee, SalaryRun, SalaryEntry
from app.services.salary_service import (
    calculate_tax_deduction,
    calculate_employer_contributions,
    calculate_pension,
    create_salary_run,
    recalculate_salary_entry,
    recalculate_all_entries,
    approve_salary_run,
    mark_salary_run_paid,
    generate_salary_slip,
    generate_agi_data,
    generate_collectum_data,
)


@pytest.fixture
def salary_company(db):
    """Create a company with fiscal year, accounts, and employees."""
    company = Company(
        name='LönTestAB',
        org_number='5566001122',
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

    # Create required accounts
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

    db.session.flush()

    # Create employees
    emp1 = Employee(
        company_id=company.id,
        personal_number='19900101-1234',
        first_name='Anna',
        last_name='Svensson',
        employment_start=date(2025, 1, 1),
        monthly_salary=Decimal('40000'),
        tax_table='33',
        tax_column=1,
        pension_plan='ITP1',
    )
    emp2 = Employee(
        company_id=company.id,
        personal_number='19850515-5678',
        first_name='Erik',
        last_name='Johansson',
        employment_start=date(2025, 3, 1),
        monthly_salary=Decimal('35000'),
        tax_table='30',
        tax_column=1,
        pension_plan='ITP2',
    )
    emp3 = Employee(
        company_id=company.id,
        personal_number='19950101-9012',
        first_name='Lisa',
        last_name='Nilsson',
        employment_start=date(2025, 6, 1),
        monthly_salary=Decimal('30000'),
        tax_table='28',
        tax_column=1,
        pension_plan='none',
        active=False,  # Inactive
    )
    db.session.add_all([emp1, emp2, emp3])
    db.session.commit()
    return company, fy, [emp1, emp2, emp3]


class TestTaxDeduction:
    def test_basic_tax(self):
        tax = calculate_tax_deduction(40000, '33', 1)
        assert tax == Decimal('13200')

    def test_zero_salary(self):
        tax = calculate_tax_deduction(0, '33', 1)
        assert tax == Decimal('0')

    def test_column_adjustment(self):
        # Column 2 reduces by 2%
        tax_col1 = calculate_tax_deduction(40000, '33', 1)
        tax_col2 = calculate_tax_deduction(40000, '33', 2)
        assert tax_col1 == Decimal('13200')  # 33%
        assert tax_col2 == Decimal('12400')  # 31%

    def test_column_4_increases(self):
        # Column 4 increases by 2%
        tax = calculate_tax_deduction(40000, '33', 4)
        assert tax == Decimal('14000')  # 35%


class TestEmployerContributions:
    def test_standard_rate(self):
        result = calculate_employer_contributions(40000)
        assert result == Decimal('12568.00')

    def test_young_employee(self):
        result = calculate_employer_contributions(40000, birth_year=2002)
        assert result == Decimal('4084.00')

    def test_senior_employee(self):
        result = calculate_employer_contributions(40000, birth_year=1955)
        assert result == Decimal('4084.00')


class TestPension:
    def test_itp1_below_threshold(self):
        # 40000 < 7.5 * 80000 / 12 = 50000
        result = calculate_pension(40000, 'ITP1')
        assert result == Decimal('1800.00')

    def test_itp1_above_threshold(self):
        # 60000 > 50000 threshold
        result = calculate_pension(60000, 'ITP1')
        # 50000 * 4.5% + 10000 * 30% = 2250 + 3000 = 5250
        assert result == Decimal('5250.00')

    def test_itp2(self):
        result = calculate_pension(35000, 'ITP2')
        assert result == Decimal('1575.00')

    def test_no_pension(self):
        result = calculate_pension(30000, 'none')
        assert result == Decimal('0')

    def test_empty_plan(self):
        result = calculate_pension(30000, '')
        assert result == Decimal('0')


class TestSalaryRun:
    def test_create_run(self, db, salary_company):
        company, fy, employees = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 3)
        assert run.status == 'draft'
        # Only 2 active employees
        assert len(run.entries) == 2
        assert run.total_gross == Decimal('75000')  # 40000 + 35000

    def test_duplicate_run_raises(self, db, salary_company):
        company, fy, _ = salary_company
        create_salary_run(company.id, fy.id, 2026, 3)
        with pytest.raises(ValueError, match='finns redan'):
            create_salary_run(company.id, fy.id, 2026, 3)

    def test_entries_calculated_correctly(self, db, salary_company):
        company, fy, employees = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 4)

        anna_entry = [e for e in run.entries if e.employee.first_name == 'Anna'][0]
        assert anna_entry.gross_salary == Decimal('40000')
        assert anna_entry.tax_deduction == Decimal('13200')  # 33%
        assert anna_entry.net_salary == Decimal('26800')
        assert anna_entry.employer_contributions == Decimal('12568.00')
        assert anna_entry.pension_amount == Decimal('1800.00')  # ITP1

    def test_recalculate_entry(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 5)
        entry = run.entries[0]
        original_gross = entry.gross_salary

        recalculate_salary_entry(entry.id, overrides={
            'gross_salary': 45000,
        })
        db.session.refresh(entry)
        assert entry.gross_salary == Decimal('45000')
        assert entry.gross_salary != original_gross

    def test_recalculate_all(self, db, salary_company):
        company, fy, employees = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 6)
        # Change employee salary
        employees[0].monthly_salary = Decimal('50000')
        db.session.commit()

        recalculate_all_entries(run.id)
        db.session.refresh(run)
        anna_entry = [e for e in run.entries if e.employee.first_name == 'Anna'][0]
        assert anna_entry.gross_salary == Decimal('50000')


class TestApproval:
    def test_approve_creates_verification(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 7)
        approve_salary_run(run.id, user_id=1)

        db.session.refresh(run)
        assert run.status == 'approved'
        assert run.verification_id is not None
        assert run.verification.verification_type == 'salary'
        assert run.verification.is_balanced

    def test_approve_non_draft_raises(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 8)
        approve_salary_run(run.id, user_id=1)
        with pytest.raises(ValueError, match='utkast'):
            approve_salary_run(run.id, user_id=1)

    def test_mark_paid(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 9)
        approve_salary_run(run.id, user_id=1)
        mark_salary_run_paid(run.id, date(2026, 9, 25))

        db.session.refresh(run)
        assert run.status == 'paid'
        assert run.paid_date == date(2026, 9, 25)


class TestReporting:
    def test_salary_slip(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 10)
        entry = run.entries[0]
        slip = generate_salary_slip(entry)
        assert 'company' in slip
        assert 'employee' in slip
        assert slip['gross_salary'] == entry.gross_salary

    def test_agi_data(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 11)
        agi = generate_agi_data(run)
        assert len(agi['entries']) == 2
        assert agi['total_gross'] == run.total_gross

    def test_collectum_data(self, db, salary_company):
        company, fy, _ = salary_company
        run = create_salary_run(company.id, fy.id, 2026, 12)
        data = generate_collectum_data(company.id, 2026, 12)
        # emp1 has ITP1, emp2 has ITP2 → both show in collectum
        assert len(data['entries']) == 2

    def test_collectum_no_run(self, db, salary_company):
        company, _, _ = salary_company
        data = generate_collectum_data(company.id, 2025, 1)
        assert data is None
