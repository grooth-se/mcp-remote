"""Asset management service: fixed asset register, depreciation, disposal."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from app.extensions import db
from app.models.asset import FixedAsset, DepreciationRun, DepreciationEntry, ASSET_CATEGORY_DEFAULTS, ASSET_CATEGORY_LABELS
from app.models.accounting import FiscalYear, Account, Verification
from app.models.audit import AuditLog
from app.services.accounting_service import create_verification


def _next_asset_number(company_id):
    """Generate next asset number like AT-2025-001."""
    year = date.today().year
    prefix = f'AT-{year}-'
    last = db.session.query(func.max(FixedAsset.asset_number)).filter(
        FixedAsset.company_id == company_id,
        FixedAsset.asset_number.like(f'{prefix}%')
    ).scalar()
    if last:
        try:
            seq = int(last.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:03d}'


def _ensure_account(company_id, account_number, name, account_type):
    """Get or create a BAS account."""
    account = Account.query.filter_by(
        company_id=company_id, account_number=account_number
    ).first()
    if not account:
        account = Account(
            company_id=company_id,
            account_number=account_number,
            name=name,
            account_type=account_type,
            active=True,
        )
        db.session.add(account)
        db.session.flush()
    return account


def create_asset(company_id, data, created_by=None):
    """Create a new fixed asset.

    data: dict with name, asset_category, purchase_date, purchase_amount, etc.
    """
    category = data['asset_category']
    defaults = ASSET_CATEGORY_DEFAULTS.get(category)
    if not defaults:
        raise ValueError(f'Okänd tillgångskategori: {category}')

    asset = FixedAsset(
        company_id=company_id,
        name=data['name'],
        asset_number=_next_asset_number(company_id),
        description=data.get('description'),
        asset_category=category,
        purchase_date=data['purchase_date'],
        purchase_amount=Decimal(str(data['purchase_amount'])),
        supplier_name=data.get('supplier_name'),
        invoice_reference=data.get('invoice_reference'),
        depreciation_method=data.get('depreciation_method', 'straight_line'),
        useful_life_months=data.get('useful_life_months') or defaults[3],
        residual_value=Decimal(str(data.get('residual_value', 0) or 0)),
        depreciation_start=data.get('depreciation_start') or data['purchase_date'],
        asset_account=data.get('asset_account') or defaults[0],
        depreciation_account=data.get('depreciation_account') or defaults[1],
        expense_account=data.get('expense_account') or defaults[2],
        status='active',
        created_by=created_by,
    )
    db.session.add(asset)
    db.session.flush()

    audit = AuditLog(
        company_id=company_id,
        user_id=created_by,
        action='create',
        entity_type='fixed_asset',
        entity_id=asset.id,
        new_values={'name': asset.name, 'amount': float(asset.purchase_amount)},
    )
    db.session.add(audit)
    db.session.commit()
    return asset


def update_asset(asset_id, data):
    """Update editable fields on a fixed asset."""
    asset = db.session.get(FixedAsset, asset_id)
    if not asset:
        raise ValueError('Tillgång hittades inte')

    for field in ('name', 'description', 'supplier_name', 'invoice_reference',
                  'depreciation_method', 'useful_life_months', 'residual_value',
                  'depreciation_start', 'asset_account', 'depreciation_account',
                  'expense_account'):
        if field in data:
            val = data[field]
            if field in ('residual_value',) and val is not None:
                val = Decimal(str(val))
            setattr(asset, field, val)

    db.session.commit()
    return asset


def get_assets(company_id, status=None, category=None):
    """List fixed assets with optional filters."""
    q = FixedAsset.query.filter_by(company_id=company_id)
    if status:
        q = q.filter_by(status=status)
    if category:
        q = q.filter_by(asset_category=category)
    return q.order_by(FixedAsset.asset_number).all()


def get_asset(asset_id):
    """Get a single asset."""
    return db.session.get(FixedAsset, asset_id)


def get_accumulated_depreciation(asset_id):
    """Calculate total accumulated depreciation from posted entries."""
    result = db.session.query(
        func.coalesce(func.sum(DepreciationEntry.period_amount), 0)
    ).join(DepreciationRun).filter(
        DepreciationEntry.asset_id == asset_id,
        DepreciationRun.status == 'posted',
    ).scalar()
    return Decimal(str(result))


def calculate_monthly_depreciation(asset):
    """Calculate monthly depreciation for an asset.

    Straight-line: (purchase_amount - residual_value) / useful_life_months
    Declining balance: (book_value * 2 / useful_life_months), capped at book_value - residual_value
    """
    if asset.status != 'active':
        return Decimal('0')

    purchase = Decimal(str(asset.purchase_amount))
    residual = Decimal(str(asset.residual_value or 0))
    months = asset.useful_life_months
    accumulated = get_accumulated_depreciation(asset.id)
    book_value = purchase - accumulated

    if book_value <= residual:
        return Decimal('0')

    if asset.depreciation_method == 'declining_balance':
        # Double declining balance
        rate = Decimal('2') / Decimal(str(months))
        monthly = (book_value * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # Don't depreciate below residual
        max_dep = book_value - residual
        return min(monthly, max_dep)
    else:
        # Straight-line
        depreciable = purchase - residual
        monthly = (depreciable / Decimal(str(months))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # Don't exceed remaining book value minus residual
        max_dep = book_value - residual
        return min(monthly, max_dep)


def generate_depreciation_run(company_id, fiscal_year_id, period_date, created_by=None):
    """Generate a pending depreciation run for all active assets."""
    assets = FixedAsset.query.filter_by(
        company_id=company_id, status='active'
    ).all()

    run = DepreciationRun(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        period_date=period_date,
        status='pending',
        total_amount=0,
        created_by=created_by,
    )
    db.session.add(run)
    db.session.flush()

    total = Decimal('0')
    for asset in assets:
        # Only depreciate if started
        if asset.depreciation_start > period_date:
            continue

        monthly = calculate_monthly_depreciation(asset)
        if monthly <= 0:
            continue

        accumulated = get_accumulated_depreciation(asset.id)
        entry = DepreciationEntry(
            depreciation_run_id=run.id,
            asset_id=asset.id,
            period_amount=monthly,
            accumulated_before=accumulated,
            accumulated_after=accumulated + monthly,
            book_value_after=Decimal(str(asset.purchase_amount)) - accumulated - monthly,
        )
        db.session.add(entry)
        total += monthly

    run.total_amount = total
    db.session.commit()
    return run


def post_depreciation_run(run_id, created_by=None):
    """Post a pending depreciation run: create accounting verification."""
    run = db.session.get(DepreciationRun, run_id)
    if not run:
        raise ValueError('Avskrivningskörning hittades inte')
    if run.status == 'posted':
        raise ValueError('Avskrivningskörningen är redan bokförd')

    entries = DepreciationEntry.query.filter_by(depreciation_run_id=run.id).all()
    if not entries:
        raise ValueError('Inga avskrivningsposter att bokföra')

    # Group entries by expense_account + depreciation_account pair
    rows_by_account = {}
    for entry in entries:
        asset = entry.asset
        key = (asset.expense_account, asset.depreciation_account)
        if key not in rows_by_account:
            rows_by_account[key] = Decimal('0')
        rows_by_account[key] += entry.period_amount

    ver_rows = []
    for (expense_acct, depr_acct), amount in rows_by_account.items():
        exp_account = _ensure_account(
            run.company_id, expense_acct,
            f'Avskrivningar ({expense_acct})', 'expense'
        )
        acc_account = _ensure_account(
            run.company_id, depr_acct,
            f'Ackumulerade avskrivningar ({depr_acct})', 'asset'
        )
        ver_rows.append({
            'account_id': exp_account.id,
            'debit': float(amount),
            'credit': 0,
        })
        ver_rows.append({
            'account_id': acc_account.id,
            'debit': 0,
            'credit': float(amount),
        })

    verification = create_verification(
        company_id=run.company_id,
        fiscal_year_id=run.fiscal_year_id,
        verification_date=run.period_date,
        description=f'Avskrivningar {run.period_date.strftime("%Y-%m")}',
        rows=ver_rows,
        verification_type='depreciation',
        created_by=created_by,
        source='depreciation',
    )

    run.status = 'posted'
    run.verification_id = verification.id

    # Check if any assets are now fully depreciated
    for entry in entries:
        if entry.book_value_after <= Decimal(str(entry.asset.residual_value or 0)):
            entry.asset.status = 'fully_depreciated'

    audit = AuditLog(
        company_id=run.company_id,
        user_id=created_by,
        action='create',
        entity_type='depreciation_run',
        entity_id=run.id,
        new_values={'period': str(run.period_date), 'total': float(run.total_amount)},
    )
    db.session.add(audit)
    db.session.commit()
    return run


def dispose_asset(asset_id, disposal_date, disposal_amount, fiscal_year_id, created_by=None):
    """Dispose of an asset. Books gain/loss to 3973/7973."""
    asset = db.session.get(FixedAsset, asset_id)
    if not asset:
        raise ValueError('Tillgång hittades inte')
    if asset.status == 'disposed':
        raise ValueError('Tillgången är redan avyttrad')

    accumulated = get_accumulated_depreciation(asset.id)
    book_value = Decimal(str(asset.purchase_amount)) - accumulated
    disposal_amt = Decimal(str(disposal_amount))
    gain_loss = disposal_amt - book_value

    # Build verification rows
    asset_acct = _ensure_account(
        asset.company_id, asset.asset_account,
        f'Tillgångskonto ({asset.asset_account})', 'asset'
    )
    depr_acct = _ensure_account(
        asset.company_id, asset.depreciation_account,
        f'Ack avskrivningar ({asset.depreciation_account})', 'asset'
    )
    bank_acct = _ensure_account(
        asset.company_id, '1930', 'Företagskonto', 'asset'
    )

    ver_rows = []

    # Debit bank for disposal proceeds
    if disposal_amt > 0:
        ver_rows.append({
            'account_id': bank_acct.id,
            'debit': float(disposal_amt),
            'credit': 0,
        })

    # Credit asset account (remove original cost)
    ver_rows.append({
        'account_id': asset_acct.id,
        'debit': 0,
        'credit': float(asset.purchase_amount),
    })

    # Debit accumulated depreciation (remove)
    if accumulated > 0:
        ver_rows.append({
            'account_id': depr_acct.id,
            'debit': float(accumulated),
            'credit': 0,
        })

    # Gain or loss
    if gain_loss > 0:
        gain_acct = _ensure_account(
            asset.company_id, '3973', 'Vinst vid avyttring av maskiner/inventarier', 'revenue'
        )
        ver_rows.append({
            'account_id': gain_acct.id,
            'debit': 0,
            'credit': float(gain_loss),
        })
    elif gain_loss < 0:
        loss_acct = _ensure_account(
            asset.company_id, '7973', 'Förlust vid avyttring av maskiner/inventarier', 'expense'
        )
        ver_rows.append({
            'account_id': loss_acct.id,
            'debit': float(abs(gain_loss)),
            'credit': 0,
        })

    verification = create_verification(
        company_id=asset.company_id,
        fiscal_year_id=fiscal_year_id,
        verification_date=disposal_date,
        description=f'Avyttring: {asset.name} ({asset.asset_number})',
        rows=ver_rows,
        verification_type='disposal',
        created_by=created_by,
        source='asset_disposal',
    )

    asset.status = 'disposed'
    asset.disposed_date = disposal_date
    asset.disposal_amount = disposal_amt
    asset.disposal_verification_id = verification.id

    audit = AuditLog(
        company_id=asset.company_id,
        user_id=created_by,
        action='update',
        entity_type='fixed_asset',
        entity_id=asset.id,
        new_values={'action': 'disposed', 'gain_loss': float(gain_loss)},
    )
    db.session.add(audit)
    db.session.commit()
    return asset


def get_depreciation_schedule(asset_id):
    """Generate full depreciation schedule for an asset.

    Returns list of dicts: month, depreciation, accumulated, book_value.
    """
    asset = db.session.get(FixedAsset, asset_id)
    if not asset:
        return []

    purchase = Decimal(str(asset.purchase_amount))
    residual = Decimal(str(asset.residual_value or 0))
    months = asset.useful_life_months
    start = asset.depreciation_start

    schedule = []
    accumulated = Decimal('0')
    book_value = purchase

    for i in range(months):
        month_num = start.month + i
        year = start.year + (month_num - 1) // 12
        month = ((month_num - 1) % 12) + 1

        if asset.depreciation_method == 'declining_balance':
            rate = Decimal('2') / Decimal(str(months))
            dep = (book_value * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            max_dep = book_value - residual
            dep = min(dep, max_dep)
        else:
            depreciable = purchase - residual
            dep = (depreciable / Decimal(str(months))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            max_dep = book_value - residual
            dep = min(dep, max_dep)

        if dep <= 0:
            break

        accumulated += dep
        book_value -= dep

        schedule.append({
            'month': f'{year}-{month:02d}',
            'depreciation': float(dep),
            'accumulated': float(accumulated),
            'book_value': float(book_value),
        })

        if book_value <= residual:
            break

    return schedule


def get_asset_note_data(company_id, fiscal_year_id):
    """Generate K2 asset note data by category.

    Returns dict: {category_label: {opening, purchases, disposals, depreciation, closing}}.
    """
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return {}

    assets = FixedAsset.query.filter_by(company_id=company_id).all()
    if not assets:
        return {}

    note = {}
    for category, label in ASSET_CATEGORY_LABELS.items():
        cat_assets = [a for a in assets if a.asset_category == category]
        if not cat_assets:
            continue

        opening = Decimal('0')
        purchases = Decimal('0')
        disposals = Decimal('0')
        depreciation = Decimal('0')

        for asset in cat_assets:
            purchase_amt = Decimal(str(asset.purchase_amount))

            # Opening: assets purchased before FY start
            if asset.purchase_date < fy.start_date:
                opening += purchase_amt
            elif asset.purchase_date <= fy.end_date:
                purchases += purchase_amt

            # Disposals during FY
            if asset.status == 'disposed' and asset.disposed_date:
                if fy.start_date <= asset.disposed_date <= fy.end_date:
                    disposals += purchase_amt

            # Depreciation during FY (from posted entries)
            dep_amount = db.session.query(
                func.coalesce(func.sum(DepreciationEntry.period_amount), 0)
            ).join(DepreciationRun).filter(
                DepreciationEntry.asset_id == asset.id,
                DepreciationRun.status == 'posted',
                DepreciationRun.fiscal_year_id == fiscal_year_id,
            ).scalar()
            depreciation += Decimal(str(dep_amount))

        closing = opening + purchases - disposals - depreciation

        if opening or purchases or disposals or depreciation:
            note[label] = {
                'opening': float(opening),
                'purchases': float(purchases),
                'disposals': float(disposals),
                'depreciation': float(depreciation),
                'closing': float(closing),
            }

    return note
