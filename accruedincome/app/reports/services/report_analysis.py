"""Report analysis and KPI generation.

Ported from legacy acrued5_report_analysis.py
"""

import pandas as pd
from app.extensions import db
from app.models import FactProjectMonthly


def get_all_closing_dates():
    """Return all distinct closing dates, sorted descending."""
    return FactProjectMonthly.get_closing_dates()


def generate_kpi_report1(closing_date: str) -> pd.DataFrame:
    """Generate KPI Report 1: Revenue/COGS/GM by project.

    Args:
        closing_date: Closing date string (YYYY-MM-DD)

    Returns:
        DataFrame with project-level revenue metrics
    """
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    if not projects:
        return pd.DataFrame()

    data = []
    for p in projects:
        data.append({
            'project_number': p.project_number,
            'project_name': p.project_name or '',
            'actual_income': p.actual_income_cur or 0,
            'actual_cost': p.actual_cost_cur or 0,
            'accrued_income': p.accrued_income_cur or 0,
            'remaining_income': p.remaining_income or 0,
            'remaining_cost': p.remaining_cost or 0,
            'total_income': p.total_income_cur or 0,
            'COGS': p.total_cost_cur or 0,
            'GM': (p.total_income_cur or 0) - (p.total_cost_cur or 0),
            'GM_pct': p.profit_margin_cur or 0,
        })

    return pd.DataFrame(data)


def generate_kpi_report2(closing_date: str) -> pd.DataFrame:
    """Generate KPI Report 2: Project valuation with PoC.

    Args:
        closing_date: Closing date string (YYYY-MM-DD)

    Returns:
        DataFrame with project valuation metrics
    """
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    if not projects:
        return pd.DataFrame()

    data = []
    for p in projects:
        data.append({
            'project_number': p.project_number,
            'project_name': p.project_name or '',
            'TCV': p.total_income_cur or 0,
            'COGS': p.total_cost_cur or 0,
            'GM': (p.total_income_cur or 0) - (p.total_cost_cur or 0),
            'GM_pct': p.profit_margin_cur or 0,
            'PoC': p.completion_cur1 or 0,
            'contingency': p.contingency_cur or 0,
            'risk': p.risk_amount or 0,
        })

    return pd.DataFrame(data)


def generate_summary_sheet(closing_date: str) -> dict:
    """Generate summary KPIs for a closing date.

    Args:
        closing_date: Closing date string (YYYY-MM-DD)

    Returns:
        Dictionary with aggregate KPIs
    """
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    if not projects:
        return {
            'closing_date': closing_date,
            'project_count': 0,
            'total_revenue': 0,
            'total_cost': 0,
            'total_gross_margin': 0,
            'total_accrued': 0,
            'total_contingency': 0,
            'avg_gm_pct': 0,
        }

    total_revenue = sum(p.total_income_cur or 0 for p in projects)
    total_cost = sum(p.total_cost_cur or 0 for p in projects)
    total_accrued = sum(p.accrued_income_cur or 0 for p in projects)
    total_contingency = sum(p.contingency_cur or 0 for p in projects)

    # Calculate average GM%
    gm_pcts = [p.profit_margin_cur for p in projects if p.profit_margin_cur]
    avg_gm_pct = sum(gm_pcts) / len(gm_pcts) if gm_pcts else 0

    return {
        'closing_date': closing_date,
        'project_count': len(projects),
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_gross_margin': total_revenue - total_cost,
        'total_accrued': total_accrued,
        'total_contingency': total_contingency,
        'avg_gm_pct': avg_gm_pct,
    }


def _project_to_dict(p, suffix):
    """Convert a FactProjectMonthly to a dict with suffixed column names."""
    return {
        'project_number': p.project_number,
        f'project_name_{suffix}': p.project_name or '',
        f'customer_name_{suffix}': p.customer_name or '',
        # Revenue fields
        f'expected_income_{suffix}': p.expected_income or 0,
        f'actual_income_{suffix}': p.actual_income_cur or 0,
        f'remaining_income_{suffix}': p.remaining_income or 0,
        f'accrued_income_{suffix}': p.accrued_income_cur or 0,
        f'total_income_{suffix}': p.total_income_cur or 0,
        # Cost fields
        f'total_cost_{suffix}': p.total_cost_cur or 0,
        f'remaining_cost_{suffix}': p.remaining_cost or 0,
        # Profit fields
        f'project_profit_{suffix}': p.project_profit or 0,
        f'profit_margin_{suffix}': p.profit_margin_cur or 0,
        f'diff_income_{suffix}': p.diff_income or 0,
        f'diff_cost_{suffix}': p.diff_cost or 0,
        # Order book
        f'completion_{suffix}': p.completion_cur1 or 0,
        # Booking
        f'contingency_{suffix}': p.contingency_cur or 0,
    }


