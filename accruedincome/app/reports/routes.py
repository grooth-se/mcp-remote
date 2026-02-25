"""Reports blueprint routes."""

import os
import json
import urllib.request
import urllib.error
import pandas as pd
from flask import render_template, request, current_app, send_file, flash, redirect, url_for
from . import reports_bp
from app.models import FactProjectMonthly, UploadSession
from .services.excel_export import export_project_report, export_financial_statements, export_management_reports
from .services.financial_reports import FinancialReportGenerator
from .services.project_reports import ProjectReportGenerator
from .services.chart_generator import generate_project_charts, generate_single_chart
from .services.commentary_generator import CommentaryGenerator


def _load_verlista_df(session):
    """Load verlista DataFrame from file or MG5 integration API.

    Returns a DataFrame with columns expected by FinancialReportGenerator,
    or None if unavailable.
    """
    files = json.loads(session.files_json)

    # Excel-based session: read from file
    verlista_path = files.get('verlista')
    if verlista_path and os.path.exists(verlista_path):
        return pd.read_excel(verlista_path, engine='openpyxl')

    # Integration session: fetch from MG5 API (paginated)
    if files.get('source') == 'integration':
        base_url = current_app.config.get(
            'MG5_INTEGRATION_URL', 'http://mg5integration:5001')
        all_items = []
        page = 1
        while True:
            url = f'{base_url}/api/verifications?per_page=1000&page={page}'
            req = urllib.request.Request(url)
            req.add_header('Accept', 'application/json')
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read())
            except (urllib.error.URLError, Exception):
                break

            items = data.get('items', [])
            if not items:
                break
            all_items.extend(items)
            total_pages = data.get('pages', 1)
            if page >= total_pages:
                break
            page += 1

        if not all_items:
            return None

        rows = []
        for v in all_items:
            rows.append({
                'Konto': v.get('account'),
                'Debet': v.get('debit', 0) or 0,
                'Kredit': v.get('credit', 0) or 0,
                'datum': v.get('date'),
            })
        return pd.DataFrame(rows)

    return None


@reports_bp.route('/')
def index():
    """Report selection page with closing date filter."""
    closing_date = request.args.get('closing_date')
    closing_dates = FactProjectMonthly.get_closing_dates()

    if not closing_date and closing_dates:
        closing_date = closing_dates[0]

    projects = []
    totals = {}
    if closing_date:
        projects = FactProjectMonthly.get_by_closing_date(closing_date)
        totals = {
            'total_income': sum(p.total_income_cur or 0 for p in projects),
            'total_cost': sum(p.total_cost_cur or 0 for p in projects),
            'total_profit': sum(p.project_profit or 0 for p in projects),
            'total_accrued': sum(p.accrued_income_cur or 0 for p in projects),
            'total_contingency': sum(p.contingency_cur or 0 for p in projects),
            'project_count': len(projects),
        }

    return render_template('reports/index.html',
                          closing_dates=closing_dates,
                          selected_date=closing_date,
                          projects=projects,
                          totals=totals)


@reports_bp.route('/project/<closing_date>')
def project_report(closing_date):
    """Project revenue report."""
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    return render_template('reports/project.html',
                          closing_date=closing_date,
                          projects=projects)


@reports_bp.route('/orderbook/<closing_date>')
def orderbook_report(closing_date):
    """Order book report - remaining contract values."""
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    # Filter to projects with remaining value
    active_projects = [p for p in projects if (p.remaining_income or 0) > 0]

    totals = {
        'total_remaining_income': sum(p.remaining_income or 0 for p in active_projects),
        'total_remaining_cost': sum(p.remaining_cost or 0 for p in active_projects),
    }

    return render_template('reports/orderbook.html',
                          closing_date=closing_date,
                          projects=active_projects,
                          totals=totals)


@reports_bp.route('/profit/<closing_date>')
def profit_report(closing_date):
    """Profit and change report."""
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    return render_template('reports/profit.html',
                          closing_date=closing_date,
                          projects=projects)


@reports_bp.route('/booking/<closing_date>')
def booking_diff(closing_date):
    """Booking differences table."""
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    # Calculate booking entries needed
    total_accrued = sum(p.accrued_income_cur or 0 for p in projects)
    total_contingency = sum(p.contingency_cur or 0 for p in projects)
    net_booking = total_accrued - total_contingency

    return render_template('reports/booking.html',
                          closing_date=closing_date,
                          projects=projects,
                          total_accrued=total_accrued,
                          total_contingency=total_contingency,
                          net_booking=net_booking)


