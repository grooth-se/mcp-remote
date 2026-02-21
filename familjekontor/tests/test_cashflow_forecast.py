"""Tests for Phase 10G: Enhanced Cash Flow Forecasting."""

import pytest
from datetime import date
from decimal import Decimal

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice, Customer
from app.models.recurring_invoice import RecurringInvoiceTemplate, RecurringLineItem
from app.models.tax import TaxPayment
from app.services.cashflow_service import get_enhanced_cash_flow_forecast


def _setup_company(db):
    company = Company(name='CF AB', org_number='556700-0001', company_type='AB')
    db.session.add(company)
    db.session.commit()
    fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.commit()
    return company, fy


_ver_counter = [0]

def _create_cash_verification(db, company_id, fy_id, month, amount, desc='Test'):
    """Create a verification with a 19xx cash row + counterpart."""
    cash_acct = Account.query.filter_by(company_id=company_id, account_number='1930').first()
    if not cash_acct:
        cash_acct = Account(company_id=company_id, account_number='1930', name='Bank', account_type='asset')
        db.session.add(cash_acct)
        db.session.flush()
    exp_acct = Account.query.filter_by(company_id=company_id, account_number='5010').first()
    if not exp_acct:
        exp_acct = Account(company_id=company_id, account_number='5010', name='Hyra', account_type='expense')
        db.session.add(exp_acct)
        db.session.flush()

    _ver_counter[0] += 1
    # Determine year from FY
    fy = db.session.get(FiscalYear, fy_id)
    ver_year = fy.year if fy else 2025
    v = Verification(
        company_id=company_id, fiscal_year_id=fy_id,
        verification_date=date(ver_year, month, 15),
        verification_number=_ver_counter[0],
        description=desc,
    )
    db.session.add(v)
    db.session.flush()

    if amount > 0:
        # Cash inflow
        row1 = VerificationRow(verification_id=v.id, account_id=cash_acct.id,
                               debit=Decimal(str(amount)), credit=Decimal('0'))
        row2 = VerificationRow(verification_id=v.id, account_id=exp_acct.id,
                               debit=Decimal('0'), credit=Decimal(str(amount)))
    else:
        # Cash outflow
        amt = abs(amount)
        row1 = VerificationRow(verification_id=v.id, account_id=cash_acct.id,
                               debit=Decimal('0'), credit=Decimal(str(amt)))
        row2 = VerificationRow(verification_id=v.id, account_id=exp_acct.id,
                               debit=Decimal(str(amt)), credit=Decimal('0'))

    db.session.add_all([row1, row2])
    db.session.commit()
    return v


# ---- Service tests ----