def compare_two_months(current_date: str, previous_date: str) -> dict:
    """Compare two closing dates and calculate deltas.

    Args:
        current_date: Current closing date (YYYY-MM-DD)
        previous_date: Previous closing date (YYYY-MM-DD)

    Returns:
        Dictionary with:
        - detail: DataFrame with per-project deltas for all report views
        - summary_curr: Current period summary
        - summary_prev: Previous period summary
    """
    # Get projects for both periods
    curr_projects = FactProjectMonthly.get_by_closing_date(current_date)
    prev_projects = FactProjectMonthly.get_by_closing_date(previous_date)

    # Convert to DataFrames with all fields needed for report views
    curr_data = [_project_to_dict(p, 'curr') for p in curr_projects]
    prev_data = [_project_to_dict(p, 'prev') for p in prev_projects]

    df_curr = pd.DataFrame(curr_data) if curr_data else pd.DataFrame()
    df_prev = pd.DataFrame(prev_data) if prev_data else pd.DataFrame()

    # Merge on project_number (outer join to capture new/removed projects)
    if not df_curr.empty and not df_prev.empty:
        merged = df_curr.merge(df_prev, on='project_number', how='outer')
    elif not df_curr.empty:
        merged = df_curr.copy()
        # Add zero prev columns
        for col in df_curr.columns:
            if col.endswith('_curr') and col != 'project_number':
                merged[col.replace('_curr', '_prev')] = 0
    elif not df_prev.empty:
        merged = df_prev.copy()
        # Add zero curr columns
        for col in df_prev.columns:
            if col.endswith('_prev') and col != 'project_number':
                merged[col.replace('_prev', '_curr')] = 0
    else:
        merged = pd.DataFrame()

    # Fill NaN with 0 for numeric, '' for text
    if not merged.empty:
        text_cols = [c for c in merged.columns if 'project_name' in c or 'customer_name' in c]
        num_cols = [c for c in merged.columns if c not in text_cols and c != 'project_number']
        merged[text_cols] = merged[text_cols].fillna('')
        merged[num_cols] = merged[num_cols].fillna(0)

        # Resolve project_name: prefer curr, fall back to prev
        merged['project_name'] = merged.apply(
            lambda r: r.get('project_name_curr', '') or r.get('project_name_prev', ''), axis=1)
        merged['customer_name'] = merged.apply(
            lambda r: r.get('customer_name_curr', '') or r.get('customer_name_prev', ''), axis=1)

        # Compute gross margins
        merged['gross_margin_curr'] = merged['total_income_curr'] - merged['total_cost_curr']
        merged['gross_margin_prev'] = merged['total_income_prev'] - merged['total_cost_prev']

        # Remaining margin
        merged['remaining_margin_curr'] = merged['remaining_income_curr'] - merged['remaining_cost_curr']
        merged['remaining_margin_prev'] = merged['remaining_income_prev'] - merged['remaining_cost_prev']

        # Net booking
        merged['net_booking_curr'] = merged['accrued_income_curr'] - merged['contingency_curr']
        merged['net_booking_prev'] = merged['accrued_income_prev'] - merged['contingency_prev']

        # Calculate all deltas
        delta_fields = [
            'total_income', 'total_cost', 'gross_margin', 'accrued_income',
            'completion', 'expected_income', 'actual_income', 'remaining_income',
            'remaining_cost', 'remaining_margin', 'project_profit', 'profit_margin',
            'diff_income', 'diff_cost', 'contingency', 'net_booking',
        ]
        for field in delta_fields:
            merged[f'delta_{field}'] = merged[f'{field}_curr'] - merged[f'{field}_prev']

        # Legacy aliases for backward compat
        merged['delta_revenue'] = merged['delta_total_income']
        merged['delta_accrued'] = merged['delta_accrued_income']
        merged['total_income_curr_legacy'] = merged['total_income_curr']
        merged['total_income_prev_legacy'] = merged['total_income_prev']
        merged['accrued_income_curr_legacy'] = merged['accrued_income_curr']
        merged['accrued_income_prev_legacy'] = merged['accrued_income_prev']

    return {
        'detail': merged,
        'summary_curr': generate_summary_sheet(current_date),
        'summary_prev': generate_summary_sheet(previous_date),
        'current_date': current_date,
        'previous_date': previous_date,
    }
