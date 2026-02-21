"""Tests for Phase 10E: Anomaly Detection."""

import pytest
from datetime import date, datetime
from decimal import Decimal

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice
from app.services.anomaly_service import (
    detect_anomalies,
    detect_amount_outliers,
    detect_duplicate_payments,
    detect_weekend_bookings,
    detect_round_number_bias,
    detect_missing_sequences,
)


def _setup_company(db):
    company = Company(name='Anomaly AB', org_number='556700-0001', company_type='AB')
    db.session.add(company)
    db.session.commit()
    fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.commit()
    return company, fy


def _create_account(db, company_id, number, name):
    acct = Account(company_id=company_id, account_number=number, name=name, account_type='expense')
    db.session.add(acct)
    db.session.commit()
    return acct


def _create_verification_with_row(db, company_id, fy_id, acct_id, debit, credit,
                                   ver_date=None, ver_number=None, description='Test'):
    v = Verification(
        company_id=company_id, fiscal_year_id=fy_id,
        verification_date=ver_date or date(2025, 3, 15),
        verification_number=ver_number,
        description=description,
    )
    db.session.add(v)
    db.session.flush()
    row = VerificationRow(
        verification_id=v.id, account_id=acct_id,
        debit=Decimal(str(debit)), credit=Decimal(str(credit)),
    )
    db.session.add(row)
    db.session.commit()
    return v


# ---- detect_anomalies integration ----

class TestDetectAnomalies:
    def test_returns_all_categories(self, db):
        company, fy = _setup_company(db)
        result = detect_anomalies(company.id, fy.id)
        assert 'amount_outliers' in result
        assert 'duplicate_payments' in result
        assert 'weekend_bookings' in result
        assert 'round_number_bias' in result
        assert 'missing_sequences' in result
        assert 'total_count' in result

    def test_empty_data_returns_zero_count(self, db):
        company, fy = _setup_company(db)
        result = detect_anomalies(company.id, fy.id)
        assert result['total_count'] == 0

    def test_total_count_sums_all(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # Create a weekend booking (Saturday)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                       ver_date=date(2025, 3, 15), ver_number=1)  # Saturday
        result = detect_anomalies(company.id, fy.id)
        assert result['total_count'] >= 1


# ---- Amount Outliers ----

class TestAmountOutliers:
    def test_no_data(self, db):
        company, fy = _setup_company(db)
        assert detect_amount_outliers(company.id, fy.id) == []

    def test_no_outlier_with_uniform_amounts(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        for i in range(5):
            _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                           ver_number=i + 1)
        outliers = detect_amount_outliers(company.id, fy.id)
        assert len(outliers) == 0

    def test_detects_large_outlier(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # 10 normal amounts + 1 very large (need enough to make stddev meaningful)
        for i in range(10):
            _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                           ver_number=i + 1)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 500000, 0,
                                       ver_number=11)
        outliers = detect_amount_outliers(company.id, fy.id)
        assert len(outliers) >= 1
        amounts = [o['amount'] for o in outliers]
        assert 500000.0 in amounts

    def test_outlier_has_all_fields(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        for i in range(10):
            _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                           ver_number=i + 1)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 500000, 0,
                                       ver_number=11)
        outliers = detect_amount_outliers(company.id, fy.id)
        o = outliers[0]
        assert 'verification_id' in o
        assert 'account_number' in o
        assert 'mean' in o
        assert 'stddev' in o
        assert 'cutoff' in o

    def test_too_few_rows_skipped(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0, ver_number=1)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 100000, 0, ver_number=2)
        # Only 2 rows in prefix 50 — below threshold of 3
        assert detect_amount_outliers(company.id, fy.id) == []


# ---- Duplicate Payments ----

