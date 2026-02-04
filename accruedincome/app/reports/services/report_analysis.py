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


def compare_two_months(current_date: str, previous_date: str) -> dict:
    """Compare two closing dates and calculate deltas.

    Args:
        current_date: Current closing date (YYYY-MM-DD)
        previous_date: Previous closing date (YYYY-MM-DD)

    Returns:
        Dictionary with:
        - detail: DataFrame with per-project deltas
        - summary_curr: Current period summary
        - summary_prev: Previous period summary
    """
    # Get projects for both periods
    curr_projects = FactProjectMonthly.get_by_closing_date(current_date)
    prev_projects = FactProjectMonthly.get_by_closing_date(previous_date)

    # Convert to DataFrames
    curr_data = []
    for p in curr_projects:
        curr_data.append({
            'project_number': p.project_number,
            'project_name': p.project_name,
            'total_income_curr': p.total_income_cur or 0,
            'total_cost_curr': p.total_cost_cur or 0,
            'gross_margin_curr': (p.total_income_cur or 0) - (p.total_cost_cur or 0),
            'accrued_income_curr': p.accrued_income_cur or 0,
            'completion_curr': p.completion_cur1 or 0,
        })

    prev_data = []
    for p in prev_projects:
        prev_data.append({
            'project_number': p.project_number,
            'total_income_prev': p.total_income_cur or 0,
            'total_cost_prev': p.total_cost_cur or 0,
            'gross_margin_prev': (p.total_income_cur or 0) - (p.total_cost_cur or 0),
            'accrued_income_prev': p.accrued_income_cur or 0,
            'completion_prev': p.completion_cur1 or 0,
        })

    df_curr = pd.DataFrame(curr_data) if curr_data else pd.DataFrame()
    df_prev = pd.DataFrame(prev_data) if prev_data else pd.DataFrame()

    # Merge on project_number (outer join to capture new/removed projects)
    if not df_curr.empty and not df_prev.empty:
        merged = df_curr.merge(df_prev, on='project_number', how='outer')
    elif not df_curr.empty:
        merged = df_curr.copy()
        for col in ['total_income_prev', 'total_cost_prev', 'gross_margin_prev',
                    'accrued_income_prev', 'completion_prev']:
            merged[col] = 0
    elif not df_prev.empty:
        merged = df_prev.copy()
        merged['project_name'] = ''
        for col in ['total_income_curr', 'total_cost_curr', 'gross_margin_curr',
                    'accrued_income_curr', 'completion_curr']:
            merged[col] = 0
    else:
        merged = pd.DataFrame()

    # Fill NaN with 0
    merged = merged.fillna(0)

    # Calculate deltas
    if not merged.empty:
        merged['delta_revenue'] = merged['total_income_curr'] - merged['total_income_prev']
        merged['delta_cost'] = merged['total_cost_curr'] - merged['total_cost_prev']
        merged['delta_gross_margin'] = merged['gross_margin_curr'] - merged['gross_margin_prev']
        merged['delta_accrued'] = merged['accrued_income_curr'] - merged['accrued_income_prev']
        merged['delta_completion'] = merged['completion_curr'] - merged['completion_prev']

    return {
        'detail': merged,
        'summary_curr': generate_summary_sheet(current_date),
        'summary_prev': generate_summary_sheet(previous_date),
        'current_date': current_date,
        'previous_date': previous_date,
    }
