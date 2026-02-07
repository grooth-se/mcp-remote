"""Salary service for payroll processing, tax, pension, and reporting."""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models.salary import Employee, SalaryRun, SalaryEntry, MONTH_NAMES_SV
from app.models.accounting import FiscalYear, Account
from app.services.accounting_service import create_verification


# ---------------------------------------------------------------------------
# Tax calculation
# ---------------------------------------------------------------------------

def calculate_tax_deduction(gross, tax_table, tax_column=1):
    """Calculate PAYE tax (källskatt) using simplified percentage-based approach.

    tax_table number approximates the tax percentage.
    tax_column adjusts slightly (column 1 = standard).
    """
    gross = Decimal(str(gross))
    pct = Decimal(str(tax_table))
    # Column adjustments: col 1=0, col 2=-2, col 3=-4, col 4=+2, col 5=+4, col 6=+6
    col_adj = {1: 0, 2: -2, 3: -4, 4: 2, 5: 4, 6: 6}
    adjustment = Decimal(str(col_adj.get(tax_column, 0)))
    effective_pct = pct + adjustment
    tax = (gross * effective_pct / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return max(tax, Decimal('0'))


# ---------------------------------------------------------------------------
# Employer contributions
# ---------------------------------------------------------------------------

STANDARD_RATE = Decimal('31.42')
REDUCED_RATE = Decimal('10.21')


def calculate_employer_contributions(gross, birth_year=None):
    """Calculate Swedish employer contributions (arbetsgivaravgifter).

    Standard: 31.42%. Reduced for young (<26) and senior (>65): 10.21%.
    """
    gross = Decimal(str(gross))
    rate = STANDARD_RATE
    if birth_year is not None:
        current_year = date.today().year
        age = current_year - birth_year
        if age < 26 or age > 65:
            rate = REDUCED_RATE
    return (gross * rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pension
# ---------------------------------------------------------------------------

def calculate_pension(gross, plan, ibb=80000):
    """Calculate pension contribution.

    ITP1: 4.5% up to 7.5*IBB/12 monthly, 30% above that threshold.
    ITP2: simplified 4.5% flat.
    None: 0.
    """
    gross = Decimal(str(gross))
    if plan == 'none' or not plan:
        return Decimal('0')

    if plan == 'ITP2':
        return (gross * Decimal('4.5') / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    # ITP1
    threshold = Decimal(str(ibb)) * Decimal('7.5') / Decimal('12')
    if gross <= threshold:
        return (gross * Decimal('4.5') / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    else:
        below = (threshold * Decimal('4.5') / Decimal('100'))
        above = ((gross - threshold) * Decimal('30') / Decimal('100'))
        return (below + above).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Salary run lifecycle
# ---------------------------------------------------------------------------

VACATION_PAY_RATE = Decimal('12')  # 12%


def _calculate_entry(employee):
    """Calculate a SalaryEntry for an employee based on their master data."""
    gross = Decimal(str(employee.monthly_salary))
    tax = calculate_tax_deduction(gross, employee.tax_table, employee.tax_column)
    net = gross - tax
    employer = calculate_employer_contributions(gross)
    pension = calculate_pension(gross, employee.pension_plan)
    vacation = (gross * VACATION_PAY_RATE / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    return {
        'gross_salary': gross,
        'tax_deduction': tax,
        'net_salary': net,
        'employer_contributions': employer,
        'pension_amount': pension,
        'vacation_pay_provision': vacation,
        'other_deductions': Decimal('0'),
        'other_additions': Decimal('0'),
    }


def create_salary_run(company_id, fiscal_year_id, period_year, period_month):
    """Create a draft salary run with auto-populated entries for all active employees."""
    # Check for existing run
    existing = SalaryRun.query.filter_by(
        company_id=company_id,
        period_year=period_year,
        period_month=period_month,
    ).first()
    if existing:
        raise ValueError(
            f'Löneköring finns redan för {MONTH_NAMES_SV[period_month]} {period_year}'
        )

    run = SalaryRun(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        period_year=period_year,
        period_month=period_month,
        status='draft',
    )
    db.session.add(run)
    db.session.flush()

    employees = Employee.query.filter_by(
        company_id=company_id, active=True
    ).all()

    for emp in employees:
        calc = _calculate_entry(emp)
        entry = SalaryEntry(
            salary_run_id=run.id,
            employee_id=emp.id,
            **calc,
        )
        db.session.add(entry)

    db.session.flush()
    _update_run_totals(run)
    db.session.commit()
    return run


def _update_run_totals(run):
    """Recalculate run totals from entries."""
    entries = SalaryEntry.query.filter_by(salary_run_id=run.id).all()
    run.total_gross = sum(e.gross_salary for e in entries)
    run.total_tax = sum(e.tax_deduction for e in entries)
    run.total_net = sum(e.net_salary for e in entries)
    run.total_employer_contributions = sum(e.employer_contributions for e in entries)
    run.total_pension = sum(e.pension_amount for e in entries)


def recalculate_salary_entry(entry_id, overrides=None):
    """Recalculate a single entry, applying optional overrides."""
    entry = db.session.get(SalaryEntry, entry_id)
    if not entry:
        raise ValueError('Lönepost hittades inte')
    if entry.salary_run.status != 'draft':
        raise ValueError('Kan bara ändra utkast')

    emp = entry.employee
    calc = _calculate_entry(emp)

    if overrides:
        for key in ('gross_salary', 'tax_deduction', 'other_deductions',
                    'other_additions', 'notes'):
            if key in overrides and overrides[key] is not None:
                calc[key] = overrides[key] if key == 'notes' else Decimal(str(overrides[key]))

        # Recalculate dependent values when gross is overridden
        if 'gross_salary' in overrides:
            gross = calc['gross_salary']
            if 'tax_deduction' not in overrides:
                calc['tax_deduction'] = calculate_tax_deduction(
                    gross, emp.tax_table, emp.tax_column
                )
            calc['employer_contributions'] = calculate_employer_contributions(gross)
            calc['pension_amount'] = calculate_pension(gross, emp.pension_plan)
            calc['vacation_pay_provision'] = (
                gross * VACATION_PAY_RATE / Decimal('100')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Always recalculate net
        calc['net_salary'] = (
            calc['gross_salary']
            + calc.get('other_additions', Decimal('0'))
            - calc['tax_deduction']
            - calc.get('other_deductions', Decimal('0'))
        )

    entry.gross_salary = calc['gross_salary']
    entry.tax_deduction = calc['tax_deduction']
    entry.net_salary = calc['net_salary']
    entry.employer_contributions = calc['employer_contributions']
    entry.pension_amount = calc['pension_amount']
    entry.vacation_pay_provision = calc['vacation_pay_provision']
    entry.other_deductions = calc.get('other_deductions', Decimal('0'))
    entry.other_additions = calc.get('other_additions', Decimal('0'))
    if overrides and 'notes' in overrides:
        entry.notes = overrides['notes']

    _update_run_totals(entry.salary_run)
    db.session.commit()
    return entry


def recalculate_all_entries(run_id):
    """Recalculate all entries in a salary run."""
    run = db.session.get(SalaryRun, run_id)
    if not run or run.status != 'draft':
        raise ValueError('Kan bara räkna om utkast')

    for entry in run.entries:
        calc = _calculate_entry(entry.employee)
        entry.gross_salary = calc['gross_salary']
        entry.tax_deduction = calc['tax_deduction']
        entry.net_salary = calc['net_salary']
        entry.employer_contributions = calc['employer_contributions']
        entry.pension_amount = calc['pension_amount']
        entry.vacation_pay_provision = calc['vacation_pay_provision']

    _update_run_totals(run)
    db.session.commit()
    return run


# ---------------------------------------------------------------------------
# Approval → Verification
# ---------------------------------------------------------------------------

# Account numbers from BAS kontoplan
SALARY_ACCOUNTS = {
    'salary_expense': '7010',      # Löner tjänstemän (DEBIT)
    'employer_expense': '7510',    # Arbetsgivaravgifter (DEBIT)
    'pension_expense': '7410',     # Pensionspremier (DEBIT)
    'vacation_expense': '7090',    # Semesterlöneskuld (DEBIT)
    'tax_liability': '2710',       # Personalens källskatt (CREDIT)
    'employer_liability': '2730',  # Lagstadgade soc.avg (CREDIT)
    'bank': '1930',                # Företagskonto/netto (CREDIT)
    'vacation_liability': '2920',  # Upplupna semesterlön (CREDIT)
    'pension_liability': '2950',   # Upplupna pension (CREDIT)
}


def approve_salary_run(run_id, user_id):
    """Approve a salary run and create a balanced verification."""
    run = db.session.get(SalaryRun, run_id)
    if not run:
        raise ValueError('Löneköring hittades inte')
    if run.status != 'draft':
        raise ValueError('Kan bara godkänna utkast')

    company_id = run.company_id
    fiscal_year_id = run.fiscal_year_id

    total_gross = Decimal(str(run.total_gross))
    total_tax = Decimal(str(run.total_tax))
    total_net = Decimal(str(run.total_net))
    total_employer = Decimal(str(run.total_employer_contributions))
    total_pension = Decimal(str(run.total_pension))
    total_vacation = sum(
        Decimal(str(e.vacation_pay_provision)) for e in run.entries
    )

    # Build verification rows
    def _get_account_id(account_number):
        acct = Account.query.filter_by(
            company_id=company_id, account_number=account_number
        ).first()
        if not acct:
            raise ValueError(f'Konto {account_number} saknas. Skapa det först.')
        return acct.id

    rows = []

    # DEBIT rows
    if total_gross > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['salary_expense']),
            'debit': total_gross, 'credit': Decimal('0'),
            'description': 'Bruttolöner',
        })
    if total_employer > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['employer_expense']),
            'debit': total_employer, 'credit': Decimal('0'),
            'description': 'Arbetsgivaravgifter',
        })
    if total_pension > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['pension_expense']),
            'debit': total_pension, 'credit': Decimal('0'),
            'description': 'Pensionspremier',
        })
    if total_vacation > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['vacation_expense']),
            'debit': total_vacation, 'credit': Decimal('0'),
            'description': 'Semesterlöneskuld',
        })

    # CREDIT rows
    if total_tax > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['tax_liability']),
            'debit': Decimal('0'), 'credit': total_tax,
            'description': 'Personalens källskatt',
        })
    if total_employer > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['employer_liability']),
            'debit': Decimal('0'), 'credit': total_employer,
            'description': 'Arbetsgivaravgifter skuld',
        })
    if total_net > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['bank']),
            'debit': Decimal('0'), 'credit': total_net,
            'description': 'Nettolöner utbetalda',
        })
    if total_vacation > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['vacation_liability']),
            'debit': Decimal('0'), 'credit': total_vacation,
            'description': 'Upplupna semesterlöner',
        })
    if total_pension > 0:
        rows.append({
            'account_id': _get_account_id(SALARY_ACCOUNTS['pension_liability']),
            'debit': Decimal('0'), 'credit': total_pension,
            'description': 'Upplupna pensionskostnader',
        })

    ver_date = date(run.period_year, run.period_month, 25)
    description = f'Lön {run.period_label}'

    verification = create_verification(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        verification_date=ver_date,
        description=description,
        rows=rows,
        verification_type='salary',
        created_by=user_id,
        source='salary_run',
    )

    run.verification_id = verification.id
    run.approved_by = user_id
    run.approved_at = datetime.now(timezone.utc)
    run.status = 'approved'
    db.session.commit()
    return run