@reports_bp.route('/charts')
def charts():
    """Project progress charts."""
    closing_dates = FactProjectMonthly.get_closing_dates()
    closing_date = request.args.get('closing_date')

    if not closing_date and closing_dates:
        closing_date = closing_dates[0]

    projects = []
    if closing_date:
        projects = FactProjectMonthly.get_by_closing_date(closing_date)

    # Check which charts exist
    charts_folder = current_app.config['CHARTS_FOLDER']
    chart_files = {}
    for p in projects:
        chart_path = os.path.join(charts_folder, f'{p.project_number}.png')
        if os.path.exists(chart_path):
            chart_files[p.project_number] = True

    return render_template('reports/charts.html',
                          closing_dates=closing_dates,
                          selected_date=closing_date,
                          projects=projects,
                          chart_files=chart_files)


@reports_bp.route('/chart/<project_number>')
def chart_image(project_number):
    """Serve project chart image."""
    charts_folder = current_app.config['CHARTS_FOLDER']
    chart_path = os.path.join(charts_folder, f'{project_number}.png')

    if os.path.exists(chart_path):
        return send_file(chart_path, mimetype='image/png')
    else:
        # Try to generate the chart on-demand
        output_folder = str(current_app.config['OUTPUT_FOLDER'])
        result = generate_single_chart(project_number, output_folder)
        if result and os.path.exists(result):
            return send_file(result, mimetype='image/png')
        return 'Chart not found', 404


@reports_bp.route('/charts/regenerate', methods=['POST'])
def regenerate_charts():
    """Regenerate all project charts from database historical data."""
    output_folder = str(current_app.config['OUTPUT_FOLDER'])

    try:
        generated = generate_project_charts(output_folder)
        flash(f'Successfully generated {len(generated)} project charts.', 'success')
    except Exception as e:
        flash(f'Error generating charts: {str(e)}', 'error')

    return redirect(url_for('reports.charts'))


@reports_bp.route('/financial')
def financial():
    """Financial reports page - P&L and Balance Sheet."""
    # Get available upload sessions with verlista files
    sessions = UploadSession.query\
        .filter(UploadSession.status.in_(['validated', 'calculated', 'stored']))\
        .order_by(UploadSession.created_at.desc())\
        .limit(10).all()

    return render_template('reports/financial.html', sessions=sessions)