class TestEnhancedForecast:
    def test_empty_data_returns_structure(self, db):
        company, fy = _setup_company(db)
        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        assert 'labels' in result
        assert 'actual' in result
        assert 'forecast' in result
        assert 'confidence_upper' in result
        assert 'confidence_lower' in result
        assert 'known_obligations' in result
        assert 'avg_monthly_cf' in result
        assert 'has_seasonal' in result

    def test_empty_data_no_forecast(self, db):
        company, fy = _setup_company(db)
        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        assert all(f is None for f in result['forecast'])
        assert result['avg_monthly_cf'] == 0.0

    def test_with_actual_data(self, db):
        company, fy = _setup_company(db)
        _create_cash_verification(db, company.id, fy.id, 1, -5000)
        _create_cash_verification(db, company.id, fy.id, 2, -6000)
        _create_cash_verification(db, company.id, fy.id, 3, -4000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        assert result['avg_monthly_cf'] != 0.0
        # Should have forecast for months after actual data
        has_forecast = any(f is not None for f in result['forecast'])
        assert has_forecast

    def test_confidence_intervals(self, db):
        company, fy = _setup_company(db)
        _create_cash_verification(db, company.id, fy.id, 1, -5000)
        _create_cash_verification(db, company.id, fy.id, 2, -8000)
        _create_cash_verification(db, company.id, fy.id, 3, -3000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        # Find a forecast month
        for i in range(12):
            if result['forecast'][i] is not None:
                assert result['confidence_upper'][i] is not None
                assert result['confidence_lower'][i] is not None
                assert result['confidence_upper'][i] >= result['forecast'][i]
                assert result['confidence_lower'][i] <= result['forecast'][i]
                break

    def test_no_seasonal_without_prior_year(self, db):
        company, fy = _setup_company(db)
        _create_cash_verification(db, company.id, fy.id, 1, -5000)
        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        assert result['has_seasonal'] is False

    def test_seasonal_with_prior_year(self, db):
        company, fy = _setup_company(db)
        prior_fy = FiscalYear(company_id=company.id, year=2024, start_date=date(2024, 1, 1),
                              end_date=date(2024, 12, 31), status='closed')
        db.session.add(prior_fy)
        db.session.commit()

        # Create prior year data
        _create_cash_verification(db, company.id, prior_fy.id, 1, -3000)
        _create_cash_verification(db, company.id, prior_fy.id, 6, -9000)

        # Create current year data
        _create_cash_verification(db, company.id, fy.id, 1, -4000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        assert result['has_seasonal'] is True

    def test_forecast_months_param(self, db):
        company, fy = _setup_company(db)
        _create_cash_verification(db, company.id, fy.id, 1, -5000)
        _create_cash_verification(db, company.id, fy.id, 2, -6000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id, forecast_months=2)
        # Count non-None forecasts
        forecast_count = sum(1 for f in result['forecast'] if f is not None)
        assert forecast_count <= 2

    def test_twelve_labels(self, db):
        company, fy = _setup_company(db)
        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        assert len(result['labels']) == 12


class TestKnownObligations:
    def test_pending_supplier_invoice(self, db):
        company, fy = _setup_company(db)
        supplier = Supplier(company_id=company.id, name='Lev AB')
        db.session.add(supplier)
        db.session.commit()
        inv = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F001', invoice_date=date(2025, 1, 1),
            due_date=date(2025, 6, 15), total_amount=Decimal('10000'),
            status='pending',
        )
        db.session.add(inv)
        db.session.commit()

        # Create some actual data to trigger forecasting
        _create_cash_verification(db, company.id, fy.id, 1, -5000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        # June obligation should include the -10000
        assert result['known_obligations'][5] == -10000.0

    def test_recurring_invoice_income(self, db):
        company, fy = _setup_company(db)
        customer = Customer(company_id=company.id, name='Kund AB')
        db.session.add(customer)
        db.session.commit()
        tmpl = RecurringInvoiceTemplate(
            company_id=company.id, customer_id=customer.id,
            name='Månadsavgift', interval='monthly',
            start_date=date(2025, 1, 1), next_date=date(2025, 7, 1),
            active=True,
        )
        db.session.add(tmpl)
        db.session.flush()
        li = RecurringLineItem(
            template_id=tmpl.id, line_number=1, description='Avgift',
            quantity=1, unit_price=Decimal('5000'),
            vat_rate=Decimal('25'),
        )
        db.session.add(li)
        db.session.commit()

        _create_cash_verification(db, company.id, fy.id, 1, -3000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        # July should have positive obligation from recurring invoice
        assert result['known_obligations'][6] == 5000.0

    def test_tax_payment_history(self, db):
        company, fy = _setup_company(db)
        # Prior year tax payment in March
        tp = TaxPayment(
            company_id=company.id, payment_type='vat',
            amount=Decimal('8000'), payment_date=date(2024, 3, 12),
        )
        db.session.add(tp)
        db.session.commit()

        _create_cash_verification(db, company.id, fy.id, 1, -5000)

        result = get_enhanced_cash_flow_forecast(company.id, fy.id)
        # March obligation should include -8000 from historical tax
        assert result['known_obligations'][2] == -8000.0


# ---- Route tests ----

class TestForecastRoute:
    def test_forecast_no_company(self, logged_in_client, db):
        resp = logged_in_client.get('/cashflow/forecast', follow_redirects=True)
        assert resp.status_code == 200

    def test_forecast_renders(self, logged_in_client, db):
        company = Company(name='CF AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/cashflow/forecast')
        assert resp.status_code == 200
        assert 'Kassaflödesprognos' in resp.get_data(as_text=True)

    def test_forecast_with_fy_param(self, logged_in_client, db):
        company = Company(name='CF AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/cashflow/forecast?fiscal_year_id={fy.id}')
        assert resp.status_code == 200

    def test_existing_forecast_route_unchanged(self, logged_in_client, db):
        """Verify the original /cashflow/api/monthly still works."""
        company = Company(name='CF AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/cashflow/api/monthly?fiscal_year_id={fy.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'monthly' in data
        assert 'forecast' in data
