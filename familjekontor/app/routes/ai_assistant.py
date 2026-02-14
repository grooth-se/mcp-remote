"""AI Assistant routes — chat interface, query endpoint, admin status."""

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, jsonify,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.utils.ai_client import get_ollama_status, is_ollama_available
from app.services import ai_service
from app.services.report_service import get_profit_and_loss, get_balance_sheet

ai_bp = Blueprint('ai', __name__)


def _get_company_context():
    """Build financial context dict for the active company."""
    company_id = session.get('active_company_id')
    if not company_id:
        return None

    company = db.session.get(Company, company_id)
    if not company:
        return None

    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()

    if not fy:
        return {'company_name': company.name}

    data = {'company_name': company.name, 'fiscal_year': fy.year}

    try:
        pnl = get_profit_and_loss(company_id, fy.id)
        data['revenue'] = pnl.get('sections', {}).get('Nettoomsättning', {}).get('total', 0)
        data['net_income'] = pnl.get('result_before_tax', 0)
        data['expenses'] = abs(pnl.get('operating_result', 0) - data['revenue'])
    except Exception:
        pass

    try:
        bs = get_balance_sheet(company_id, fy.id)
        data['total_assets'] = bs.get('total_assets', 0)
        data['equity'] = bs.get('sections', {}).get('Eget kapital', {}).get('total', 0)
    except Exception:
        pass

    return data


# ---------------------------------------------------------------------------
# Chat Interface
# ---------------------------------------------------------------------------

@ai_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('dashboard.index'))

    status = get_ollama_status()
    return render_template('ai/index.html', ai_status=status)


@ai_bp.route('/query', methods=['POST'])
@login_required
def query():
    """AJAX endpoint for natural language financial queries."""
    data = request.get_json(silent=True) or {}
    question = data.get('query', '').strip()

    if not question:
        return jsonify({'answer': 'Skriv en fråga.', 'query_type': 'empty'})

    company_data = _get_company_context()

    result = ai_service.interpret_financial_query(question, company_data)
    return jsonify(result)


@ai_bp.route('/suggest-account', methods=['POST'])
@login_required
def suggest_account():
    """AJAX endpoint for account suggestions on bank transactions."""
    data = request.get_json(silent=True) or {}
    description = data.get('description', '')
    amount = data.get('amount')

    suggestion = ai_service.suggest_account(description, amount=amount)
    if suggestion:
        return jsonify(suggestion)
    return jsonify({'error': 'Ingen förslag kunde genereras'}), 404


@ai_bp.route('/analyze-invoice', methods=['POST'])
@login_required
def analyze_invoice():
    """AJAX endpoint for invoice text analysis."""
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'Ingen text att analysera'}), 400

    result = ai_service.analyze_invoice_text(text)
    if result:
        return jsonify(result)
    return jsonify({'error': 'Kunde inte analysera fakturatexten'}), 422


# ---------------------------------------------------------------------------
# Admin Status
# ---------------------------------------------------------------------------

@ai_bp.route('/status')
@login_required
def status():
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('ai.index'))

    status = get_ollama_status()
    tesseract_available = False
    try:
        from app.utils.ocr import is_tesseract_available
        tesseract_available = is_tesseract_available()
    except Exception:
        pass

    return render_template('ai/status.html',
                           ai_status=status,
                           tesseract_available=tesseract_available)
