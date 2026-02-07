"""Tests for database models."""

from datetime import date
from app.models.user import User
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow


def test_user_password(db):
    user = User(username='test', email='test@test.com')
    user.set_password('secret')
    assert user.check_password('secret')
    assert not user.check_password('wrong')


def test_user_roles(db):
    admin = User(username='admin', email='a@t.com', role='admin')
    user = User(username='user', email='u@t.com', role='user')
    readonly = User(username='ro', email='r@t.com', role='readonly')
    assert admin.is_admin
    assert not user.is_admin
    assert readonly.is_readonly


def test_company_creation(db):
    company = Company(name='Test AB', org_number='5566778899', company_type='AB')
    db.session.add(company)
    db.session.commit()
    assert company.id is not None
    assert company.active is True


def test_fiscal_year(db):
    company = Company(name='Test AB', org_number='5566778899', company_type='AB')
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(company_id=company.id, year=2025,
                    start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add(fy)
    db.session.commit()
    assert fy.status == 'open'


def test_verification_balance(db):
    company = Company(name='Test AB', org_number='5566778899', company_type='AB')
    db.session.add(company)
    db.session.flush()

    fy = FiscalYear(company_id=company.id, year=2025,
                    start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add(fy)
    db.session.flush()

    acc1 = Account(company_id=company.id, account_number='1930', name='Bank', account_type='asset')
    acc2 = Account(company_id=company.id, account_number='3000', name='Försäljning', account_type='revenue')
    db.session.add_all([acc1, acc2])
    db.session.flush()

    ver = Verification(company_id=company.id, fiscal_year_id=fy.id,
                       verification_number=1, verification_date=date(2025, 1, 15),
                       description='Test')
    db.session.add(ver)
    db.session.flush()

    row1 = VerificationRow(verification_id=ver.id, account_id=acc1.id, debit=1000, credit=0)
    row2 = VerificationRow(verification_id=ver.id, account_id=acc2.id, debit=0, credit=1000)
    db.session.add_all([row1, row2])
    db.session.commit()

    assert ver.is_balanced
    assert ver.total_debit == 1000
    assert ver.total_credit == 1000
