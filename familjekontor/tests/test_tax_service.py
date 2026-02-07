"""Tests for tax_service functions."""

from datetime import date
from decimal import Decimal
import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.tax import VATReport, Deadline, TaxPayment
from app.services.tax_service import (
    calculate_vat_for_period,
    get_vat_periods_for_year,
    create_vat_report,
    finalize_vat_report,
    seed_deadlines_for_year,
    get_upcoming_deadlines,
    get_overdue_deadlines,
    complete_deadline,
    record_tax_payment,
    list_tax_payments,
    get_tax_payment_summary,
    calculate_employer_tax_for_period,
)


@pytest.fixture
def company_with_data(db):
    """Create a company, fiscal year, accounts, and test verifications."""
    company = Company(
        name='TestAB',
        org_number='5566778899',
        company_type='AB',
        vat_period='quarterly',
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

    # Create VAT accounts
    accts = {}
    for num, name, atype in [
        ('2610', 'Utgående moms 25%', 'liability'),
        ('2620', 'Utgående moms 12%', 'liability'),
        ('2630', 'Utgående moms 6%', 'liability'),
        ('2640', 'Ingående moms', 'asset'),
        ('7510', 'Arbetsgivaravgifter', 'expense'),
        ('7010', 'Löner tjänstemän', 'expense'),
    ]:
        a = Account(company_id=company.id, account_number=num, name=name, account_type=atype)
        db.session.add(a)
        db.session.flush()
        accts[num] = a

    # Create a verification with VAT entries
    ver = Verification(
        company_id=company.id,
        fiscal_year_id=fy.id,
        verification_number=1,
        verification_date=date(2026, 2, 15),
        description='Test sale',
    )
    db.session.add(ver)
    db.session.flush()

    # Output VAT 25%: credit 5000
    db.session.add(VerificationRow(
        verification_id=ver.id, account_id=accts['2610'].id,
        debit=0, credit=5000,
    ))
    # Input VAT: debit 1000
    db.session.add(VerificationRow(
        verification_id=ver.id, account_id=accts['2640'].id,
        debit=1000, credit=0,
    ))
    # Salary: debit 30000
    db.session.add(VerificationRow(
        verification_id=ver.id, account_id=accts['7010'].id,
        debit=30000, credit=0,
    ))
    # Employer tax: debit 9426
    db.session.add(VerificationRow(
        verification_id=ver.id, account_id=accts['7510'].id,
        debit=9426, credit=0,
    ))

    db.session.commit()
    return company, fy


class TestVATCalculation:
    def test_calculate_vat_for_period(self, db, company_with_data):
        company, fy = company_with_data
        result = calculate_vat_for_period(
            company.id, fy.id, date(2026, 1, 1), date(2026, 3, 31)
        )
        assert result['output_vat_25'] == Decimal('5000')
        assert result['output_vat_12'] == Decimal('0')
        assert result['output_vat_6'] == Decimal('0')
        assert result['input_vat'] == Decimal('1000')
        assert result['vat_to_pay'] == Decimal('4000')

    def test_get_vat_periods_quarterly(self, db, company_with_data):
        company, fy = company_with_data
        periods = get_vat_periods_for_year(company.id, 2026)
        assert len(periods) == 4
        assert periods[0]['label'] == 'Q1 2026'
        assert periods[0]['period_start'] == date(2026, 1, 1)
        assert periods[0]['period_end'] == date(2026, 3, 31)

    def test_create_vat_report(self, db, company_with_data):
        company, fy = company_with_data
        periods = get_vat_periods_for_year(company.id, 2026)
        report = create_vat_report(company.id, fy.id, periods[0])
        assert report.id is not None
        assert report.status == 'draft'
        assert report.output_vat_25 == Decimal('5000')
        assert report.vat_to_pay == Decimal('4000')

    def test_finalize_vat_report(self, db, company_with_data):
        company, fy = company_with_data
        periods = get_vat_periods_for_year(company.id, 2026)
        report = create_vat_report(company.id, fy.id, periods[0])
        finalized = finalize_vat_report(report.id)
        assert finalized.status == 'filed'


class TestDeadlines:
    def test_seed_deadlines_for_year(self, db, company_with_data):
        company, fy = company_with_data
        deadlines = seed_deadlines_for_year(company.id, 2026)
        assert len(deadlines) > 0
        # AB quarterly: 4 VAT + 12 employer_tax + 4 corporate_tax + 1 annual_report + 1 tax_return = 22
        types = [d.deadline_type for d in deadlines]
        assert types.count('vat') == 4
        assert types.count('employer_tax') == 12
        assert types.count('corporate_tax') == 4
        assert types.count('annual_report') == 1
        assert types.count('tax_return') == 1

    def test_seed_idempotent(self, db, company_with_data):
        company, fy = company_with_data
        first = seed_deadlines_for_year(company.id, 2026)
        second = seed_deadlines_for_year(company.id, 2026)
        assert len(first) > 0
        assert len(second) == 0

    def test_complete_deadline(self, db, company_with_data):
        company, fy = company_with_data
        deadlines = seed_deadlines_for_year(company.id, 2026)
        result = complete_deadline(deadlines[0].id, completed_by=1, notes='Done')
        assert result.status == 'completed'
        assert result.notes == 'Done'


class TestPayments:
    def test_record_and_list(self, db, company_with_data):
        company, fy = company_with_data
        payment = record_tax_payment(
            company_id=company.id,
            payment_type='vat',
            amount=Decimal('4000'),
            payment_date=date(2026, 5, 12),
            reference='OCR123',
        )
        assert payment.id is not None
        payments = list_tax_payments(company.id, 2026)
        assert len(payments) == 1

    def test_payment_summary(self, db, company_with_data):
        company, fy = company_with_data
        record_tax_payment(company.id, 'vat', Decimal('4000'), date(2026, 5, 12))
        record_tax_payment(company.id, 'employer_tax', Decimal('9426'), date(2026, 5, 12))
        summary = get_tax_payment_summary(company.id, 2026)
        assert summary['vat']['total'] == Decimal('4000')
        assert summary['employer_tax']['total'] == Decimal('9426')
        assert summary['_grand_total'] == Decimal('13426')


class TestEmployerTax:
    def test_calculate_employer_tax(self, db, company_with_data):
        company, fy = company_with_data
        result = calculate_employer_tax_for_period(
            company.id, fy.id, date(2026, 1, 1), date(2026, 3, 31)
        )
        assert result['total_salaries'] == Decimal('30000')
        assert result['total_employer_tax'] == Decimal('9426')
