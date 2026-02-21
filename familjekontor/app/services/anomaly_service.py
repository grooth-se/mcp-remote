"""Anomaly detection service: rule-based detection of unusual transactions."""

import statistics
from datetime import timedelta
from decimal import Decimal
from collections import defaultdict

from app.extensions import db
from app.models.accounting import Verification, VerificationRow, Account, FiscalYear
from app.models.invoice import SupplierInvoice


def detect_anomalies(company_id, fiscal_year_id):
    """Run all anomaly detection checks.

    Returns dict with categories, each containing a list of anomaly dicts.
    """
    results = {
        'amount_outliers': detect_amount_outliers(company_id, fiscal_year_id),
        'duplicate_payments': detect_duplicate_payments(company_id),
        'weekend_bookings': detect_weekend_bookings(company_id, fiscal_year_id),
        'round_number_bias': detect_round_number_bias(company_id, fiscal_year_id),
        'missing_sequences': detect_missing_sequences(company_id, fiscal_year_id),
    }

    results['total_count'] = sum(len(v) for v in results.values())
    return results


def detect_amount_outliers(company_id, fiscal_year_id, threshold=3.0):
    """Detect transaction amounts > mean + threshold*stddev per account prefix.

    Returns list of dicts with verification_id, account, amount, mean, stddev.
    """
    rows = (db.session.query(
        VerificationRow.verification_id,
        Account.account_number,
        Account.name,
        VerificationRow.debit,
        VerificationRow.credit,
    )
    .join(Account, Account.id == VerificationRow.account_id)
    .join(Verification, Verification.id == VerificationRow.verification_id)
    .filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
    )
    .all())

    # Group amounts by account prefix (2 digits)
    prefix_amounts = defaultdict(list)
    prefix_rows = defaultdict(list)

    for ver_id, acct_num, acct_name, debit, credit in rows:
        prefix = acct_num[:2]
        amount = float(debit or 0) + float(credit or 0)
        if amount > 0:
            prefix_amounts[prefix].append(amount)
            prefix_rows[prefix].append({
                'verification_id': ver_id,
                'account_number': acct_num,
                'account_name': acct_name,
                'amount': amount,
            })

    outliers = []
    for prefix, amounts in prefix_amounts.items():
        if len(amounts) < 3:
            continue

        mean = statistics.mean(amounts)
        try:
            stddev = statistics.stdev(amounts)
        except statistics.StatisticsError:
            continue

        if stddev == 0:
            continue

        cutoff = mean + threshold * stddev
        for row_data in prefix_rows[prefix]:
            if row_data['amount'] > cutoff:
                outliers.append({
                    **row_data,
                    'mean': round(mean, 2),
                    'stddev': round(stddev, 2),
                    'cutoff': round(cutoff, 2),
                })

    return outliers


def detect_duplicate_payments(company_id, window_days=3):
    """Detect potential duplicate supplier invoice payments.

    Groups by (supplier_id, total_amount) within a time window.
    Returns list of duplicate groups.
    """
    invoices = (SupplierInvoice.query
                .filter_by(company_id=company_id, status='paid')
                .order_by(SupplierInvoice.paid_at)
                .all())

    groups = defaultdict(list)
    for inv in invoices:
        if inv.total_amount and inv.paid_at:
            key = (inv.supplier_id, float(inv.total_amount))
            groups[key].append(inv)

    duplicates = []
    for key, inv_list in groups.items():
        if len(inv_list) < 2:
            continue

        for i in range(len(inv_list)):
            for j in range(i + 1, len(inv_list)):
                delta = abs((inv_list[j].paid_at - inv_list[i].paid_at).days)
                if delta <= window_days:
                    duplicates.append({
                        'supplier_id': key[0],
                        'supplier_name': inv_list[i].supplier.name if inv_list[i].supplier else '',
                        'amount': key[1],
                        'invoice_a': inv_list[i].invoice_number,
                        'invoice_b': inv_list[j].invoice_number,
                        'days_apart': delta,
                    })

    return duplicates


def detect_weekend_bookings(company_id, fiscal_year_id):
    """Detect verifications dated on Saturday or Sunday.

    Returns list of dicts with verification_id, date, day_name.
    """
    verifications = (Verification.query
                     .filter_by(company_id=company_id, fiscal_year_id=fiscal_year_id)
                     .all())

    weekends = []
    for v in verifications:
        if v.verification_date and v.verification_date.weekday() >= 5:
            day_name = 'Lördag' if v.verification_date.weekday() == 5 else 'Söndag'
            weekends.append({
                'verification_id': v.id,
                'verification_number': v.verification_number,
                'date': str(v.verification_date),
                'day_name': day_name,
                'description': v.description,
            })

    return weekends


def detect_round_number_bias(company_id, fiscal_year_id, threshold_pct=30):
    """Flag if >threshold_pct of transaction amounts are divisible by 1000.

    Returns list with a single item if bias detected, empty otherwise.
    """
    rows = (db.session.query(VerificationRow.debit, VerificationRow.credit)
            .join(Verification, Verification.id == VerificationRow.verification_id)
            .filter(
                Verification.company_id == company_id,
                Verification.fiscal_year_id == fiscal_year_id,
            )
            .all())

    amounts = []
    for debit, credit in rows:
        d = float(debit or 0)
        c = float(credit or 0)
        if d > 0:
            amounts.append(d)
        if c > 0:
            amounts.append(c)

    if not amounts:
        return []

    round_count = sum(1 for a in amounts if a >= 1000 and a % 1000 == 0)
    pct = (round_count / len(amounts)) * 100

    if pct > threshold_pct:
        return [{
            'round_count': round_count,
            'total_count': len(amounts),
            'percentage': round(pct, 1),
            'threshold': threshold_pct,
        }]

    return []


def detect_missing_sequences(company_id, fiscal_year_id):
    """Detect gaps in verification_number series.

    Returns list of missing numbers.
    """
    numbers = (db.session.query(Verification.verification_number)
               .filter_by(company_id=company_id, fiscal_year_id=fiscal_year_id)
               .order_by(Verification.verification_number)
               .all())

    if not numbers:
        return []

    nums = sorted([n[0] for n in numbers if n[0] is not None])
    if not nums:
        return []

    missing = []
    expected = nums[0]
    for n in nums:
        while expected < n:
            missing.append({
                'missing_number': expected,
            })
            expected += 1
        expected = n + 1

    return missing
