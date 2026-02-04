"""Project Report Generator - Report1, Report2, Report3 style reports.

Generates reports similar to the Excel Projectfile reports:
- Report1: Revenue/COGS/GM for Current period, Year to date, Project to date
- Report2: Project valuation with changes from previous period
- Report3: Order book analysis
"""

from dataclasses import dataclass
from typing import List, Optional
import pandas as pd
from app.models import FactProjectMonthly


@dataclass
class Report1Row:
    """Report1 row: Revenue/COGS/GM by project."""
    project_number: str
    project_name: str
    # Current period
    current_revenue: float
    current_cogs: float
    current_gm: float
    current_gm_pct: float
    # Year to date
    ytd_revenue: float
    ytd_cogs: float
    ytd_gm: float
    ytd_gm_pct: float
    # Project to date
    ptd_revenue: float
    ptd_cogs: float
    ptd_gm: float
    ptd_gm_pct: float


@dataclass
class Report2Row:
    """Report2 row: Project valuation and changes."""
    project_number: str
    project_name: str
    # Last updated calculation
    tcv_revenue: float
    cogs: float
    gm: float
    gm_pct: float
    poc: float
    contingency: float
    # Changes in current period
    delta_revenue: float
    delta_cogs: float
    delta_gm: float
    currency_effect: float


@dataclass
class Report3Row:
    """Report3 row: Order book analysis."""
    project_number: str
    project_name: str
    ob_order_backlog: float
    order_intake: float
    revenue: float
    eb_order_backlog: float
    gm_pct: float
    production_start: Optional[str]
    delivery: Optional[str]