def mark_salary_run_paid(run_id, paid_date):
    """Mark an approved salary run as paid."""
    run = db.session.get(SalaryRun, run_id)
    if not run:
        raise ValueError('Löneköring hittades inte')
    if run.status != 'approved':
        raise ValueError('Kan bara markera godkänd löneköring som betald')

    run.paid_date = paid_date
    run.status = 'paid'
    db.session.commit()
    return run


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def generate_salary_slip(entry):
    """Generate salary slip data for a single entry."""
    emp = entry.employee
    run = entry.salary_run
    return {
        'company': run.company,
        'period_label': run.period_label,
        'period_year': run.period_year,
        'period_month': run.period_month,
        'employee': emp,
        'gross_salary': entry.gross_salary,
        'tax_deduction': entry.tax_deduction,
        'net_salary': entry.net_salary,
        'employer_contributions': entry.employer_contributions,
        'pension_amount': entry.pension_amount,
        'vacation_pay_provision': entry.vacation_pay_provision,
        'other_deductions': entry.other_deductions,
        'other_additions': entry.other_additions,
        'notes': entry.notes,
    }


def generate_agi_data(run):
    """Generate AGI (Arbetsgivardeklaration) data for Skatteverket."""
    entries = []
    for entry in run.entries:
        emp = entry.employee
        entries.append({
            'personal_number': emp.personal_number,
            'full_name': emp.full_name,
            'gross_salary': entry.gross_salary,
            'tax_deduction': entry.tax_deduction,
            'employer_contributions': entry.employer_contributions,
            'pension_amount': entry.pension_amount,
        })
    return {
        'company': run.company,
        'period_year': run.period_year,
        'period_month': run.period_month,
        'period_label': run.period_label,
        'entries': entries,
        'total_gross': run.total_gross,
        'total_tax': run.total_tax,
        'total_employer': run.total_employer_contributions,
    }


def generate_collectum_data(company_id, period_year, period_month):
    """Generate Collectum pension report data."""
    run = SalaryRun.query.filter_by(
        company_id=company_id,
        period_year=period_year,
        period_month=period_month,
    ).first()

    if not run:
        return None

    entries = []
    for entry in run.entries:
        emp = entry.employee
        if emp.pension_plan in ('ITP1', 'ITP2'):
            entries.append({
                'personal_number': emp.personal_number,
                'full_name': emp.full_name,
                'pension_plan': emp.pension_plan,
                'gross_salary': entry.gross_salary,
                'pension_amount': entry.pension_amount,
            })

    return {
        'company': run.company,
        'period_year': period_year,
        'period_month': period_month,
        'period_label': run.period_label,
        'entries': entries,
        'total_pension': sum(e['pension_amount'] for e in entries),
    }
