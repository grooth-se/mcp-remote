"""Monthly Report Commentary Generator.

Generates analysis and commentary for monthly management reports by comparing
current period vs previous month and year-to-date performance.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from app.models import FactProjectMonthly


@dataclass
class ProjectHighlight:
    """A notable project change or metric."""
    project_number: str
    project_name: str
    metric: str
    current_value: float
    previous_value: float
    change: float
    change_pct: float
    comment: str


@dataclass
class CommentarySection:
    """A section of the commentary with bullets and data."""
    title: str
    icon: str
    bullets: List[str] = field(default_factory=list)
    highlights: List[ProjectHighlight] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass
class MonthlyCommentary:
    """Complete monthly report commentary."""
    current_date: str
    previous_date: str
    year_end_date: str

    # Summary metrics
    summary: dict = field(default_factory=dict)

    # Commentary sections
    revenue_section: CommentarySection = None
    margin_section: CommentarySection = None
    orderbook_section: CommentarySection = None
    project_section: CommentarySection = None
    risk_section: CommentarySection = None

    # Top movers
    top_revenue_increases: List[ProjectHighlight] = field(default_factory=list)
    top_revenue_decreases: List[ProjectHighlight] = field(default_factory=list)
    top_margin_changes: List[ProjectHighlight] = field(default_factory=list)
    new_projects: List[dict] = field(default_factory=list)
    completed_projects: List[dict] = field(default_factory=list)


class CommentaryGenerator:
    """Generate monthly report commentary from project data."""

    # Thresholds for highlighting changes
    SIGNIFICANT_REVENUE_CHANGE = 500000  # SEK
    SIGNIFICANT_MARGIN_CHANGE = 0.05  # 5 percentage points
    SIGNIFICANT_ORDERBOOK_CHANGE = 1000000  # SEK

    def __init__(self, current_date: str, previous_date: str, year_end_date: str = None):
        """Initialize commentary generator.

        Args:
            current_date: Current period closing date (YYYY-MM-DD)
            previous_date: Previous month closing date
            year_end_date: End of previous year for YTD calculations
        """
        self.current_date = current_date
        self.previous_date = previous_date
        self.year_end_date = year_end_date

        # Load data
        self.current_data = self._load_data(current_date)
        self.previous_data = self._load_data(previous_date)
        self.year_end_data = self._load_data(year_end_date) if year_end_date else {}

    def _load_data(self, closing_date: str) -> dict:
        """Load project data as dict keyed by project_number."""
        if not closing_date:
            return {}
        projects = FactProjectMonthly.get_by_closing_date(closing_date)
        return {p.project_number: p for p in projects}

    def _format_amount(self, amount: float) -> str:
        """Format amount in millions or thousands."""
        if abs(amount) >= 1000000:
            return f"{amount/1000000:.1f}M"
        elif abs(amount) >= 1000:
            return f"{amount/1000:.0f}K"
        else:
            return f"{amount:.0f}"

    def _calculate_summary(self) -> dict:
        """Calculate summary metrics for current, previous, and YTD."""
        def sum_metric(data: dict, attr: str) -> float:
            return sum(getattr(p, attr) or 0 for p in data.values())

        # Current period totals
        curr_revenue = sum_metric(self.current_data, 'total_income_cur')
        curr_cost = sum_metric(self.current_data, 'total_cost_cur')
        curr_gm = curr_revenue - curr_cost
        curr_gm_pct = curr_gm / curr_revenue if curr_revenue else 0
        curr_accrued = sum_metric(self.current_data, 'accrued_income_cur')
        curr_orderbook = sum_metric(self.current_data, 'remaining_income_cur')
        curr_contingency = sum_metric(self.current_data, 'contingency_cur')

        # Previous period totals
        prev_revenue = sum_metric(self.previous_data, 'total_income_cur')
        prev_cost = sum_metric(self.previous_data, 'total_cost_cur')
        prev_gm = prev_revenue - prev_cost
        prev_gm_pct = prev_gm / prev_revenue if prev_revenue else 0
        prev_accrued = sum_metric(self.previous_data, 'accrued_income_cur')
        prev_orderbook = sum_metric(self.previous_data, 'remaining_income_cur')

        # Year end totals (for YTD)
        ye_revenue = sum_metric(self.year_end_data, 'total_income_cur')
        ye_cost = sum_metric(self.year_end_data, 'total_cost_cur')
        ye_gm = ye_revenue - ye_cost

        # Month-over-month changes
        mom_revenue = curr_revenue - prev_revenue
        mom_cost = curr_cost - prev_cost
        mom_gm = curr_gm - prev_gm
        mom_gm_pct = curr_gm_pct - prev_gm_pct
        mom_accrued = curr_accrued - prev_accrued
        mom_orderbook = curr_orderbook - prev_orderbook

        # Year-to-date
        ytd_revenue = curr_revenue - ye_revenue
        ytd_cost = curr_cost - ye_cost
        ytd_gm = ytd_revenue - ytd_cost

        return {
            'current': {
                'revenue': curr_revenue,
                'cost': curr_cost,
                'gross_margin': curr_gm,
                'gross_margin_pct': curr_gm_pct,
                'accrued': curr_accrued,
                'orderbook': curr_orderbook,
                'contingency': curr_contingency,
                'project_count': len(self.current_data),
            },
            'previous': {
                'revenue': prev_revenue,
                'cost': prev_cost,
                'gross_margin': prev_gm,
                'gross_margin_pct': prev_gm_pct,
                'accrued': prev_accrued,
                'orderbook': prev_orderbook,
                'project_count': len(self.previous_data),
            },
            'mom_change': {
                'revenue': mom_revenue,
                'cost': mom_cost,
                'gross_margin': mom_gm,
                'gross_margin_pct': mom_gm_pct,
                'accrued': mom_accrued,
                'orderbook': mom_orderbook,
            },
            'ytd': {
                'revenue': ytd_revenue,
                'cost': ytd_cost,
                'gross_margin': ytd_gm,
            }
        }

    def _find_new_projects(self) -> List[dict]:
        """Find projects that are new this month."""
        new_projects = []
        for proj_num, curr in self.current_data.items():
            if proj_num not in self.previous_data:
                new_projects.append({
                    'project_number': proj_num,
                    'project_name': curr.project_name or '',
                    'revenue': curr.total_income_cur or 0,
                    'margin_pct': curr.profit_margin_cur or 0,
                })
        return sorted(new_projects, key=lambda x: x['revenue'], reverse=True)

    def _find_completed_projects(self) -> List[dict]:
        """Find projects completed this month (PoC went to 100%)."""
        completed = []
        for proj_num, curr in self.current_data.items():
            prev = self.previous_data.get(proj_num)
            if prev:
                curr_poc = curr.completion_cur1 or 0
                prev_poc = prev.completion_cur1 or 0
                if curr_poc >= 0.99 and prev_poc < 0.99:
                    completed.append({
                        'project_number': proj_num,
                        'project_name': curr.project_name or '',
                        'revenue': curr.total_income_cur or 0,
                        'margin_pct': curr.profit_margin_cur or 0,
                    })
        return sorted(completed, key=lambda x: x['revenue'], reverse=True)

    def _find_top_revenue_changes(self) -> tuple:
        """Find projects with largest revenue changes."""
        changes = []
        for proj_num, curr in self.current_data.items():
            prev = self.previous_data.get(proj_num)
            if prev:
                curr_rev = curr.total_income_cur or 0
                prev_rev = prev.total_income_cur or 0
                change = curr_rev - prev_rev
                if abs(change) > self.SIGNIFICANT_REVENUE_CHANGE:
                    change_pct = change / prev_rev if prev_rev else 0
                    changes.append(ProjectHighlight(
                        project_number=proj_num,
                        project_name=curr.project_name or '',
                        metric='Revenue',
                        current_value=curr_rev,
                        previous_value=prev_rev,
                        change=change,
                        change_pct=change_pct,
                        comment=f"Revenue {'increased' if change > 0 else 'decreased'} by {self._format_amount(abs(change))}"
                    ))

        # Sort and split into increases and decreases
        increases = sorted([c for c in changes if c.change > 0], key=lambda x: x.change, reverse=True)[:5]
        decreases = sorted([c for c in changes if c.change < 0], key=lambda x: x.change)[:5]

        return increases, decreases

    def _find_margin_changes(self) -> List[ProjectHighlight]:
        """Find projects with significant margin changes."""
        changes = []
        for proj_num, curr in self.current_data.items():
            prev = self.previous_data.get(proj_num)
            if prev:
                curr_margin = curr.profit_margin_cur or 0
                prev_margin = prev.profit_margin_cur or 0
                change = curr_margin - prev_margin
                if abs(change) > self.SIGNIFICANT_MARGIN_CHANGE:
                    changes.append(ProjectHighlight(
                        project_number=proj_num,
                        project_name=curr.project_name or '',
                        metric='Gross Margin',
                        current_value=curr_margin,
                        previous_value=prev_margin,
                        change=change,
                        change_pct=change,
                        comment=f"Margin {'improved' if change > 0 else 'declined'} by {abs(change)*100:.1f} pp"
                    ))

        return sorted(changes, key=lambda x: abs(x.change), reverse=True)[:5]

    def _generate_revenue_commentary(self, summary: dict) -> CommentarySection:
        """Generate revenue section commentary."""
        section = CommentarySection(
            title="Revenue Performance",
            icon="bi-cash-stack",
            metrics={
                'current': summary['current']['revenue'],
                'previous': summary['previous']['revenue'],
                'change': summary['mom_change']['revenue'],
                'ytd': summary['ytd']['revenue'],
            }
        )

        mom_change = summary['mom_change']['revenue']
        mom_pct = mom_change / summary['previous']['revenue'] if summary['previous']['revenue'] else 0

        # Generate bullets
        if mom_change > 0:
            section.bullets.append(
                f"Total revenue increased by {self._format_amount(mom_change)} ({mom_pct*100:.1f}%) month-over-month"
            )
        elif mom_change < 0:
            section.bullets.append(
                f"Total revenue decreased by {self._format_amount(abs(mom_change))} ({abs(mom_pct)*100:.1f}%) month-over-month"
            )
        else:
            section.bullets.append("Revenue remained flat month-over-month")

        ytd_rev = summary['ytd']['revenue']
        if ytd_rev > 0:
            section.bullets.append(f"Year-to-date revenue recognition: {self._format_amount(ytd_rev)}")

        return section

    def _generate_margin_commentary(self, summary: dict) -> CommentarySection:
        """Generate margin section commentary."""
        section = CommentarySection(
            title="Gross Margin Analysis",
            icon="bi-percent",
            metrics={
                'current_pct': summary['current']['gross_margin_pct'],
                'previous_pct': summary['previous']['gross_margin_pct'],
                'change_pct': summary['mom_change']['gross_margin_pct'],
                'current_amount': summary['current']['gross_margin'],
            }
        )

        change_pp = summary['mom_change']['gross_margin_pct'] * 100

        if change_pp > 0.5:
            section.bullets.append(f"Gross margin improved by {change_pp:.1f} percentage points")
        elif change_pp < -0.5:
            section.bullets.append(f"Gross margin declined by {abs(change_pp):.1f} percentage points")
        else:
            section.bullets.append("Gross margin remained stable")

        section.bullets.append(
            f"Current portfolio margin: {summary['current']['gross_margin_pct']*100:.1f}%"
        )

        return section

    def _generate_orderbook_commentary(self, summary: dict) -> CommentarySection:
        """Generate order book section commentary."""
        section = CommentarySection(
            title="Order Book & Backlog",
            icon="bi-box-seam",
            metrics={
                'current': summary['current']['orderbook'],
                'previous': summary['previous']['orderbook'],
                'change': summary['mom_change']['orderbook'],
            }
        )

        change = summary['mom_change']['orderbook']

        if change > self.SIGNIFICANT_ORDERBOOK_CHANGE:
            section.bullets.append(f"Order book increased by {self._format_amount(change)}")
        elif change < -self.SIGNIFICANT_ORDERBOOK_CHANGE:
            section.bullets.append(f"Order book decreased by {self._format_amount(abs(change))} due to revenue recognition")
        else:
            section.bullets.append("Order book remained relatively stable")

        section.bullets.append(f"Current backlog: {self._format_amount(summary['current']['orderbook'])}")

        return section

    def _generate_project_commentary(self, new_projects: list, completed: list, summary: dict) -> CommentarySection:
        """Generate project activity section commentary."""
        section = CommentarySection(
            title="Project Activity",
            icon="bi-folder",
            metrics={
                'current_count': summary['current']['project_count'],
                'previous_count': summary['previous']['project_count'],
                'new_count': len(new_projects),
                'completed_count': len(completed),
            }
        )

        if new_projects:
            section.bullets.append(f"{len(new_projects)} new project(s) added this month")

        if completed:
            section.bullets.append(f"{len(completed)} project(s) reached 100% completion")

        count_change = summary['current']['project_count'] - summary['previous']['project_count']
        if count_change != 0:
            section.bullets.append(
                f"Active project count {'increased' if count_change > 0 else 'decreased'} "
                f"from {summary['previous']['project_count']} to {summary['current']['project_count']}"
            )

        return section

    def _generate_risk_commentary(self, summary: dict) -> CommentarySection:
        """Generate risk and contingency section commentary."""
        section = CommentarySection(
            title="Risk & Contingency",
            icon="bi-shield-exclamation",
            metrics={
                'contingency': summary['current']['contingency'],
                'accrued': summary['current']['accrued'],
                'accrued_change': summary['mom_change']['accrued'],
            }
        )

        accrued_change = summary['mom_change']['accrued']
        if accrued_change > 0:
            section.bullets.append(f"Accrued income increased by {self._format_amount(accrued_change)}")
        elif accrued_change < 0:
            section.bullets.append(f"Accrued income decreased by {self._format_amount(abs(accrued_change))}")

        contingency = summary['current']['contingency']
        if contingency > 0:
            section.bullets.append(f"Total contingency reserves: {self._format_amount(contingency)}")

        return section

    def generate(self) -> MonthlyCommentary:
        """Generate complete monthly commentary."""
        summary = self._calculate_summary()
        new_projects = self._find_new_projects()
        completed_projects = self._find_completed_projects()
        top_increases, top_decreases = self._find_top_revenue_changes()
        margin_changes = self._find_margin_changes()

        commentary = MonthlyCommentary(
            current_date=self.current_date,
            previous_date=self.previous_date,
            year_end_date=self.year_end_date or '',
            summary=summary,
            revenue_section=self._generate_revenue_commentary(summary),
            margin_section=self._generate_margin_commentary(summary),
            orderbook_section=self._generate_orderbook_commentary(summary),
            project_section=self._generate_project_commentary(new_projects, completed_projects, summary),
            risk_section=self._generate_risk_commentary(summary),
            top_revenue_increases=top_increases,
            top_revenue_decreases=top_decreases,
            top_margin_changes=margin_changes,
            new_projects=new_projects[:5],
            completed_projects=completed_projects[:5],
        )

        return commentary
