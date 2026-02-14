"""Period comparison and account drill-down services.

Provides side-by-side P&L/BS comparison, year-over-year analysis,
and detailed account-level transaction views.
"""

from collections import OrderedDict
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models.accounting import Account, Verification, VerificationRow, FiscalYear
from app.services.report_service import (
    get_profit_and_loss, get_balance_sheet, _get_account_balances,
)


def compare_periods(company_id, fy_id_a, fy_id_b, report_type='pnl'):
    """Compare two fiscal years side by side.

    Returns merged section data with amounts for both periods plus changes.
    ``report_type`` is 'pnl' or 'balance'.
    """
    if report_type == 'pnl':
        data_a = get_profit_and_loss(company_id, fy_id_a)
        data_b = get_profit_and_loss(company_id, fy_id_b)
    else:
        data_a = get_balance_sheet(company_id, fy_id_a)
        data_b = get_balance_sheet(company_id, fy_id_b)

    fy_a = db.session.get(FiscalYear, fy_id_a)
    fy_b = db.session.get(FiscalYear, fy_id_b)

    sections = OrderedDict()
    all_section_names = list(data_a['sections'].keys())
    for name in data_b['sections']:
        if name not in all_section_names:
            all_section_names.append(name)

    for name in all_section_names:
        sec_a = data_a['sections'].get(name, {'accounts': [], 'total': 0})
        sec_b = data_b['sections'].get(name, {'accounts': [], 'total': 0})

        # Merge accounts by account_number
        accts_a = {a.account_number: (a, bal) for a, bal in sec_a['accounts']}
        accts_b = {a.account_number: (a, bal) for a, bal in sec_b['accounts']}

        all_numbers = list(accts_a.keys())
        for num in accts_b:
            if num not in all_numbers:
                all_numbers.append(num)
        all_numbers.sort()

        rows = []
        for num in all_numbers:
            a_entry = accts_a.get(num)
            b_entry = accts_b.get(num)
            account = a_entry[0] if a_entry else b_entry[0]
            val_a = a_entry[1] if a_entry else 0.0
            val_b = b_entry[1] if b_entry else 0.0
            change = val_a - val_b
            pct = round((change / abs(val_b)) * 100, 1) if val_b and abs(val_b) > 0.01 else None
            rows.append({
                'account_number': num,
                'account_name': account.name,
                'amount_a': round(val_a, 2),
                'amount_b': round(val_b, 2),
                'change': round(change, 2),
                'change_pct': pct,
            })

        total_a = float(sec_a['total'])
        total_b = float(sec_b['total'])
        total_change = round(total_a - total_b, 2)
        total_pct = round((total_change / abs(total_b)) * 100, 1) if total_b and abs(total_b) > 0.01 else None

        sections[name] = {
            'rows': rows,
            'total_a': round(total_a, 2),
            'total_b': round(total_b, 2),
            'total_change': total_change,
            'total_change_pct': total_pct,
        }

    result = {
        'sections': sections,
        'fy_a': fy_a,
        'fy_b': fy_b,
        'report_type': report_type,
    }

    if report_type == 'pnl':
        for key in ('gross_profit', 'operating_result', 'result_before_tax'):
            val_a = float(data_a.get(key, 0))
            val_b = float(data_b.get(key, 0))
            change = round(val_a - val_b, 2)
            pct = round((change / abs(val_b)) * 100, 1) if val_b and abs(val_b) > 0.01 else None
            result[key] = {
                'amount_a': round(val_a, 2),
                'amount_b': round(val_b, 2),
                'change': change,
                'change_pct': pct,
            }
    else:
        for key in ('total_assets', 'total_equity_liabilities'):
            val_a = float(data_a.get(key, 0))
            val_b = float(data_b.get(key, 0))
            change = round(val_a - val_b, 2)
            pct = round((change / abs(val_b)) * 100, 1) if val_b and abs(val_b) > 0.01 else None
            result[key] = {
                'amount_a': round(val_a, 2),
                'amount_b': round(val_b, 2),
                'change': change,
                'change_pct': pct,
            }

    return result


