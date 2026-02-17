from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.investment import (
    InvestmentPortfolio, InvestmentHolding, InvestmentTransaction,
    INSTRUMENT_TYPE_LABELS, TRANSACTION_TYPE_LABELS,
)
from app.forms.investment import (
    PortfolioForm, TransactionForm, ImportForm, PriceUpdateForm, HoldingEditForm,
)
from app.services.investment_service import (
    create_portfolio, get_portfolios, get_portfolio,
    get_holding, get_holding_transactions, update_holding_price,
    update_holding_metadata,
    create_transaction, get_portfolio_summary,
    get_dividend_income_summary, get_interest_income_summary,
    parse_nordnet_csv, import_nordnet_transactions,
)

investments_bp = Blueprint('investments', __name__)


def _get_active_context():
    company_id = session.get('active_company_id')
    if not company_id:
        return None, None, None
    from app.models.company import Company
    company = db.session.get(Company, company_id)
    active_fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()
    return company_id, company, active_fy


# ---------------------------------------------------------------------------
# Portfolio Overview
# ---------------------------------------------------------------------------

@investments_bp.route('/')
@login_required
def index():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    summary = get_portfolio_summary(company_id)
    return render_template('investments/index.html', summary=summary,
                           instrument_labels=INSTRUMENT_TYPE_LABELS)


