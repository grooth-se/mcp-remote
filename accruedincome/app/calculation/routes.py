"""Calculation blueprint routes."""

import json
import os
import pickle
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
    session = UploadSession.query.filter_by(session_id=session_id).first()

    if not session:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404

    output_folder = str(current_app.config['OUTPUT_FOLDER'])

    try:
        if _is_integration_session(session):
            dataframes = _load_integration_dataframes(session)
            calculator = AccruedIncomeCalculator({}, output_folder)
            result_df, closing_date = calculator.run(dataframes=dataframes)
        else:
            files = json.loads(session.files_json)
            calculator = AccruedIncomeCalculator(files, output_folder)
            result_df, closing_date = calculator.run()

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
    session = UploadSession.query.filter_by(session_id=session_id).first()

    if not session or session.status != 'calculated':
        flash('No calculated results to store', 'error')
        return redirect(url_for('calculation.index'))

    output_folder = str(current_app.config['OUTPUT_FOLDER'])

    try:
        # Re-run calculation to get DataFrame
        if _is_integration_session(session):
            dataframes = _load_integration_dataframes(session)
            calculator = AccruedIncomeCalculator({}, output_folder)
            result_df, closing_date = calculator.run(dataframes=dataframes)
        else:
            files = json.loads(session.files_json)
            calculator = AccruedIncomeCalculator(files, output_folder)
            result_df, closing_date = calculator.run()

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
