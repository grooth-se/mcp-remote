"""Tax & compliance service - VAT reporting, deadlines, and tax payments."""

from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.tax import VATReport, Deadline, TaxPayment
from app.models.accounting import Account, Verification, VerificationRow, FiscalYear
from app.models.company import Company


# ---------------------------------------------------------------------------
# VAT
# ---------------------------------------------------------------------------

def calculate_vat_for_period(company_id, fiscal_year_id, period_start, period_end):
    """Query VAT accounts 2610-2650 and return a breakdown dict."""
    vat_accounts = {
        '2610': 'output_vat_25',
        '2620': 'output_vat_12',
        '2630': 'output_vat_6',
    }
    input_accounts = ['2640', '2641', '2645']

    result = {
        'output_vat_25': Decimal('0'),
        'output_vat_12': Decimal('0'),
        'output_vat_6': Decimal('0'),
        'input_vat': Decimal('0'),
    }

    for acct_num, field in vat_accounts.items():
        account = Account.query.filter_by(
            company_id=company_id, account_number=acct_num
        ).first()
        if not account:
            continue
        row = db.session.query(
            func.coalesce(func.sum(VerificationRow.credit), 0) -
            func.coalesce(func.sum(VerificationRow.debit), 0)
        ).join(Verification).filter(
            VerificationRow.account_id == account.id,
            Verification.fiscal_year_id == fiscal_year_id,
            Verification.verification_date >= period_start,
            Verification.verification_date <= period_end,
        ).scalar()
        result[field] = Decimal(str(row)) if row else Decimal('0')

    # Input VAT (debit side)
    for acct_num in input_accounts:
        account = Account.query.filter_by(
            company_id=company_id, account_number=acct_num
        ).first()
        if not account:
            continue
        row = db.session.query(
            func.coalesce(func.sum(VerificationRow.debit), 0) -
            func.coalesce(func.sum(VerificationRow.credit), 0)
        ).join(Verification).filter(
            VerificationRow.account_id == account.id,
            Verification.fiscal_year_id == fiscal_year_id,
            Verification.verification_date >= period_start,
            Verification.verification_date <= period_end,
        ).scalar()
        result['input_vat'] += Decimal(str(row)) if row else Decimal('0')

    result['vat_to_pay'] = (
        result['output_vat_25'] + result['output_vat_12'] + result['output_vat_6']
        - result['input_vat']
    )
    return result


def get_vat_periods_for_year(company_id, year):
    """Return period list based on company.vat_period setting."""
    company = db.session.get(Company, company_id)
    if not company:
        return []

    periods = []
    if company.vat_period == 'monthly':
        import calendar
        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            periods.append({
                'label': f'{year}-{month:02d}',
                'period_type': 'monthly',
                'period_month': month,
                'period_quarter': None,
                'period_start': date(year, month, 1),
                'period_end': date(year, month, last_day),
            })
    elif company.vat_period == 'quarterly':
        quarter_months = [(1, 3), (4, 6), (7, 9), (10, 12)]
        for q, (start_m, end_m) in enumerate(quarter_months, 1):
            import calendar
            last_day = calendar.monthrange(year, end_m)[1]
            periods.append({
                'label': f'Q{q} {year}',
                'period_type': 'quarterly',
                'period_month': None,
                'period_quarter': q,
                'period_start': date(year, start_m, 1),
                'period_end': date(year, end_m, last_day),
            })
    else:  # annual
        periods.append({
            'label': str(year),
            'period_type': 'annual',
            'period_month': None,
            'period_quarter': None,
            'period_start': date(year, 1, 1),
            'period_end': date(year, 12, 31),
        })

    return periods


def create_vat_report(company_id, fiscal_year_id, period_info, created_by=None):
    """Calculate VAT for the given period and persist as VATReport."""
    vat = calculate_vat_for_period(
        company_id, fiscal_year_id,
        period_info['period_start'], period_info['period_end']
    )

    report = VATReport(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        period_type=period_info['period_type'],
        period_year=period_info['period_start'].year,
        period_month=period_info.get('period_month'),
        period_quarter=period_info.get('period_quarter'),
        period_start=period_info['period_start'],
        period_end=period_info['period_end'],
        output_vat_25=vat['output_vat_25'],
        output_vat_12=vat['output_vat_12'],
        output_vat_6=vat['output_vat_6'],
        input_vat=vat['input_vat'],
        vat_to_pay=vat['vat_to_pay'],
        status='draft',
        created_by=created_by,
    )
    db.session.add(report)
    db.session.commit()
    return report


def finalize_vat_report(report_id):
    """Lock a VAT report as filed."""
    report = db.session.get(VATReport, report_id)
    if not report:
        return None
    report.status = 'filed'
    db.session.commit()
    return report


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------

MONTH_NAMES_SV = [
    '', 'januari', 'februari', 'mars', 'april', 'maj', 'juni',
    'juli', 'augusti', 'september', 'oktober', 'november', 'december',
]