class TestDuplicatePayments:
    def test_no_invoices(self, db):
        company, fy = _setup_company(db)
        assert detect_duplicate_payments(company.id) == []

    def test_detects_duplicate(self, db):
        company, fy = _setup_company(db)
        supplier = Supplier(company_id=company.id, name='Lev AB')
        db.session.add(supplier)
        db.session.commit()
        inv1 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F001', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 3, 10),
        )
        inv2 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F002', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 3, 12),
        )
        db.session.add_all([inv1, inv2])
        db.session.commit()
        dupes = detect_duplicate_payments(company.id)
        assert len(dupes) == 1
        assert dupes[0]['amount'] == 5000.0
        assert dupes[0]['days_apart'] <= 3

    def test_no_duplicate_far_apart(self, db):
        company, fy = _setup_company(db)
        supplier = Supplier(company_id=company.id, name='Lev AB')
        db.session.add(supplier)
        db.session.commit()
        inv1 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F001', invoice_date=date(2025, 1, 1),
            due_date=date(2025, 2, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 1, 15),
        )
        inv2 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F002', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 3, 15),
        )
        db.session.add_all([inv1, inv2])
        db.session.commit()
        dupes = detect_duplicate_payments(company.id)
        assert len(dupes) == 0

    def test_different_amounts_no_dup(self, db):
        company, fy = _setup_company(db)
        supplier = Supplier(company_id=company.id, name='Lev AB')
        db.session.add(supplier)
        db.session.commit()
        inv1 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F001', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 3, 10),
        )
        inv2 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F002', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('6000'),
            status='paid', paid_at=datetime(2025, 3, 11),
        )
        db.session.add_all([inv1, inv2])
        db.session.commit()
        dupes = detect_duplicate_payments(company.id)
        assert len(dupes) == 0

    def test_duplicate_has_supplier_name(self, db):
        company, fy = _setup_company(db)
        supplier = Supplier(company_id=company.id, name='Leverantören AB')
        db.session.add(supplier)
        db.session.commit()
        inv1 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F001', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 3, 10),
        )
        inv2 = SupplierInvoice(
            company_id=company.id, supplier_id=supplier.id,
            invoice_number='F002', invoice_date=date(2025, 3, 1),
            due_date=date(2025, 4, 1), total_amount=Decimal('5000'),
            status='paid', paid_at=datetime(2025, 3, 11),
        )
        db.session.add_all([inv1, inv2])
        db.session.commit()
        dupes = detect_duplicate_payments(company.id)
        assert dupes[0]['supplier_name'] == 'Leverantören AB'


# ---- Weekend Bookings ----

class TestWeekendBookings:
    def test_no_weekend(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # 2025-03-17 is Monday
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                       ver_date=date(2025, 3, 17), ver_number=1)
        assert detect_weekend_bookings(company.id, fy.id) == []

    def test_saturday(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # 2025-03-15 is Saturday
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                       ver_date=date(2025, 3, 15), ver_number=1)
        weekends = detect_weekend_bookings(company.id, fy.id)
        assert len(weekends) == 1
        assert weekends[0]['day_name'] == 'Lördag'

    def test_sunday(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # 2025-03-16 is Sunday
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                       ver_date=date(2025, 3, 16), ver_number=1)
        weekends = detect_weekend_bookings(company.id, fy.id)
        assert len(weekends) == 1
        assert weekends[0]['day_name'] == 'Söndag'

    def test_weekend_has_description(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                       ver_date=date(2025, 3, 15), ver_number=1,
                                       description='Helgbokning')
        weekends = detect_weekend_bookings(company.id, fy.id)
        assert weekends[0]['description'] == 'Helgbokning'

    def test_weekend_has_verification_number(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                       ver_date=date(2025, 3, 15), ver_number=42)
        weekends = detect_weekend_bookings(company.id, fy.id)
        assert weekends[0]['verification_number'] == 42


# ---- Round Number Bias ----

