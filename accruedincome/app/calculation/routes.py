"""Calculation blueprint routes."""

import json
import os
import pickle
import pandas as pd
from flask import (
    render_template, request, jsonify, flash,
    redirect, url_for, current_app
)
from . import calculation_bp
from .services import AccruedIncomeCalculator
from app.extensions import db
from app.models import FactProjectMonthly, UploadSession


def _load_integration_dataframes(session):
    """Load pickled integration DataFrames for a session."""
    upload_folder = os.path.join(
        current_app.config['UPLOAD_FOLDER'], session.session_id
    )
    pickle_path = os.path.join(upload_folder, 'integration_data.pkl')
    with open(pickle_path, 'rb') as f:
        return pickle.load(f)


def _is_integration_session(session):
    """Check if upload session was loaded from MG5 integration."""
    try:
        files = json.loads(session.files_json)
        return files.get('source') == 'integration'
    except (json.JSONDecodeError, TypeError):
        return False


def _get_session_closing_date(session):
    """Get closing_date stored in the session metadata (from integration form)."""
    try:
        files = json.loads(session.files_json)
        return files.get('closing_date')
    except (json.JSONDecodeError, TypeError):
        return None


def _import_accrued_history(calculator, current_closing_date):
    """Import historical rows from Accuredhistory into FactProjectMonthly.

    Imports all historical closing dates that differ from the current one
    and don't already exist in the database.
    """
    hist_df = calculator.dataframes.get('Accuredhistory')
    if hist_df is None or hist_df.empty:
        return

    # Ensure closing is datetime for formatting
    hist_df = hist_df.copy()
    hist_df['closing'] = pd.to_datetime(hist_df['closing'], errors='coerce')

    # Get unique historical closing dates (excluding current)
    hist_dates = hist_df['closing'].dropna().dt.strftime('%Y-%m-%d').unique()
    existing_dates = set(FactProjectMonthly.get_closing_dates())

    for hist_date in hist_dates:
        if hist_date == current_closing_date:
            continue  # Already stored by the main loop
        if hist_date in existing_dates:
            continue  # Already in DB from a previous import

        date_rows = hist_df[
            hist_df['closing'].dt.strftime('%Y-%m-%d') == hist_date
        ]

        for _, row in date_rows.iterrows():
            proj_num = str(row.get('Projektnummer', ''))
            if not proj_num:
                continue

            def _fval(col, default=0):
                v = row.get(col, default)
                try:
                    return float(v) if pd.notna(v) else default
                except (ValueError, TypeError):
                    return default

            project = FactProjectMonthly(
                closing_date=hist_date,
                project_number=proj_num,
                project_name=str(row.get('Benamning', '') or ''),
                customer_name=str(row.get('Kundnamn', '') or ''),
                actual_cost_cur=_fval('actcost CUR'),
                actual_income_cur=_fval('actincome CUR'),
                accrued_income_cur=_fval('accured income CUR'),
                total_cost_cur=_fval('totalcost CUR'),
                total_income_cur=_fval('totalincome CUR'),
                contingency_cur=_fval('contingency CUR'),
                include_in_accrued=bool(row.get('incl', True)),
                contingency_factor=_fval('complex'),
                completion_cur=_fval('completion CUR'),
                completion_cur1=_fval('completion CUR1'),
                profit_margin_cur=_fval('profit margin CUR'),
                remaining_income=_fval('Remaining income'),
                remaining_cost=_fval('Remaining cost'),
                actual_income=_fval('act income'),
                actual_cost=_fval('act cost'),
            )
            db.session.add(project)


@calculation_bp.route('/')
def index():
    """Calculation setup page."""
    sessions = UploadSession.query\
        .filter(UploadSession.status.in_(['validated', 'uploaded']))\
        .order_by(UploadSession.created_at.desc())\
        .limit(10).all()
    return render_template('calculation/run.html', sessions=sessions)


