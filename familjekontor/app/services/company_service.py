"""Company management service."""

from datetime import date
from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account
from app.utils.bas_kontoplan import seed_accounts_for_company


def create_company(name, org_number, company_type, accounting_standard='K2',
                   fiscal_year_start=1, vat_period='quarterly', base_currency='SEK'):
    """Create a new company and seed its chart of accounts + initial fiscal year."""
    company = Company(
        name=name,
        org_number=org_number,
        company_type=company_type,
        accounting_standard=accounting_standard,
        fiscal_year_start=fiscal_year_start,
        vat_period=vat_period,
        base_currency=base_currency,
    )
    db.session.add(company)
    db.session.flush()  # Get the ID

    # Seed BAS accounts
    seed_accounts_for_company(company.id)

    # Create current fiscal year
    today = date.today()
    year = today.year
    fy_start = date(year, fiscal_year_start, 1)
    if fiscal_year_start == 1:
        fy_end = date(year, 12, 31)
    else:
        fy_end = date(year + 1, fiscal_year_start - 1, 28)  # simplified

    fiscal_year = FiscalYear(
        company_id=company.id,
        year=year,
        start_date=fy_start,
        end_date=fy_end,
        status='open',
    )
    db.session.add(fiscal_year)
    db.session.commit()

    # Seed tax deadlines for the current year
    from app.services.tax_service import seed_deadlines_for_year
    seed_deadlines_for_year(company.id, year)

    return company


def get_company_summary(company_id):
    """Get summary stats for a company."""
    from app.models.accounting import Verification
    from app.models.invoice import SupplierInvoice, CustomerInvoice

    company = db.session.get(Company, company_id)
    if not company:
        return None

    active_fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()

    verification_count = 0
    if active_fy:
        verification_count = Verification.query.filter_by(
            company_id=company_id, fiscal_year_id=active_fy.id
        ).count()

    pending_supplier = SupplierInvoice.query.filter_by(
        company_id=company_id, status='pending'
    ).count()

    unpaid_customer = CustomerInvoice.query.filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.in_(['sent', 'overdue'])
    ).count()

    account_count = Account.query.filter_by(company_id=company_id, active=True).count()

    return {
        'company': company,
        'active_fiscal_year': active_fy,
        'verification_count': verification_count,
        'pending_supplier_invoices': pending_supplier,
        'unpaid_customer_invoices': unpaid_customer,
        'account_count': account_count,
    }
