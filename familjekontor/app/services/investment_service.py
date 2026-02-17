"""Investment/portfolio service: portfolios, holdings, transactions, Nordnet CSV."""

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.investment import (
    InvestmentPortfolio, InvestmentHolding, InvestmentTransaction,
)
from app.models.accounting import FiscalYear, Account
from app.models.audit import AuditLog
from app.services.accounting_service import create_verification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_account(company_id, account_number, name, account_type):
    """Get or create a BAS account."""
    account = Account.query.filter_by(
        company_id=company_id, account_number=account_number
    ).first()
    if not account:
        account = Account(
            company_id=company_id, account_number=account_number,
            name=name, account_type=account_type, active=True,
        )
        db.session.add(account)
        db.session.flush()
    return account


# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------

def create_portfolio(company_id, data, created_by=None):
    """Create an investment portfolio."""
    portfolio = InvestmentPortfolio(
        company_id=company_id,
        name=data['name'],
        portfolio_type=data.get('portfolio_type', 'aktiedepå'),
        broker=data.get('broker'),
        account_number=data.get('account_number'),
        currency=data.get('currency', 'SEK'),
        ledger_account=data.get('ledger_account'),
    )
    db.session.add(portfolio)

    audit = AuditLog(
        company_id=company_id, user_id=created_by,
        action='create', entity_type='investment_portfolio', entity_id=0,
        new_values={'name': portfolio.name, 'broker': portfolio.broker},
    )
    db.session.add(audit)
    db.session.commit()

    audit.entity_id = portfolio.id
    db.session.commit()
    return portfolio


def get_portfolios(company_id, active_only=True):
    """List investment portfolios."""
    q = InvestmentPortfolio.query.filter_by(company_id=company_id)
    if active_only:
        q = q.filter_by(active=True)
    return q.order_by(InvestmentPortfolio.name).all()


def get_portfolio(portfolio_id):
    """Get a single portfolio."""
    return db.session.get(InvestmentPortfolio, portfolio_id)


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

def _get_or_create_holding(portfolio, company_id, data):
    """Find existing holding by name/ISIN or create new."""
    isin = data.get('isin')
    name = data['name']

    holding = None
    if isin:
        holding = InvestmentHolding.query.filter_by(
            portfolio_id=portfolio.id, isin=isin
        ).first()
    if not holding:
        holding = InvestmentHolding.query.filter_by(
            portfolio_id=portfolio.id, name=name
        ).first()

    if not holding:
        holding = InvestmentHolding(
            portfolio_id=portfolio.id,
            company_id=company_id,
            isin=isin,
            name=name,
            ticker=data.get('ticker'),
            instrument_type=data.get('instrument_type', 'aktie'),
            currency=data.get('currency', 'SEK'),
            quantity=0,
            average_cost=0,
            total_cost=0,
            org_number=data.get('org_number'),
            ownership_pct=Decimal(str(data['ownership_pct'])) if data.get('ownership_pct') else None,
            interest_rate=Decimal(str(data['interest_rate'])) if data.get('interest_rate') else None,
            maturity_date=data.get('maturity_date'),
            face_value=Decimal(str(data['face_value'])) if data.get('face_value') else None,
        )
        db.session.add(holding)
        db.session.flush()

    return holding


def get_holding(holding_id):
    """Get a single holding."""
    return db.session.get(InvestmentHolding, holding_id)


def get_holding_transactions(holding_id):
    """Get transactions for a holding."""
    return InvestmentTransaction.query.filter_by(
        holding_id=holding_id
    ).order_by(InvestmentTransaction.transaction_date.desc()).all()