def seed_deadlines_for_year(company_id, year):
    """Auto-generate all Swedish tax deadlines for a company and year.

    Idempotent - skips if auto-generated deadlines already exist for the year.
    """
    existing = Deadline.query.filter_by(
        company_id=company_id, auto_generated=True
    ).filter(
        db.extract('year', Deadline.due_date) == year
    ).count()
    if existing > 0:
        return []

    company = db.session.get(Company, company_id)
    if not company:
        return []

    deadlines = []

    # --- VAT deadlines ---
    if company.vat_period == 'monthly':
        for month in range(1, 13):
            # VAT due on the 12th of the following month
            due_month = month + 1 if month < 12 else 1
            due_year = year if month < 12 else year + 1
            due = date(due_year, due_month, 12)
            reminder = date(due_year, due_month, 5)
            deadlines.append(Deadline(
                company_id=company_id,
                deadline_type='vat',
                description=f'Momsdeklaration {MONTH_NAMES_SV[month]} {year}',
                due_date=due,
                reminder_date=reminder,
                period_label=f'{year}-{month:02d}',
                auto_generated=True,
            ))
    elif company.vat_period == 'quarterly':
        quarter_due = {
            1: (year, 5, 12),   # Q1 due May 12
            2: (year, 8, 12),   # Q2 due Aug 12
            3: (year, 11, 12),  # Q3 due Nov 12
            4: (year + 1, 2, 12),  # Q4 due Feb 12 next year
        }
        for q, (dy, dm, dd) in quarter_due.items():
            due = date(dy, dm, dd)
            reminder = date(dy, dm, 5)
            deadlines.append(Deadline(
                company_id=company_id,
                deadline_type='vat',
                description=f'Momsdeklaration Q{q} {year}',
                due_date=due,
                reminder_date=reminder,
                period_label=f'Q{q} {year}',
                auto_generated=True,
            ))
    else:  # annual
        deadlines.append(Deadline(
            company_id=company_id,
            deadline_type='vat',
            description=f'Momsdeklaration {year} (helår)',
            due_date=date(year + 1, 2, 12),
            reminder_date=date(year + 1, 2, 5),
            period_label=str(year),
            auto_generated=True,
        ))

    # --- Employer tax (monthly, 12th of following month) ---
    for month in range(1, 13):
        due_month = month + 1 if month < 12 else 1
        due_year = year if month < 12 else year + 1
        due = date(due_year, due_month, 12)
        reminder = date(due_year, due_month, 5)
        deadlines.append(Deadline(
            company_id=company_id,
            deadline_type='employer_tax',
            description=f'Arbetsgivardeklaration {MONTH_NAMES_SV[month]} {year}',
            due_date=due,
            reminder_date=reminder,
            period_label=f'{year}-{month:02d}',
            auto_generated=True,
        ))

    # --- Company-type specific ---
    if company.company_type == 'AB':
        # Corporate tax: quarterly preliminary payments (12 Mar, 12 Jun, 12 Sep, 12 Dec)
        for q, m in enumerate([3, 6, 9, 12], 1):
            deadlines.append(Deadline(
                company_id=company_id,
                deadline_type='corporate_tax',
                description=f'Preliminär skatt Q{q} {year}',
                due_date=date(year, m, 12),
                reminder_date=date(year, m, 5),
                period_label=f'Q{q} {year}',
                auto_generated=True,
            ))
        # Annual report: 7 months after fiscal year end
        fy_end_month = (company.fiscal_year_start - 1) if company.fiscal_year_start > 1 else 12
        fy_end_year = year if company.fiscal_year_start == 1 else year
        ar_month = fy_end_month + 7
        ar_year = fy_end_year
        if ar_month > 12:
            ar_month -= 12
            ar_year += 1
        deadlines.append(Deadline(
            company_id=company_id,
            deadline_type='annual_report',
            description=f'Årsredovisning {year}',
            due_date=date(ar_year, ar_month, 1),
            reminder_date=date(ar_year, ar_month - 1 if ar_month > 1 else 12,
                               15 if ar_month > 1 else 15),
            period_label=str(year),
            auto_generated=True,
        ))
        # Tax return: July 1
        deadlines.append(Deadline(
            company_id=company_id,
            deadline_type='tax_return',
            description=f'Inkomstdeklaration AB {year}',
            due_date=date(year + 1, 7, 1),
            reminder_date=date(year + 1, 6, 15),
            period_label=str(year),
            auto_generated=True,
        ))
    elif company.company_type == 'HB':
        # Annual report: 6 months after fiscal year end
        fy_end_month = (company.fiscal_year_start - 1) if company.fiscal_year_start > 1 else 12
        fy_end_year = year
        ar_month = fy_end_month + 6
        ar_year = fy_end_year
        if ar_month > 12:
            ar_month -= 12
            ar_year += 1
        deadlines.append(Deadline(
            company_id=company_id,
            deadline_type='annual_report',
            description=f'Årsredovisning HB {year}',
            due_date=date(ar_year, ar_month, 1),
            reminder_date=date(ar_year, ar_month - 1 if ar_month > 1 else 12,
                               15 if ar_month > 1 else 15),
            period_label=str(year),
            auto_generated=True,
        ))
        # Tax return: May 2
        deadlines.append(Deadline(
            company_id=company_id,
            deadline_type='tax_return',
            description=f'Inkomstdeklaration HB {year}',
            due_date=date(year + 1, 5, 2),
            reminder_date=date(year + 1, 4, 15),
            period_label=str(year),
            auto_generated=True,
        ))

    db.session.add_all(deadlines)
    db.session.commit()
    return deadlines