@calculation_bp.route('/run', methods=['POST'])
def run():
    """Execute calculation (AJAX endpoint)."""
    session_id = request.form.get('session_id')
    closing_date_override = (
        request.form.get('closing_date', '').strip()
        or None
    )
    session = UploadSession.query.filter_by(session_id=session_id).first()

    if not session:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404

    # Fall back to closing_date stored in session metadata (integration form)
    if not closing_date_override:
        closing_date_override = _get_session_closing_date(session)

    output_folder = str(current_app.config['OUTPUT_FOLDER'])

    try:
        if _is_integration_session(session):
            dataframes = _load_integration_dataframes(session)
            calculator = AccruedIncomeCalculator({}, output_folder)
            result_df, closing_date = calculator.run(
                dataframes=dataframes, closing_date=closing_date_override)
        else:
            files = json.loads(session.files_json)
            calculator = AccruedIncomeCalculator(files, output_folder)
            result_df, closing_date = calculator.run(
                closing_date=closing_date_override)

        # Update session
        session.closing_date = closing_date
        session.result_count = len(result_df)
        session.status = 'calculated'
        db.session.commit()

        # Calculate summary
        total_accrued = float(result_df['accured income CUR'].sum())
        total_contingency = float(result_df['contingency CUR'].sum())

        return jsonify({
            'status': 'success',
            'closing_date': closing_date,
            'project_count': len(result_df),
            'total_accrued': total_accrued,
            'total_contingency': total_contingency
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@calculation_bp.route('/store', methods=['POST'])
def store():
    """Store calculation results to database."""
    session_id = request.form.get('session_id')
    closing_date_override = (
        request.form.get('closing_date', '').strip()
        or None
    )
    session = UploadSession.query.filter_by(session_id=session_id).first()

    if not session or session.status != 'calculated':
        flash('No calculated results to store', 'error')
        return redirect(url_for('calculation.index'))

    # Fall back to closing_date stored in session metadata (integration form)
    if not closing_date_override:
        closing_date_override = _get_session_closing_date(session)

    output_folder = str(current_app.config['OUTPUT_FOLDER'])

    try:
        # Re-run calculation to get DataFrame
        if _is_integration_session(session):
            dataframes = _load_integration_dataframes(session)
            calculator = AccruedIncomeCalculator({}, output_folder)
            result_df, closing_date = calculator.run(
                dataframes=dataframes, closing_date=closing_date_override)
        else:
            files = json.loads(session.files_json)
            calculator = AccruedIncomeCalculator(files, output_folder)
            result_df, closing_date = calculator.run(
                closing_date=closing_date_override)

        # Delete existing records for this closing date
        FactProjectMonthly.query.filter_by(closing_date=closing_date).delete()

        # Insert new records
        for idx, row in result_df.iterrows():
            project = FactProjectMonthly(
                closing_date=closing_date,
                project_number=str(idx),
                project_name=str(row.get('Benamning', '')),
                customer_name=str(row.get('Kundnamn', '')),

                # Original values
                expected_income=float(row.get('Forvan. intakt', 0) or 0),
                expected_cost=float(row.get('Forvan. kostnad', 0) or 0),
                executed_income=float(row.get('Utf., intakt', 0) or 0),
                executed_cost=float(row.get('Utf., kostnad', 0) or 0),

                # GL actuals
                actual_income=float(row.get('act income', 0) or 0),
                actual_cost=float(row.get('act cost', 0) or 0),
                cm_cost=float(row.get('CM cost', 0) or 0),

                # Revaluation
                remaining_cost=float(row.get('Remaining cost', 0) or 0),
                remaining_income=float(row.get('Remaining income', 0) or 0),
                remaining_income_val=float(row.get('Remaining income val.', 0) or 0),
                remaining_income_cur=float(row.get('Remaining income CUR', 0) or 0),

                # Milestones
                milestone_amount=float(row.get('Milestone', 0) or 0),
                milestone_cur=float(row.get('Milestone CUR', 0) or 0),

                # Basic metrics
                profit_margin=float(row.get('vinstmarg', 0) or 0),
                cost_factor=float(row.get('kostfakt', 0) or 0),
                completion_rate=float(row.get('fardiggrad', 0) or 0),
                accrued_income=float(row.get('accured income', 0) or 0),
                risk_amount=float(row.get('risk', 0) or 0),

                # Currency adjusted
                actual_income_cur=float(row.get('actincome CUR', 0) or 0),
                actual_cost_cur=float(row.get('actcost CUR', 0) or 0),
                total_income_cur=float(row.get('totalincome CUR', 0) or 0),
                total_cost_cur=float(row.get('totalcost CUR', 0) or 0),
                profit_margin_cur=float(row.get('profit margin CUR', 0) or 0),
                actual_cost_invoiced_cur=float(row.get('actcost invo CUR', 0) or 0),
                completion_cur=float(row.get('completion CUR', 0) or 0),
                completion_cur1=float(row.get('completion CUR1', 0) or 0),
                accrued_income_cur=float(row.get('accured income CUR', 0) or 0),
                contingency_cur=float(row.get('contingency CUR', 0) or 0),

                # Adjustments
                include_in_accrued=bool(row.get('incl', True)),
                contingency_factor=float(row.get('complex', 0) or 0),
                income_adjustment=float(row.get('incomeadj', 0) or 0),
                cost_calc_adjustment=float(row.get('costcalcadj', 0) or 0),
                purchase_adjustment=float(row.get('puradj', 0) or 0),

                # Variance
                project_profit=float(row.get('projloss', 0) or 0),
                diff_income=float(row.get('diffincome', 0) or 0),
                diff_cost=float(row.get('diffcost', 0) or 0),
            )
            db.session.add(project)

        # Import historical data from Accuredhistory into DB
        _import_accrued_history(calculator, closing_date)

        session.status = 'stored'
        db.session.commit()

        flash(f'Stored {len(result_df)} projects for {closing_date}', 'success')
        return redirect(url_for('reports.index', closing_date=closing_date))

    except Exception as e:
        db.session.rollback()
        flash(f'Error storing results: {str(e)}', 'error')
        return redirect(url_for('calculation.index'))


@calculation_bp.route('/results/<closing_date>')
def results(closing_date):
    """View calculation results for a closing date."""
    projects = FactProjectMonthly.get_by_closing_date(closing_date)

    if not projects:
        flash(f'No data found for {closing_date}', 'warning')
        return redirect(url_for('calculation.index'))

    # Calculate totals
    totals = {
        'total_income': sum(p.total_income_cur or 0 for p in projects),
        'total_cost': sum(p.total_cost_cur or 0 for p in projects),
        'total_accrued': sum(p.accrued_income_cur or 0 for p in projects),
        'total_contingency': sum(p.contingency_cur or 0 for p in projects),
    }

    return render_template('calculation/results.html',
                          closing_date=closing_date,
                          projects=projects,
                          totals=totals)