def update_holding_price(holding_id, price, price_date=None):
    """Update current market price for a holding."""
    holding = db.session.get(InvestmentHolding, holding_id)
    if not holding:
        raise ValueError('Innehav hittades inte')

    holding.current_price = Decimal(str(price))
    holding.last_price_date = price_date or date.today()
    holding.current_value = holding.current_price * holding.quantity
    holding.unrealized_gain = holding.current_value - holding.total_cost
    db.session.commit()
    return holding


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def create_transaction(portfolio_id, data, created_by=None):
    """Create an investment transaction.

    Handles: köp, sälj, utdelning, ränta, avgift, insättning, uttag.
    Updates holding quantity/cost and creates accounting verification.
    """
    portfolio = db.session.get(InvestmentPortfolio, portfolio_id)
    if not portfolio:
        raise ValueError('Portfölj hittades inte')

    company_id = portfolio.company_id
    tx_type = data['transaction_type']
    amount = Decimal(str(data['amount']))
    exchange_rate = Decimal(str(data.get('exchange_rate', 1)))
    amount_sek = amount * exchange_rate
    commission = Decimal(str(data.get('commission', 0)))
    quantity = Decimal(str(data['quantity'])) if data.get('quantity') else None
    price_per_unit = Decimal(str(data['price_per_unit'])) if data.get('price_per_unit') else None

    holding = None
    realized_gain = None

    # For buy/sell/dividend on specific instruments, manage holding
    if tx_type in ('kop', 'salj', 'utdelning', 'utlan', 'amortering', 'kupong') and data.get('name'):
        holding = _get_or_create_holding(portfolio, company_id, data)

    if tx_type == 'kop' and holding and quantity:
        # Update average cost (weighted average)
        old_total_cost = holding.total_cost or Decimal('0')
        old_qty = holding.quantity or Decimal('0')
        new_cost = amount_sek + commission
        new_qty = old_qty + quantity
        holding.total_cost = old_total_cost + new_cost
        holding.quantity = new_qty
        holding.average_cost = holding.total_cost / new_qty if new_qty > 0 else 0
        holding.active = True

    elif tx_type == 'salj' and holding and quantity:
        # Calculate realized gain using average cost
        old_qty = holding.quantity or Decimal('0')
        if quantity > old_qty:
            raise ValueError(f'Kan inte sälja {quantity} st, bara {old_qty} i innehavet')
        cost_basis = holding.average_cost * quantity
        proceeds = amount_sek - commission
        realized_gain = proceeds - cost_basis

        holding.quantity = old_qty - quantity
        holding.total_cost = holding.average_cost * holding.quantity
        if holding.quantity <= 0:
            holding.quantity = 0
            holding.total_cost = 0
            holding.active = False

    # --- Loan: utlan creates holding with face_value/remaining_principal ---
    elif tx_type == 'utlan' and holding:
        holding.instrument_type = data.get('instrument_type', 'lan')
        holding.face_value = amount_sek
        holding.remaining_principal = amount_sek
        holding.quantity = Decimal('1')
        holding.total_cost = amount_sek
        holding.active = True

    # --- Amortization: reduce remaining_principal ---
    elif tx_type == 'amortering' and holding:
        remaining = holding.remaining_principal or Decimal('0')
        if amount_sek > remaining:
            raise ValueError(
                f'Amortering {amount_sek} överskrider kvarstående kapital {remaining}'
            )
        holding.remaining_principal = remaining - amount_sek
        holding.total_cost = holding.remaining_principal
        if holding.remaining_principal <= 0:
            holding.remaining_principal = Decimal('0')
            holding.total_cost = Decimal('0')
            holding.active = False

    # --- Coupon: income from bond, no holding quantity change ---
    elif tx_type == 'kupong' and holding:
        pass  # No holding changes, just transaction + verification

    # Create transaction record
    tx = InvestmentTransaction(
        portfolio_id=portfolio_id,
        holding_id=holding.id if holding else None,
        company_id=company_id,
        transaction_date=data['transaction_date'],
        transaction_type=tx_type,
        quantity=quantity,
        price_per_unit=price_per_unit,
        amount=amount,
        currency=data.get('currency', 'SEK'),
        exchange_rate=exchange_rate,
        amount_sek=amount_sek,
        commission=commission,
        realized_gain=realized_gain,
        import_batch=data.get('import_batch'),
        note=data.get('note'),
    )
    db.session.add(tx)
    db.session.flush()

    # Update holding market value if we have a price
    if holding and holding.quantity > 0 and price_per_unit:
        holding.current_price = price_per_unit
        holding.last_price_date = data['transaction_date']
        holding.current_value = price_per_unit * holding.quantity
        holding.unrealized_gain = holding.current_value - holding.total_cost

    # Create accounting verification
    fiscal_year_id = data.get('fiscal_year_id')
    if fiscal_year_id:
        verification = _create_investment_verification(
            company_id, fiscal_year_id, portfolio, tx, holding,
            realized_gain, created_by,
        )
        if verification:
            tx.verification_id = verification.id

    db.session.commit()
    return tx