def get_yoy_analysis(company_id, fiscal_year_id, num_years=3):
    """Year-over-year analysis: section totals across multiple years.

    Returns {years: [FY objects], sections: {name: [totals]}, summaries: {key: [values]}}.
    """
    current_fy = db.session.get(FiscalYear, fiscal_year_id)
    all_fys = (FiscalYear.query
               .filter_by(company_id=company_id)
               .filter(FiscalYear.year <= current_fy.year)
               .order_by(FiscalYear.year.desc())
               .limit(num_years)
               .all())
    all_fys.reverse()  # chronological order

    years = []
    section_data = OrderedDict()
    summaries = OrderedDict()

    for fy in all_fys:
        pnl = get_profit_and_loss(company_id, fy.id)
        years.append(fy)

        for name, sec in pnl['sections'].items():
            if name not in section_data:
                section_data[name] = []
            section_data[name].append(round(float(sec['total']), 2))

        for key in ('gross_profit', 'operating_result', 'result_before_tax'):
            if key not in summaries:
                summaries[key] = []
            summaries[key].append(round(float(pnl[key]), 2))

    # Add change percentages
    changes = OrderedDict()
    for name, values in section_data.items():
        ch = [None]  # first year has no comparison
        for i in range(1, len(values)):
            prev = values[i - 1]
            pct = round(((values[i] - prev) / abs(prev)) * 100, 1) if prev and abs(prev) > 0.01 else None
            ch.append(pct)
        changes[name] = ch

    summary_changes = OrderedDict()
    for key, values in summaries.items():
        ch = [None]
        for i in range(1, len(values)):
            prev = values[i - 1]
            pct = round(((values[i] - prev) / abs(prev)) * 100, 1) if prev and abs(prev) > 0.01 else None
            ch.append(pct)
        summary_changes[key] = ch

    return {
        'years': years,
        'sections': section_data,
        'section_changes': changes,
        'summaries': summaries,
        'summary_changes': summary_changes,
    }


def get_account_drilldown(company_id, fiscal_year_id, account_number,
                          start_date=None, end_date=None):
    """Detailed account drill-down with running balance and monthly summary.

    Returns transactions, running balance, opening/closing, and monthly totals.
    """
    fy = db.session.get(FiscalYear, fiscal_year_id)
    account = Account.query.filter_by(
        company_id=company_id, account_number=account_number
    ).first()

    if not account:
        return None

    query = (db.session.query(Verification, VerificationRow)
             .join(VerificationRow, VerificationRow.verification_id == Verification.id)
             .filter(
                 Verification.company_id == company_id,
                 Verification.fiscal_year_id == fiscal_year_id,
                 VerificationRow.account_id == account.id,
             )
             .order_by(Verification.verification_date, Verification.verification_number))

    if start_date:
        query = query.filter(Verification.verification_date >= start_date)
    if end_date:
        query = query.filter(Verification.verification_date <= end_date)

    results = query.all()

    # Opening balance: sum of all transactions before start_date (if filtering)
    opening_balance = 0.0
    if start_date:
        opening = (db.session.query(
            func.coalesce(func.sum(VerificationRow.debit), 0),
            func.coalesce(func.sum(VerificationRow.credit), 0),
        ).join(Verification, Verification.id == VerificationRow.verification_id)
         .filter(
             Verification.company_id == company_id,
             Verification.fiscal_year_id == fiscal_year_id,
             VerificationRow.account_id == account.id,
             Verification.verification_date < start_date,
         ).first())
        if opening:
            opening_balance = float(opening[0] - opening[1])

    # Build transaction list with running balance
    transactions = []
    running = opening_balance
    monthly_debit = {}
    monthly_credit = {}

    for ver, row in results:
        debit = float(row.debit)
        credit = float(row.credit)
        running += debit - credit

        transactions.append({
            'date': ver.verification_date,
            'verification_id': ver.id,
            'verification_number': ver.verification_number,
            'description': ver.description or row.description or '',
            'debit': round(debit, 2),
            'credit': round(credit, 2),
            'balance': round(running, 2),
        })

        month = ver.verification_date.month
        monthly_debit[month] = monthly_debit.get(month, 0) + debit
        monthly_credit[month] = monthly_credit.get(month, 0) + credit

    closing_balance = running

    # Monthly summary for sparkline
    monthly = []
    for m in range(1, 13):
        d = round(monthly_debit.get(m, 0), 2)
        c = round(monthly_credit.get(m, 0), 2)
        monthly.append({
            'month': m,
            'debit': d,
            'credit': c,
            'net': round(d - c, 2),
        })

    return {
        'account': account,
        'fiscal_year': fy,
        'opening_balance': round(opening_balance, 2),
        'closing_balance': round(closing_balance, 2),
        'transactions': transactions,
        'monthly': monthly,
        'total_debit': round(sum(t['debit'] for t in transactions), 2),
        'total_credit': round(sum(t['credit'] for t in transactions), 2),
    }