@investments_bp.route('/portfolios/new', methods=['GET', 'POST'])
@login_required
def portfolio_new():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('investments.index'))

    form = PortfolioForm()
    if form.validate_on_submit():
        data = {
            'name': form.name.data,
            'portfolio_type': form.portfolio_type.data,
            'broker': form.broker.data,
            'account_number': form.account_number.data,
            'currency': form.currency.data,
            'ledger_account': form.ledger_account.data,
        }
        try:
            p = create_portfolio(company_id, data, created_by=current_user.id)
            flash(f'Portfölj "{p.name}" skapad.', 'success')
            return redirect(url_for('investments.portfolio_view', portfolio_id=p.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('investments/portfolio_form.html', form=form)


@investments_bp.route('/portfolios/<int:portfolio_id>')
@login_required
def portfolio_view(portfolio_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    portfolio = get_portfolio(portfolio_id)
    if not portfolio or portfolio.company_id != company_id:
        flash('Portfölj hittades inte.', 'danger')
        return redirect(url_for('investments.index'))

    active_holdings = [h for h in portfolio.holdings if h.active]
    inactive_holdings = [h for h in portfolio.holdings if not h.active]

    total_cost = sum(float(h.total_cost or 0) for h in active_holdings)
    total_value = sum(float(h.current_value or h.total_cost or 0) for h in active_holdings)

    return render_template('investments/portfolio_view.html',
                           portfolio=portfolio,
                           active_holdings=active_holdings,
                           inactive_holdings=inactive_holdings,
                           total_cost=total_cost,
                           total_value=total_value)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@investments_bp.route('/portfolios/<int:portfolio_id>/transactions/new', methods=['GET', 'POST'])
@login_required
def transaction_new(portfolio_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('investments.index'))

    portfolio = get_portfolio(portfolio_id)
    if not portfolio or portfolio.company_id != company_id:
        flash('Portfölj hittades inte.', 'danger')
        return redirect(url_for('investments.index'))

    form = TransactionForm()
    if form.validate_on_submit():
        data = {
            'transaction_type': form.transaction_type.data,
            'transaction_date': form.transaction_date.data,
            'name': form.name.data,
            'isin': form.isin.data,
            'ticker': form.ticker.data,
            'instrument_type': form.instrument_type.data or 'aktie',
            'quantity': form.quantity.data,
            'price_per_unit': form.price_per_unit.data,
            'amount': form.amount.data,
            'commission': form.commission.data or 0,
            'currency': form.currency.data or 'SEK',
            'exchange_rate': form.exchange_rate.data or 1,
            'note': form.note.data,
            'fiscal_year_id': active_fy.id if active_fy else None,
            'org_number': form.org_number.data,
            'ownership_pct': form.ownership_pct.data,
            'interest_rate': form.interest_rate.data,
            'maturity_date': form.maturity_date.data,
            'face_value': form.face_value.data,
        }
        try:
            tx = create_transaction(portfolio_id, data, created_by=current_user.id)
            flash(f'Transaktion registrerad: {tx.transaction_type_label}.', 'success')
            return redirect(url_for('investments.portfolio_view', portfolio_id=portfolio_id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('investments/transaction_form.html', form=form,
                           portfolio=portfolio)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@investments_bp.route('/portfolios/<int:portfolio_id>/import', methods=['GET', 'POST'])
@login_required
def import_csv(portfolio_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('investments.index'))

    portfolio = get_portfolio(portfolio_id)
    if not portfolio or portfolio.company_id != company_id:
        flash('Portfölj hittades inte.', 'danger')
        return redirect(url_for('investments.index'))

    form = ImportForm()
    preview = None

    if form.validate_on_submit():
        action = request.form.get('action', 'preview')

        if action == 'preview':
            try:
                preview = parse_nordnet_csv(form.csv_file.data)
                if not preview:
                    flash('Inga transaktioner hittades i filen.', 'warning')
            except ValueError as e:
                flash(str(e), 'danger')
        elif action == 'confirm':
            # Re-parse (file not persisted between requests)
            try:
                transactions = parse_nordnet_csv(form.csv_file.data)
                result = import_nordnet_transactions(
                    portfolio_id, transactions,
                    fiscal_year_id=active_fy.id if active_fy else None,
                    created_by=current_user.id,
                )
                flash(f'Importerade {result["imported"]} transaktioner '
                      f'({result["skipped"]} redan befintliga).', 'success')
                return redirect(url_for('investments.portfolio_view',
                                        portfolio_id=portfolio_id))
            except ValueError as e:
                flash(str(e), 'danger')

    return render_template('investments/import.html', form=form,
                           portfolio=portfolio, preview=preview,
                           tx_labels=TRANSACTION_TYPE_LABELS)


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

@investments_bp.route('/holdings/<int:holding_id>')
@login_required
def holding_view(holding_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    holding = get_holding(holding_id)
    if not holding or holding.company_id != company_id:
        flash('Innehav hittades inte.', 'danger')
        return redirect(url_for('investments.index'))

    transactions = get_holding_transactions(holding_id)
    return render_template('investments/holding_view.html',
                           holding=holding, transactions=transactions)


@investments_bp.route('/holdings/<int:holding_id>/edit', methods=['GET', 'POST'])
@login_required
def holding_edit(holding_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('investments.index'))

    holding = get_holding(holding_id)
    if not holding or holding.company_id != company_id:
        flash('Innehav hittades inte.', 'danger')
        return redirect(url_for('investments.index'))

    form = HoldingEditForm(obj=holding)
    if form.validate_on_submit():
        try:
            update_holding_metadata(holding.id, {
                'org_number': form.org_number.data,
                'ownership_pct': form.ownership_pct.data,
                'interest_rate': form.interest_rate.data,
                'maturity_date': form.maturity_date.data,
                'face_value': form.face_value.data,
            })
            flash(f'Detaljer uppdaterade för {holding.name}.', 'success')
            return redirect(url_for('investments.holding_view', holding_id=holding.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('investments/holding_edit.html', form=form, holding=holding)


@investments_bp.route('/holdings/<int:holding_id>/price', methods=['GET', 'POST'])
@login_required
def price_update(holding_id):
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('investments.index'))

    holding = get_holding(holding_id)
    if not holding or holding.company_id != company_id:
        flash('Innehav hittades inte.', 'danger')
        return redirect(url_for('investments.index'))

    form = PriceUpdateForm()
    if form.validate_on_submit():
        try:
            update_holding_price(holding.id, form.current_price.data,
                                  form.price_date.data)
            flash(f'Pris uppdaterat för {holding.name}.', 'success')
            return redirect(url_for('investments.holding_view', holding_id=holding.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('investments/price_update.html', form=form, holding=holding)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@investments_bp.route('/reports')
@login_required
def reports():
    company_id, company, active_fy = _get_active_context()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    summary = get_portfolio_summary(company_id)
    dividend_summary = []
    interest_summary = []
    if active_fy:
        dividend_summary = get_dividend_income_summary(company_id, active_fy.id)
        interest_summary = get_interest_income_summary(company_id, active_fy.id)

    return render_template('investments/reports.html',
                           summary=summary, dividend_summary=dividend_summary,
                           interest_summary=interest_summary,
                           active_fy=active_fy)
