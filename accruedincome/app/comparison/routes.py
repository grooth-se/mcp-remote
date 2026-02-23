"""Comparison blueprint routes - month-over-month analysis."""

from flask import (
    render_template, request, flash, redirect,
    url_for, send_file, session
)

from . import comparison_bp
from app.models import FactProjectMonthly
from app.reports.services.report_analysis import (
    compare_two_months,
    get_all_closing_dates
)
from app.reports.services.excel_export import export_comparison_to_excel


@comparison_bp.route('/')
def index():
    """Comparison page with date selection."""
    closing_dates = get_all_closing_dates()

    # Get selected dates from query params or session
    current_date = request.args.get('current_date')
    previous_date = request.args.get('previous_date')

    if not current_date and closing_dates:
        current_date = closing_dates[0] if len(closing_dates) > 0 else None
    if not previous_date and closing_dates:
        previous_date = closing_dates[1] if len(closing_dates) > 1 else None

    return render_template('comparison/index.html',
                          closing_dates=closing_dates,
                          current_date=current_date,
                          previous_date=previous_date)


@comparison_bp.route('/run', methods=['POST'])
def run():
    """Generate comparison between two periods."""
    current_date = request.form.get('current_date')
    previous_date = request.form.get('previous_date')

    if not current_date or not previous_date:
        flash('Please select both current and previous closing dates.', 'warning')
        return redirect(url_for('comparison.index'))

    if current_date == previous_date:
        flash('Please select different dates for comparison.', 'warning')
        return redirect(url_for('comparison.index'))

    # Generate comparison
    result = compare_two_months(current_date, previous_date)

    # Store in session for export
    session['comparison_current'] = current_date
    session['comparison_previous'] = previous_date

    # Convert DataFrame rows to list of dicts for template iteration
    rows = result['detail'].to_dict('records') if not result['detail'].empty else []

    return render_template('comparison/results.html',
                          result=result,
                          rows=rows,
                          current_date=current_date,
                          previous_date=previous_date)


@comparison_bp.route('/export')
def export():
    """Export comparison to Excel."""
    current_date = session.get('comparison_current')
    previous_date = session.get('comparison_previous')

    if not current_date or not previous_date:
        # Try from query params
        current_date = request.args.get('current_date')
        previous_date = request.args.get('previous_date')

    if not current_date or not previous_date:
        flash('No comparison data available. Please run comparison first.', 'warning')
        return redirect(url_for('comparison.index'))

    # Generate comparison data
    result = compare_two_months(current_date, previous_date)

    # Export to Excel
    excel_buffer = export_comparison_to_excel(result)

    filename = f'comparison_{current_date}_vs_{previous_date}.xlsx'
    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