@reports_bp.route('/financial/generate', methods=['POST'])
def financial_generate():
    """Generate P&L and Balance Sheet from verlista."""
    session_id = request.form.get('session_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    closing_date = request.form.get('closing_date')

    session = UploadSession.query.filter_by(session_id=session_id).first()
    if not session:
        flash('Upload session not found.', 'error')
        return redirect(url_for('reports.financial'))

    try:
        verlista_df = _load_verlista_df(session)
        if verlista_df is None or verlista_df.empty:
            flash('Verlista data not available.', 'error')
            return redirect(url_for('reports.financial'))

        # Generate reports
        generator = FinancialReportGenerator(verlista_df)
        pnl_data = generator.generate_pnl_report(start_date, end_date)
        bs_data = generator.generate_balance_sheet(closing_date)

        return render_template('reports/financial_result.html',
                              pnl_data=pnl_data,
                              bs_data=bs_data,
                              session_id=session_id,
                              start_date=start_date,
                              end_date=end_date,
                              closing_date=closing_date)

    except Exception as e:
        flash(f'Error generating reports: {str(e)}', 'error')
        return redirect(url_for('reports.financial'))


@reports_bp.route('/management')
def management():
    """Management reports page - Report1, Report2, Report3 style."""
    closing_dates = FactProjectMonthly.get_closing_dates()

    return render_template('reports/management.html',
                          closing_dates=closing_dates)


@reports_bp.route('/management/generate', methods=['POST'])
def management_generate():
    """Generate management reports (Report1, Report2, Report3)."""
    current_date = request.form.get('current_date')
    previous_date = request.form.get('previous_date')
    year_end_date = request.form.get('year_end_date')

    if not current_date:
        flash('Current date is required.', 'error')
        return redirect(url_for('reports.management'))

    try:
        generator = ProjectReportGenerator(
            current_date=current_date,
            previous_date=previous_date if previous_date else None,
            year_end_date=year_end_date if year_end_date else None
        )

        report1 = generator.generate_report1()
        report2 = generator.generate_report2()
        report3 = generator.generate_report3()
        summary = generator.generate_summary()

        # Calculate totals for Report1
        report1_totals = {
            'current_revenue': sum(r.current_revenue for r in report1),
            'current_cogs': sum(r.current_cogs for r in report1),
            'current_gm': sum(r.current_gm for r in report1),
            'ytd_revenue': sum(r.ytd_revenue for r in report1),
            'ytd_cogs': sum(r.ytd_cogs for r in report1),
            'ytd_gm': sum(r.ytd_gm for r in report1),
            'ptd_revenue': sum(r.ptd_revenue for r in report1),
            'ptd_cogs': sum(r.ptd_cogs for r in report1),
            'ptd_gm': sum(r.ptd_gm for r in report1),
        }

        # Calculate totals for Report2
        report2_totals = {
            'tcv_revenue': sum(r.tcv_revenue for r in report2),
            'cogs': sum(r.cogs for r in report2),
            'gm': sum(r.gm for r in report2),
            'contingency': sum(r.contingency for r in report2),
            'delta_revenue': sum(r.delta_revenue for r in report2),
            'delta_cogs': sum(r.delta_cogs for r in report2),
            'delta_gm': sum(r.delta_gm for r in report2),
        }

        # Calculate totals for Report3
        report3_totals = {
            'ob_order_backlog': sum(r.ob_order_backlog for r in report3),
            'order_intake': sum(r.order_intake for r in report3),
            'revenue': sum(r.revenue for r in report3),
            'eb_order_backlog': sum(r.eb_order_backlog for r in report3),
        }

        return render_template('reports/management_result.html',
                              current_date=current_date,
                              previous_date=previous_date,
                              year_end_date=year_end_date,
                              report1=report1,
                              report1_totals=report1_totals,
                              report2=report2,
                              report2_totals=report2_totals,
                              report3=report3,
                              report3_totals=report3_totals,
                              summary=summary)

    except Exception as e:
        flash(f'Error generating reports: {str(e)}', 'error')
        return redirect(url_for('reports.management'))


@reports_bp.route('/export/<closing_date>')
def export(closing_date):
    """Export project report to Excel."""
    excel_buffer = export_project_report(closing_date)

    filename = f'project_report_{closing_date}.xlsx'
    return send_file(
        excel_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route('/export/management', methods=['POST'])
def export_management():
    """Export management reports to Excel."""
    current_date = request.form.get('current_date')
    previous_date = request.form.get('previous_date')
    year_end_date = request.form.get('year_end_date')

    try:
        generator = ProjectReportGenerator(
            current_date=current_date,
            previous_date=previous_date if previous_date else None,
            year_end_date=year_end_date if year_end_date else None
        )

        excel_buffer = export_management_reports(generator)

        filename = f'management_reports_{current_date}.xlsx'
        return send_file(
            excel_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        flash(f'Error exporting: {str(e)}', 'error')
        return redirect(url_for('reports.management'))


@reports_bp.route('/export/financial', methods=['POST'])
def export_financial():
    """Export financial statements to Excel."""
    session_id = request.form.get('session_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    closing_date = request.form.get('closing_date')

    session = UploadSession.query.filter_by(session_id=session_id).first()
    if not session:
        flash('Session not found.', 'error')
        return redirect(url_for('reports.financial'))

    try:
        verlista_df = _load_verlista_df(session)
        if verlista_df is None or verlista_df.empty:
            flash('Verlista data not available.', 'error')
            return redirect(url_for('reports.financial'))

        generator = FinancialReportGenerator(verlista_df)

        pnl_data = generator.generate_pnl_report(start_date, end_date)
        bs_data = generator.generate_balance_sheet(closing_date)

        excel_buffer = export_financial_statements(pnl_data, bs_data)

        filename = f'financial_statements_{closing_date}.xlsx'
        return send_file(
            excel_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        flash(f'Error exporting: {str(e)}', 'error')
        return redirect(url_for('reports.financial'))


@reports_bp.route('/commentary')
def commentary():
    """Monthly report commentary page."""
    closing_dates = FactProjectMonthly.get_closing_dates()

    # Default selections
    current_date = closing_dates[0] if closing_dates else None
    previous_date = closing_dates[1] if len(closing_dates) > 1 else None

    # Find year end date (December of previous year)
    year_end_date = None
    if current_date:
        current_year = int(current_date[:4])
        for date in closing_dates:
            if date.startswith(f'{current_year - 1}-12'):
                year_end_date = date
                break

    return render_template('reports/commentary.html',
                          closing_dates=closing_dates,
                          default_current=current_date,
                          default_previous=previous_date,
                          default_year_end=year_end_date)


@reports_bp.route('/commentary/generate', methods=['POST'])
def commentary_generate():
    """Generate monthly report commentary."""
    current_date = request.form.get('current_date')
    previous_date = request.form.get('previous_date')
    year_end_date = request.form.get('year_end_date')

    if not current_date or not previous_date:
        flash('Current and previous dates are required.', 'error')
        return redirect(url_for('reports.commentary'))

    try:
        generator = CommentaryGenerator(
            current_date=current_date,
            previous_date=previous_date,
            year_end_date=year_end_date if year_end_date else None
        )

        commentary = generator.generate()

        return render_template('reports/commentary_result.html',
                              commentary=commentary)

    except Exception as e:
        flash(f'Error generating commentary: {str(e)}', 'error')
        return redirect(url_for('reports.commentary'))