class TestRoundNumberBias:
    def test_no_data(self, db):
        company, fy = _setup_company(db)
        assert detect_round_number_bias(company.id, fy.id) == []

    def test_no_bias_with_varied_amounts(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        for i, amt in enumerate([1234, 5678, 9012, 3456], 1):
            _create_verification_with_row(db, company.id, fy.id, acct.id, amt, 0,
                                           ver_number=i)
        result = detect_round_number_bias(company.id, fy.id)
        assert len(result) == 0

    def test_detects_round_bias(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # All amounts divisible by 1000 — 100% round
        for i, amt in enumerate([1000, 2000, 3000, 4000, 5000], 1):
            _create_verification_with_row(db, company.id, fy.id, acct.id, amt, 0,
                                           ver_number=i)
        result = detect_round_number_bias(company.id, fy.id)
        assert len(result) == 1
        assert result[0]['percentage'] == 100.0

    def test_threshold_customizable(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # 2 of 4 = 50%
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0, ver_number=1)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 2000, 0, ver_number=2)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1234, 0, ver_number=3)
        _create_verification_with_row(db, company.id, fy.id, acct.id, 5678, 0, ver_number=4)
        # Default threshold 30% → should detect (50% > 30%)
        assert len(detect_round_number_bias(company.id, fy.id)) == 1
        # Higher threshold 60% → should not detect (50% < 60%)
        assert len(detect_round_number_bias(company.id, fy.id, threshold_pct=60)) == 0

    def test_small_amounts_excluded(self, db):
        """Amounts < 1000 are not counted as round."""
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        # All amounts are < 1000 but "round"
        for i, amt in enumerate([100, 200, 300, 400], 1):
            _create_verification_with_row(db, company.id, fy.id, acct.id, amt, 0,
                                           ver_number=i)
        result = detect_round_number_bias(company.id, fy.id)
        assert len(result) == 0


# ---- Missing Sequences ----

class TestMissingSequences:
    def test_no_verifications(self, db):
        company, fy = _setup_company(db)
        assert detect_missing_sequences(company.id, fy.id) == []

    def test_continuous_sequence(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        for i in range(1, 6):
            _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                           ver_number=i)
        assert detect_missing_sequences(company.id, fy.id) == []

    def test_detects_gap(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        for i in [1, 2, 5]:
            _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0,
                                           ver_number=i)
        missing = detect_missing_sequences(company.id, fy.id)
        missing_nums = [m['missing_number'] for m in missing]
        assert 3 in missing_nums
        assert 4 in missing_nums
        assert len(missing) == 2

    def test_single_verification_no_gap(self, db):
        company, fy = _setup_company(db)
        acct = _create_account(db, company.id, '5010', 'Lokalhyra')
        _create_verification_with_row(db, company.id, fy.id, acct.id, 1000, 0, ver_number=1)
        assert detect_missing_sequences(company.id, fy.id) == []


# ---- Route tests ----

class TestAnomaliesRoute:
    def test_anomalies_no_company(self, logged_in_client, db):
        resp = logged_in_client.get('/anomalies', follow_redirects=True)
        assert resp.status_code == 200
        assert 'Välj ett företag' in resp.get_data(as_text=True)

    def test_anomalies_page_renders(self, logged_in_client, db):
        company = Company(name='Test AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/anomalies')
        assert resp.status_code == 200
        assert 'Anomalidetektering' in resp.get_data(as_text=True)

    def test_anomalies_shows_counts(self, logged_in_client, db):
        company = Company(name='Test AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        fy = FiscalYear(company_id=company.id, year=2025, start_date=date(2025, 1, 1),
                        end_date=date(2025, 12, 31), status='open')
        db.session.add(fy)
        db.session.commit()
        acct = Account(company_id=company.id, account_number='5010', name='Lokalhyra', account_type='expense')
        db.session.add(acct)
        db.session.commit()
        # Saturday booking
        v = Verification(company_id=company.id, fiscal_year_id=fy.id,
                         verification_date=date(2025, 3, 15), verification_number=1,
                         description='Helgbokning')
        db.session.add(v)
        db.session.flush()
        row = VerificationRow(verification_id=v.id, account_id=acct.id,
                              debit=Decimal('1000'), credit=Decimal('0'))
        db.session.add(row)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/anomalies')
        html = resp.get_data(as_text=True)
        assert 'Helgbokningar' in html
        assert 'Lördag' in html

    def test_anomalies_no_fy(self, logged_in_client, db):
        company = Company(name='Test AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/anomalies')
        assert resp.status_code == 200
        assert 'Ingen data' in resp.get_data(as_text=True)