class ProjectReportGenerator:
    """Generate project reports from stored calculation data."""

    def __init__(self, current_date: str, previous_date: str = None, year_end_date: str = None):
        """Initialize report generator.

        Args:
            current_date: Current period closing date (YYYY-MM-DD)
            previous_date: Previous month closing date (optional)
            year_end_date: End of last year closing date (optional, for YTD)
        """
        self.current_date = current_date
        self.previous_date = previous_date
        self.year_end_date = year_end_date

        # Load data
        self.current_data = self._load_period_data(current_date)
        self.previous_data = self._load_period_data(previous_date) if previous_date else {}
        self.year_end_data = self._load_period_data(year_end_date) if year_end_date else {}

    def _load_period_data(self, closing_date: str) -> dict:
        """Load project data for a period as dict keyed by project_number."""
        if not closing_date:
            return {}
        projects = FactProjectMonthly.get_by_closing_date(closing_date)
        return {p.project_number: p for p in projects}

    def generate_report1(self) -> List[Report1Row]:
        """Generate Report1: Revenue/COGS/GM summary.

        Current period = current - previous
        Year to date = current - year_end
        Project to date = current totals
        """
        rows = []

        for proj_num, curr in self.current_data.items():
            prev = self.previous_data.get(proj_num)
            year_end = self.year_end_data.get(proj_num)

            # Project to date (cumulative)
            ptd_revenue = (curr.total_income_cur or 0) / 1000  # Convert to SEK'000
            ptd_cogs = (curr.total_cost_cur or 0) / 1000
            ptd_gm = ptd_revenue - ptd_cogs
            ptd_gm_pct = ptd_gm / ptd_revenue if ptd_revenue else 0

            # Current period delta
            if prev:
                prev_revenue = (prev.total_income_cur or 0) / 1000
                prev_cogs = (prev.total_cost_cur or 0) / 1000
            else:
                prev_revenue = 0
                prev_cogs = 0

            current_revenue = ptd_revenue - prev_revenue
            current_cogs = ptd_cogs - prev_cogs
            current_gm = current_revenue - current_cogs
            current_gm_pct = current_gm / current_revenue if current_revenue else 0

            # Year to date
            if year_end:
                ye_revenue = (year_end.total_income_cur or 0) / 1000
                ye_cogs = (year_end.total_cost_cur or 0) / 1000
            else:
                ye_revenue = 0
                ye_cogs = 0

            ytd_revenue = ptd_revenue - ye_revenue
            ytd_cogs = ptd_cogs - ye_cogs
            ytd_gm = ytd_revenue - ytd_cogs
            ytd_gm_pct = ytd_gm / ytd_revenue if ytd_revenue else 0

            rows.append(Report1Row(
                project_number=proj_num,
                project_name=curr.project_name or '',
                current_revenue=current_revenue,
                current_cogs=current_cogs,
                current_gm=current_gm,
                current_gm_pct=current_gm_pct,
                ytd_revenue=ytd_revenue,
                ytd_cogs=ytd_cogs,
                ytd_gm=ytd_gm,
                ytd_gm_pct=ytd_gm_pct,
                ptd_revenue=ptd_revenue,
                ptd_cogs=ptd_cogs,
                ptd_gm=ptd_gm,
                ptd_gm_pct=ptd_gm_pct,
            ))

        return sorted(rows, key=lambda r: r.project_number)

    def generate_report2(self) -> List[Report2Row]:
        """Generate Report2: Project valuation with changes."""
        rows = []

        for proj_num, curr in self.current_data.items():
            prev = self.previous_data.get(proj_num)

            # Last updated calculation (current values in SEK'000)
            tcv_revenue = (curr.total_income_cur or 0) / 1000
            cogs = (curr.total_cost_cur or 0) / 1000
            gm = tcv_revenue - cogs
            gm_pct = curr.profit_margin_cur or 0
            poc = curr.completion_cur1 or 0
            contingency = (curr.contingency_cur or 0) / 1000

            # Changes from previous period
            if prev:
                prev_revenue = (prev.total_income_cur or 0) / 1000
                prev_cogs = (prev.total_cost_cur or 0) / 1000
                prev_gm = prev_revenue - prev_cogs

                delta_revenue = tcv_revenue - prev_revenue
                delta_cogs = cogs - prev_cogs
                delta_gm = gm - prev_gm
                # Currency effect from diff_income/diff_cost
                currency_effect = ((curr.diff_income or 0) - (curr.diff_cost or 0)) / 1000
            else:
                delta_revenue = tcv_revenue
                delta_cogs = cogs
                delta_gm = gm
                currency_effect = 0

            rows.append(Report2Row(
                project_number=proj_num,
                project_name=curr.project_name or '',
                tcv_revenue=tcv_revenue,
                cogs=cogs,
                gm=gm,
                gm_pct=gm_pct,
                poc=poc,
                contingency=contingency,
                delta_revenue=delta_revenue,
                delta_cogs=delta_cogs,
                delta_gm=delta_gm,
                currency_effect=currency_effect,
            ))

        return sorted(rows, key=lambda r: r.project_number)

    def generate_report3(self) -> List[Report3Row]:
        """Generate Report3: Order book analysis."""
        rows = []

        for proj_num, curr in self.current_data.items():
            prev = self.previous_data.get(proj_num)

            # Opening balance = previous period remaining income
            if prev:
                ob_order_backlog = (prev.remaining_income_cur or 0) / 1000
            else:
                ob_order_backlog = 0

            # Ending balance = current remaining income
            eb_order_backlog = (curr.remaining_income_cur or 0) / 1000

            # Revenue this period
            if prev:
                revenue = ((curr.actual_income_cur or 0) - (prev.actual_income_cur or 0)) / 1000
            else:
                revenue = (curr.actual_income_cur or 0) / 1000

            # Order intake = EB - OB + Revenue
            order_intake = eb_order_backlog - ob_order_backlog + revenue

            gm_pct = curr.profit_margin_cur or 0

            rows.append(Report3Row(
                project_number=proj_num,
                project_name=curr.project_name or '',
                ob_order_backlog=ob_order_backlog,
                order_intake=order_intake,
                revenue=revenue,
                eb_order_backlog=eb_order_backlog,
                gm_pct=gm_pct,
                production_start=None,  # Not stored in current model
                delivery=None,
            ))

        return sorted(rows, key=lambda r: r.project_number)

    def generate_summary(self) -> dict:
        """Generate summary totals for the Project sheet."""
        # Calculate totals from current data
        total_accrued = sum((p.accrued_income_cur or 0) for p in self.current_data.values())
        total_orderbook = sum((p.remaining_income_cur or 0) for p in self.current_data.values())
        total_revenue = sum((p.total_income_cur or 0) for p in self.current_data.values())
        total_cogs = sum((p.total_cost_cur or 0) for p in self.current_data.values())
        total_gm = total_revenue - total_cogs
        gm_pct = total_gm / total_revenue if total_revenue else 0

        total_actual_income = sum((p.actual_income_cur or 0) for p in self.current_data.values())
        total_actual_cost = sum((p.actual_cost_cur or 0) for p in self.current_data.values())
        total_remaining_cost = sum((p.remaining_cost or 0) for p in self.current_data.values())
        total_contingency = sum((p.contingency_cur or 0) for p in self.current_data.values())

        return {
            'closing_date': self.current_date,
            'project_count': len(self.current_data),
            'accrued_revenue': total_accrued,
            'orderbook': total_orderbook,
            'total_revenue': total_revenue,
            'total_cogs': total_cogs,
            'gross_profit': total_gm,
            'gross_margin_pct': gm_pct,
            'actual_income': total_actual_income,
            'actual_cost': total_actual_cost,
            'remaining_cost': total_remaining_cost,
            'contingency': total_contingency,
        }

    def to_dataframe_report1(self) -> pd.DataFrame:
        """Export Report1 to DataFrame."""
        rows = self.generate_report1()
        return pd.DataFrame([r.__dict__ for r in rows])

    def to_dataframe_report2(self) -> pd.DataFrame:
        """Export Report2 to DataFrame."""
        rows = self.generate_report2()
        return pd.DataFrame([r.__dict__ for r in rows])

    def to_dataframe_report3(self) -> pd.DataFrame:
        """Export Report3 to DataFrame."""
        rows = self.generate_report3()
        return pd.DataFrame([r.__dict__ for r in rows])