def _create_investment_verification(company_id, fiscal_year_id, portfolio,
                                     tx, holding, realized_gain, created_by):
    """Create verification for an investment transaction."""
    ledger_acct_num = portfolio.ledger_account or '1350'
    acct_asset = _ensure_account(company_id, ledger_acct_num,
                                  'Andelar och värdepapper', 'asset')
    acct_bank = _ensure_account(company_id, '1930', 'Företagskonto', 'asset')

    rows = []
    tx_type = tx.transaction_type
    amount_sek = float(tx.amount_sek)
    commission = float(tx.commission)

    if tx_type == 'kop':
        # Debit asset, Credit bank. Commission part of cost.
        total = amount_sek + commission
        rows.append({'account_id': acct_asset.id, 'debit': total, 'credit': 0})
        rows.append({'account_id': acct_bank.id, 'debit': 0, 'credit': total})
        desc = f'Köp {tx.quantity} st {holding.name if holding else ""}'

    elif tx_type == 'salj':
        # Debit bank (proceeds), Credit asset (cost basis), gain/loss
        proceeds = amount_sek - commission
        cost_basis = float(realized_gain or 0) + proceeds if realized_gain is not None else proceeds
        # Cost basis = avg_cost * qty
        if holding:
            cost_basis = float(holding.average_cost * tx.quantity) if tx.quantity else proceeds

        rows.append({'account_id': acct_bank.id, 'debit': proceeds, 'credit': 0})
        rows.append({'account_id': acct_asset.id, 'debit': 0, 'credit': cost_basis})

        if commission > 0:
            acct_fee = _ensure_account(company_id, '6570', 'Bankkostnader', 'expense')
            rows.append({'account_id': acct_fee.id, 'debit': commission, 'credit': 0})

        if realized_gain is not None:
            rg = float(realized_gain)
            if rg > 0:
                acct_gain = _ensure_account(company_id, '8220',
                                            'Resultat vid försäljning av värdepapper', 'revenue')
                rows.append({'account_id': acct_gain.id, 'debit': 0, 'credit': rg})
            elif rg < 0:
                acct_loss = _ensure_account(company_id, '8230',
                                            'Förlust vid försäljning av värdepapper', 'expense')
                rows.append({'account_id': acct_loss.id, 'debit': abs(rg), 'credit': 0})

        desc = f'Sälj {tx.quantity} st {holding.name if holding else ""}'

    elif tx_type == 'utdelning':
        acct_div = _ensure_account(company_id, '8210', 'Utdelning på aktier', 'revenue')
        rows.append({'account_id': acct_bank.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_div.id, 'debit': 0, 'credit': amount_sek})
        desc = f'Utdelning {holding.name if holding else ""}'

    elif tx_type == 'ranta':
        acct_int = _ensure_account(company_id, '8310', 'Ränteintäkter', 'revenue')
        rows.append({'account_id': acct_bank.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_int.id, 'debit': 0, 'credit': amount_sek})
        desc = 'Ränteintäkt värdepapperskonto'

    elif tx_type == 'avgift':
        acct_fee = _ensure_account(company_id, '6570', 'Bankkostnader', 'expense')
        rows.append({'account_id': acct_fee.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_bank.id, 'debit': 0, 'credit': amount_sek})
        desc = 'Avgift värdepapperskonto'

    elif tx_type == 'insattning':
        rows.append({'account_id': acct_asset.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_bank.id, 'debit': 0, 'credit': amount_sek})
        desc = 'Insättning värdepapperskonto'

    elif tx_type == 'uttag':
        rows.append({'account_id': acct_bank.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_asset.id, 'debit': 0, 'credit': amount_sek})
        desc = 'Uttag värdepapperskonto'

    elif tx_type == 'utlan':
        acct_loan = _ensure_account(company_id, ledger_acct_num if ledger_acct_num != '1350' else '1385',
                                     'Långfristiga lånefordringar', 'asset')
        rows.append({'account_id': acct_loan.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_bank.id, 'debit': 0, 'credit': amount_sek})
        desc = f'Utlåning {holding.name if holding else ""}'

    elif tx_type == 'amortering':
        acct_loan = _ensure_account(company_id, ledger_acct_num if ledger_acct_num != '1350' else '1385',
                                     'Långfristiga lånefordringar', 'asset')
        rows.append({'account_id': acct_bank.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_loan.id, 'debit': 0, 'credit': amount_sek})
        desc = f'Amortering {holding.name if holding else ""}'

    elif tx_type == 'kupong':
        acct_int = _ensure_account(company_id, '8310', 'Ränteintäkter', 'revenue')
        rows.append({'account_id': acct_bank.id, 'debit': amount_sek, 'credit': 0})
        rows.append({'account_id': acct_int.id, 'debit': 0, 'credit': amount_sek})
        desc = f'Kupongbetalning {holding.name if holding else ""}'

    else:
        return None

    if not rows:
        return None

    return create_verification(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        verification_date=tx.transaction_date,
        description=desc.strip(),
        rows=rows,
        verification_type='investment',
        created_by=created_by,
        source='investment',
    )


