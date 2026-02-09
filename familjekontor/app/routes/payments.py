from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required
from app.services.payment_service import get_all_payments

payments_bp = Blueprint('payments', __name__)


@payments_bp.route('/')
@login_required
def overview():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    # Read filter params
    payment_type = request.args.get('type')
    if payment_type not in ('supplier', 'customer', 'tax'):
        payment_type = None

    from_date = None
    to_date = None
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    payments, summary = get_all_payments(
        company_id, from_date=from_date, to_date=to_date, payment_type=payment_type
    )

    return render_template(
        'payments/overview.html',
        payments=payments,
        summary=summary,
        active_type=payment_type or 'all',
        from_date=from_date_str,
        to_date=to_date_str,
    )
