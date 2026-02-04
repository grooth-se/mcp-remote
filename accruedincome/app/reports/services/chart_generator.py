"""Chart generation service for project progress charts.

Generates charts from historical data stored in the database.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from app.models import FactProjectMonthly


def generate_project_charts(output_folder: str, project_numbers: list = None):
    """Generate progress charts for projects from database historical data.

    Args:
        output_folder: Directory to save chart images
        project_numbers: Optional list of specific projects to generate charts for.
                        If None, generates for all projects.

    Returns:
        dict: {project_number: chart_path} for generated charts
    """
    # Create charts folder
    charts_folder = os.path.join(output_folder, 'charts')
    os.makedirs(charts_folder, exist_ok=True)

    # Get all historical data from database
    all_projects = FactProjectMonthly.query.order_by(
        FactProjectMonthly.project_number,
        FactProjectMonthly.closing_date
    ).all()

    # Convert to DataFrame
    data = []
    for p in all_projects:
        data.append({
            'project_number': p.project_number,
            'closing_date': p.closing_date,
            'actual_cost': p.actual_cost_cur or 0,
            'actual_income': p.actual_income_cur or 0,
            'accrued_income': p.accrued_income_cur or 0,
            'total_cost': p.total_cost_cur or 0,
            'total_income': p.total_income_cur or 0,
        })

    if not data:
        return {}

    df = pd.DataFrame(data)
    df['closing_date'] = pd.to_datetime(df['closing_date'])
    df['income_plus_accrued'] = df['actual_income'] + df['accrued_income']

    # Filter to specific projects if provided
    if project_numbers:
        df = df[df['project_number'].isin(project_numbers)]

    # Group by project
    grouped = df.groupby('project_number')
    unique_projects = df['project_number'].unique()

    generated = {}

    for proj in unique_projects:
        try:
            proj_data = grouped.get_group(proj).sort_values('closing_date')

            # Need at least 2 data points for a meaningful chart
            if len(proj_data) < 2:
                continue

            plt.figure(figsize=(10, 6))

            x = proj_data['closing_date']
            y1 = proj_data['actual_cost']
            y2 = proj_data['income_plus_accrued']
            y3 = proj_data['total_cost']
            y4 = proj_data['total_income']

            # Line styles as requested:
            # Actual cost: solid black line, no points
            # Income+Accrued: solid dark red line, no points
            # Total cost: dashed line, dark grey
            # Total income: dashed line, dark green
            plt.plot(x, y1, color='black', label='Actual Cost', linestyle='-', linewidth=1.5)
            plt.plot(x, y2, color='darkred', label='Income + Accrued', linestyle='-', linewidth=1.5)
            plt.plot(x, y3, color='dimgray', label='Total Cost', linestyle='--', linewidth=1.5)
            plt.plot(x, y4, color='darkgreen', label='Total Income', linestyle='--', linewidth=1.5)

            plt.legend(loc='best')
            plt.title(f'Project: {proj}')
            plt.xlabel('Closing Date')
            plt.ylabel('Amount (SEK)')
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            chart_path = os.path.join(charts_folder, f'{proj}.png')
            plt.savefig(chart_path, dpi=100)
            plt.close()

            generated[proj] = chart_path

        except Exception as e:
            plt.close()
            continue

    return generated


def generate_single_chart(project_number: str, output_folder: str) -> str:
    """Generate chart for a single project.

    Args:
        project_number: Project number to generate chart for
        output_folder: Directory to save chart image

    Returns:
        str: Path to generated chart, or None if generation failed
    """
    result = generate_project_charts(output_folder, [project_number])
    return result.get(project_number)