# ---------------------------------------------------------------------------
# Portfolio Summary & Reports
# ---------------------------------------------------------------------------

def get_portfolio_summary(company_id):
    """Get summary across all portfolios: total value, cost, gain."""
    portfolios = get_portfolios(company_id)

    summary = {
        'portfolios': [],
        'total_cost': Decimal('0'),
        'total_value': Decimal('0'),
        'total_unrealized': Decimal('0'),
    }

    for p in portfolios:
        active_holdings = [h for h in p.holdings if h.active]
        p_cost = Decimal('0')
        p_value = Decimal('0')
        p_unrealized = Decimal('0')
        for h in active_holdings:
            if h.is_loan_type:
                val = h.remaining_principal or h.face_value or h.total_cost or 0
                p_cost += val
                p_value += val
            else:
                p_cost += h.total_cost or 0
                p_value += h.current_value or h.total_cost or 0
                p_unrealized += h.unrealized_gain or 0

        summary['portfolios'].append({
            'portfolio': p,
            'holdings_count': len(active_holdings),
            'total_cost': p_cost,
            'total_value': p_value,
            'unrealized_gain': p_unrealized,
        })
        summary['total_cost'] += p_cost
        summary['total_value'] += p_value
        summary['total_unrealized'] += p_unrealized

    return summary


def get_dividend_income_summary(company_id, fiscal_year_id):
    """Get dividend income grouped by holding for a fiscal year."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return []

    txs = InvestmentTransaction.query.filter(
        InvestmentTransaction.company_id == company_id,
        InvestmentTransaction.transaction_type == 'utdelning',
        InvestmentTransaction.transaction_date >= fy.start_date,
        InvestmentTransaction.transaction_date <= fy.end_date,
    ).all()

    by_holding = {}
    for tx in txs:
        key = tx.holding_id or 'other'
        if key not in by_holding:
            name = tx.holding.name if tx.holding else 'Övriga'
            by_holding[key] = {'name': name, 'total': Decimal('0'), 'count': 0}
        by_holding[key]['total'] += tx.amount_sek
        by_holding[key]['count'] += 1

    result = sorted(by_holding.values(), key=lambda x: x['total'], reverse=True)
    return result


def get_interest_income_summary(company_id, fiscal_year_id):
    """Get interest/coupon income grouped by holding for a fiscal year."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return []

    txs = InvestmentTransaction.query.filter(
        InvestmentTransaction.company_id == company_id,
        InvestmentTransaction.transaction_type.in_(['ranta', 'kupong']),
        InvestmentTransaction.transaction_date >= fy.start_date,
        InvestmentTransaction.transaction_date <= fy.end_date,
    ).all()

    by_holding = {}
    for tx in txs:
        key = tx.holding_id or 'other'
        if key not in by_holding:
            name = tx.holding.name if tx.holding else 'Övriga'
            by_holding[key] = {'name': name, 'total': Decimal('0'), 'count': 0}
        by_holding[key]['total'] += tx.amount_sek
        by_holding[key]['count'] += 1

    return sorted(by_holding.values(), key=lambda x: x['total'], reverse=True)


def update_holding_metadata(holding_id, data):
    """Update extended metadata on a holding (org_number, ownership, rates, etc.)."""
    holding = db.session.get(InvestmentHolding, holding_id)
    if not holding:
        raise ValueError('Innehav hittades inte')

    if 'org_number' in data:
        holding.org_number = data['org_number'] or None
    if 'ownership_pct' in data:
        holding.ownership_pct = Decimal(str(data['ownership_pct'])) if data['ownership_pct'] else None
    if 'interest_rate' in data:
        holding.interest_rate = Decimal(str(data['interest_rate'])) if data['interest_rate'] else None
    if 'maturity_date' in data:
        holding.maturity_date = data['maturity_date']
    if 'face_value' in data:
        holding.face_value = Decimal(str(data['face_value'])) if data['face_value'] else None

    db.session.commit()
    return holding


