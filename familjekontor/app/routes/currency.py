from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required

from app.models.exchange_rate import ExchangeRate
from app.forms.currency import ExchangeRateForm, FetchRatesForm
from app.services.exchange_rate_service import (
    get_rate, save_manual_rate, fetch_rates_for_range, RIKSBANKEN_SERIES,
)

currency_bp = Blueprint('currency', __name__)


@currency_bp.route('/rates')
@login_required
def rates():
    """List recent exchange rates."""
    page = request.args.get('page', 1, type=int)
    rates_query = ExchangeRate.query.order_by(
        ExchangeRate.rate_date.desc(), ExchangeRate.currency_code
    ).paginate(page=page, per_page=50, error_out=False)

    form = ExchangeRateForm()
    fetch_form = FetchRatesForm()

    return render_template('currency/rates.html',
                           rates=rates_query, form=form, fetch_form=fetch_form)


@currency_bp.route('/rates/new', methods=['POST'])
@login_required
def new_rate():
    """Save a manually entered exchange rate."""
    form = ExchangeRateForm()
    if form.validate_on_submit():
        try:
            save_manual_rate(
                currency_code=form.currency_code.data,
                rate_date=form.rate_date.data,
                rate=form.rate.data,
            )
            flash(f'Kurs sparad: {form.currency_code.data} {form.rate_date.data} = {form.rate.data} SEK', 'success')
        except Exception as e:
            flash(f'Kunde inte spara kurs: {e}', 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')

    return redirect(url_for('currency.rates'))


@currency_bp.route('/rates/fetch', methods=['POST'])
@login_required
def fetch_rates():
    """Fetch rates from Riksbanken for a date range."""
    fetch_form = FetchRatesForm()
    if fetch_form.validate_on_submit():
        start = fetch_form.start_date.data
        end = fetch_form.end_date.data
        currency = fetch_form.currency_code.data

        total_fetched = 0
        currencies = list(RIKSBANKEN_SERIES.keys()) if currency == 'ALL' else [currency]

        for curr in currencies:
            try:
                count = fetch_rates_for_range(curr, start, end)
                total_fetched += count
            except Exception as e:
                flash(f'Fel vid hämtning av {curr}: {e}', 'warning')

        flash(f'Hämtade {total_fetched} kurser från Riksbanken.', 'success')
    else:
        for field, errors in fetch_form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')

    return redirect(url_for('currency.rates'))


@currency_bp.route('/api/rate/<currency_code>/<rate_date>')
@login_required
def api_get_rate(currency_code, rate_date):
    """JSON endpoint for AJAX auto-fill in invoice forms."""
    try:
        rate_date_parsed = date.fromisoformat(rate_date)
        rate = get_rate(currency_code, rate_date_parsed)
        return jsonify({'rate': str(rate), 'source': 'riksbanken'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