def get_upcoming_deadlines(company_id, days_ahead=30):
    """Get pending deadlines within the next N days."""
    from datetime import timedelta
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    return Deadline.query.filter(
        Deadline.company_id == company_id,
        Deadline.status == 'pending',
        Deadline.due_date >= today,
        Deadline.due_date <= cutoff,
    ).order_by(Deadline.due_date).all()


def get_overdue_deadlines(company_id):
    """Get overdue deadlines and update their status."""
    today = date.today()
    overdue = Deadline.query.filter(
        Deadline.company_id == company_id,
        Deadline.status == 'pending',
        Deadline.due_date < today,
    ).all()
    for d in overdue:
        d.status = 'overdue'
    if overdue:
        db.session.commit()
    return overdue


def complete_deadline(deadline_id, completed_by, notes=None):
    """Mark a deadline as completed."""
    deadline = db.session.get(Deadline, deadline_id)
    if not deadline:
        return None
    deadline.status = 'completed'
    deadline.completed_at = datetime.now(timezone.utc)
    deadline.completed_by = completed_by
    if notes:
        deadline.notes = notes
    db.session.commit()
    return deadline


# ---------------------------------------------------------------------------
# Tax Payments
# ---------------------------------------------------------------------------

def record_tax_payment(company_id, payment_type, amount, payment_date,
                       reference=None, deadline_id=None, verification_id=None,
                       notes=None, created_by=None):
    """Persist a tax payment record."""
    payment = TaxPayment(
        company_id=company_id,
        payment_type=payment_type,
        amount=amount,
        payment_date=payment_date,
        reference=reference,
        deadline_id=deadline_id,
        verification_id=verification_id,
        notes=notes,
        created_by=created_by,
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def list_tax_payments(company_id, year=None):
    """List tax payments for a company, optionally filtered by year."""
    query = TaxPayment.query.filter_by(company_id=company_id)
    if year:
        query = query.filter(db.extract('year', TaxPayment.payment_date) == year)
    return query.order_by(TaxPayment.payment_date.desc()).all()


def get_tax_payment_summary(company_id, year):
    """Get totals by payment type for a year."""
    rows = db.session.query(
        TaxPayment.payment_type,
        func.sum(TaxPayment.amount).label('total'),
        func.count(TaxPayment.id).label('count'),
    ).filter(
        TaxPayment.company_id == company_id,
        db.extract('year', TaxPayment.payment_date) == year,
    ).group_by(TaxPayment.payment_type).all()

    summary = {}
    grand_total = Decimal('0')
    for row in rows:
        total = Decimal(str(row.total))
        summary[row.payment_type] = {
            'total': total,
            'count': row.count,
        }
        grand_total += total
    summary['_grand_total'] = grand_total
    return summary


# ---------------------------------------------------------------------------
# Employer Tax (lightweight, read-only)
# ---------------------------------------------------------------------------

def calculate_employer_tax_for_period(company_id, fiscal_year_id, start, end):
    """Read employer-tax-related accounts 7510/7511 and salary 7010/7011."""
    account_map = {
        '7510': 'arbetsgivaravgifter',
        '7511': 'arbetsgivaravgifter_extra',
        '7010': 'löner_tjänstemän',
        '7011': 'löner_kollektiv',
    }
    result = {}
    total_employer_tax = Decimal('0')
    total_salaries = Decimal('0')

    for acct_num, label in account_map.items():
        account = Account.query.filter_by(
            company_id=company_id, account_number=acct_num
        ).first()
        if not account:
            result[label] = Decimal('0')
            continue
        row = db.session.query(
            func.coalesce(func.sum(VerificationRow.debit), 0) -
            func.coalesce(func.sum(VerificationRow.credit), 0)
        ).join(Verification).filter(
            VerificationRow.account_id == account.id,
            Verification.fiscal_year_id == fiscal_year_id,
            Verification.verification_date >= start,
            Verification.verification_date <= end,
        ).scalar()
        amount = Decimal(str(row)) if row else Decimal('0')
        result[label] = amount
        if acct_num.startswith('751'):
            total_employer_tax += amount
        elif acct_num.startswith('701'):
            total_salaries += amount

    result['total_employer_tax'] = total_employer_tax
    result['total_salaries'] = total_salaries
    return result