# ---------------------------------------------------------------------------
# Nordnet CSV Import
# ---------------------------------------------------------------------------

NORDNET_TYPE_MAP = {
    'KÖPT': 'kop',
    'KÖP': 'kop',
    'SÅLT': 'salj',
    'SÄLJ': 'salj',
    'UTDELNING': 'utdelning',
    'RÄNTOR': 'ranta',
    'RÄNTA': 'ranta',
    'AVGIFT': 'avgift',
    'PRELIMINÄRSKATT': 'avgift',
    'INSÄTTNING': 'insattning',
    'UTTAG': 'uttag',
}


def parse_nordnet_csv(file_storage):
    """Parse Nordnet CSV export.

    Nordnet uses semicolon delimiter, Latin-1 encoding, Swedish headers.
    Returns list of dicts ready for import.
    """
    raw = file_storage.read()

    # Try Latin-1 first (Nordnet default), then UTF-8
    for encoding in ('latin-1', 'utf-8', 'cp1252'):
        try:
            text = raw.decode(encoding)
            break
        except (UnicodeDecodeError, AttributeError):
            continue
    else:
        raise ValueError('Kunde inte avkoda CSV-filen')

    reader = csv.DictReader(io.StringIO(text), delimiter=';')

    transactions = []
    for row in reader:
        # Normalize column names (strip whitespace, BOM)
        row = {k.strip().lstrip('\ufeff'): v.strip() for k, v in row.items() if k}

        # Find relevant columns (Nordnet header names)
        tx_date = _parse_nordnet_date(row.get('Bokföringsdag') or row.get('Handelsdag') or '')
        tx_type_raw = (row.get('Transaktionstyp') or row.get('Transaktionstext') or '').upper()
        tx_type = NORDNET_TYPE_MAP.get(tx_type_raw)

        if not tx_date or not tx_type:
            continue

        name = row.get('Värdepapper') or row.get('ISIN') or ''
        isin = row.get('ISIN') or ''
        quantity = _parse_nordnet_number(row.get('Antal') or '0')
        price = _parse_nordnet_number(row.get('Kurs') or '0')
        amount = _parse_nordnet_number(row.get('Belopp') or '0')
        commission = abs(_parse_nordnet_number(row.get('Courtage') or row.get('Avgifter') or '0'))
        currency = row.get('Valuta') or 'SEK'

        if not name and not amount:
            continue

        transactions.append({
            'transaction_date': tx_date,
            'transaction_type': tx_type,
            'name': name,
            'isin': isin if len(isin) == 12 else None,
            'quantity': abs(quantity) if quantity else None,
            'price_per_unit': abs(price) if price else None,
            'amount': abs(amount),
            'commission': commission,
            'currency': currency,
            'instrument_type': 'aktie',
        })

    return transactions


def _parse_nordnet_date(s):
    """Parse date from Nordnet format YYYY-MM-DD."""
    s = s.strip()
    if not s:
        return None
    try:
        parts = s.split('-')
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def _parse_nordnet_number(s):
    """Parse Nordnet number: uses comma as decimal, optional spaces as thousands."""
    s = s.strip().replace('\xa0', '').replace(' ', '')
    if not s or s == '-':
        return Decimal('0')
    s = s.replace(',', '.')
    try:
        return Decimal(s)
    except Exception:
        return Decimal('0')


def import_nordnet_transactions(portfolio_id, transactions, fiscal_year_id=None,
                                 created_by=None):
    """Bulk import parsed Nordnet transactions with dedup."""
    portfolio = db.session.get(InvestmentPortfolio, portfolio_id)
    if not portfolio:
        raise ValueError('Portfölj hittades inte')

    batch_id = str(uuid.uuid4())[:8]
    imported = 0
    skipped = 0

    for tx_data in transactions:
        # Dedup: check if same date+type+amount+name already exists
        existing = InvestmentTransaction.query.filter_by(
            portfolio_id=portfolio_id,
            transaction_date=tx_data['transaction_date'],
            transaction_type=tx_data['transaction_type'],
            amount=tx_data['amount'],
        ).first()

        if existing and existing.holding and existing.holding.name == tx_data.get('name', ''):
            skipped += 1
            continue

        tx_data['import_batch'] = batch_id
        tx_data['fiscal_year_id'] = fiscal_year_id
        create_transaction(portfolio_id, tx_data, created_by=created_by)
        imported += 1

    return {'imported': imported, 'skipped': skipped, 'batch_id': batch_id}
