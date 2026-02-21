"""Real estate service: CRUD, property tax calculation, rental income tracking."""

from decimal import Decimal

from app.extensions import db
from app.models.real_estate import RealEstate
from app.models.accounting import Account, Verification, VerificationRow, FiscalYear


def get_real_estates(company_id, active_only=True):
    """Get all real estate properties for a company."""
    query = RealEstate.query.filter_by(company_id=company_id)
    if active_only:
        query = query.filter_by(active=True)
    return query.order_by(RealEstate.property_name).all()


def create_real_estate(company_id, **kwargs):
    """Create a new real estate record."""
    prop = RealEstate(company_id=company_id, **kwargs)
    db.session.add(prop)
    db.session.commit()
    return prop


def update_real_estate(prop_id, **kwargs):
    """Update a real estate record."""
    prop = db.session.get(RealEstate, prop_id)
    if not prop:
        return None
    for key, val in kwargs.items():
        if hasattr(prop, key):
            setattr(prop, key, val)
    db.session.commit()
    return prop


def delete_real_estate(prop_id):
    """Soft-delete a real estate record (set active=False)."""
    prop = db.session.get(RealEstate, prop_id)
    if not prop:
        return False
    prop.active = False
    db.session.commit()
    return True


def calculate_property_tax(prop):
    """Calculate annual property tax (kommunal fastighetsavgift).

    Returns Decimal amount.
    """
    if not prop or not prop.taxeringsvarde:
        return Decimal('0')
    return (Decimal(str(prop.taxeringsvarde)) * Decimal(str(prop.property_tax_rate))).quantize(Decimal('0.01'))


def get_rental_income_ytd(company_id, fiscal_year_id, rent_account='3910'):
    """Get year-to-date rental income from VerificationRow on the rent account.

    Returns Decimal total (credit - debit).
    """
    result = (db.session.query(
        db.func.coalesce(db.func.sum(VerificationRow.credit), 0).label('total_credit'),
        db.func.coalesce(db.func.sum(VerificationRow.debit), 0).label('total_debit'),
    )
    .join(Verification, Verification.id == VerificationRow.verification_id)
    .join(Account, Account.id == VerificationRow.account_id)
    .filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
        Account.account_number == rent_account,
    )
    .first())

    if result:
        credit = Decimal(str(result.total_credit or 0))
        debit = Decimal(str(result.total_debit or 0))
        return credit - debit
    return Decimal('0')


def get_real_estate_summary(company_id, fiscal_year_id=None):
    """Get summary of all properties with calculated data.

    Returns list of dicts with property info, tax, and rental income.
    """
    properties = get_real_estates(company_id, active_only=True)
    summaries = []

    for prop in properties:
        tax = calculate_property_tax(prop)
        rental_income = Decimal('0')
        if fiscal_year_id:
            rental_income = get_rental_income_ytd(
                company_id, fiscal_year_id, prop.rent_account or '3910'
            )

        summaries.append({
            'id': prop.id,
            'property_name': prop.property_name,
            'fastighetsbeteckning': prop.fastighetsbeteckning,
            'city': prop.city,
            'taxeringsvarde': float(prop.taxeringsvarde or 0),
            'property_tax': float(tax),
            'monthly_rent_target': float(prop.monthly_rent_target or 0),
            'rental_income_ytd': float(rental_income),
            'has_asset': prop.asset_id is not None,
        })

    return summaries
