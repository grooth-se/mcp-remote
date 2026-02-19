"""Data review service — summary, anomaly detection, and paginated drill-down."""

from datetime import date, datetime

from sqlalchemy import func, inspect as sa_inspect, or_, String, cast

from app.extensions import db
from app.models.accounting import Account, Verification
from app.models.projects import (
    Project, ProjectAdjustment, TimeTracking, CustomerOrderProjectMap,
)
from app.models.orders import CustomerOrder, PurchaseOrder, Quote, OrderIntake
from app.models.invoicing import InvoiceLog, ExchangeRate
from app.models.inventory import Article, MinimumStock

# Internal columns to hide from review UI
_HIDDEN_COLS = {'id', 'created_at', 'updated_at', 'source', 'import_batch_id'}

# Registry: key → (model, label, default_sort, required_fields, amount_fields, date_fields)
TABLE_REGISTRY = {
    'accounts': {
        'model': Account,
        'label': 'Accounts (Kontoplan)',
        'default_sort': 'account_number',
        'required': ['account_number'],
        'amounts': [],
        'dates': [],
    },
    'verifications': {
        'model': Verification,
        'label': 'Verifications (Verlista)',
        'default_sort': 'date',
        'required': ['verification_number', 'date', 'account'],
        'amounts': ['debit', 'credit'],
        'dates': ['date'],
    },
    'projects': {
        'model': Project,
        'label': 'Projects (Projektuppföljning)',
        'default_sort': 'project_number',
        'required': ['project_number'],
        'amounts': ['executed_cost', 'executed_income', 'expected_cost',
                     'expected_income', 'remaining_cost', 'remaining_income'],
        'dates': ['start_date', 'end_date'],
    },
    'project_adjustments': {
        'model': ProjectAdjustment,
        'label': 'Project Adjustments',
        'default_sort': 'project_number',
        'required': ['project_number'],
        'amounts': ['contingency', 'income_adjustment', 'cost_calc_adjustment',
                     'purchase_adjustment'],
        'dates': [],
    },
    'time_tracking': {
        'model': TimeTracking,
        'label': 'Time Tracking (Tiduppföljning)',
        'default_sort': 'project_number',
        'required': ['project_number'],
        'amounts': ['budget', 'actual_hours', 'expected_hours', 'remaining'],
        'dates': [],
    },
    'co_project_crossref': {
        'model': CustomerOrderProjectMap,
        'label': 'Order–Project Cross-ref',
        'default_sort': 'order_number',
        'required': ['order_number', 'project_number'],
        'amounts': [],
        'dates': [],
    },
    'customer_orders': {
        'model': CustomerOrder,
        'label': 'Customer Orders (Kundorder)',
        'default_sort': 'order_number',
        'required': ['order_number'],
        'amounts': ['remaining_amount', 'unit_price'],
        'dates': ['order_date'],
    },
    'purchase_orders': {
        'model': PurchaseOrder,
        'label': 'Purchase Orders (Inköpsorder)',
        'default_sort': 'order_number',
        'required': ['order_number'],
        'amounts': ['unit_price', 'remaining_amount', 'amount_currency'],
        'dates': ['order_date', 'delivery_date', 'requested_delivery_date'],
    },
    'quotes': {
        'model': Quote,
        'label': 'Quotes (Offerter)',
        'default_sort': 'quote_number',
        'required': ['quote_number'],
        'amounts': ['unit_price', 'amount'],
        'dates': ['validity_date', 'delivery_date'],
    },
    'order_intake': {
        'model': OrderIntake,
        'label': 'Order Intake (Orderingång)',
        'default_sort': 'log_date',
        'required': ['order_number'],
        'amounts': ['price', 'value'],
        'dates': ['log_date'],
    },
    'invoice_log': {
        'model': InvoiceLog,
        'label': 'Invoice Log (Faktureringslogg)',
        'default_sort': 'date',
        'required': ['invoice_number', 'date'],
        'amounts': ['unit_price', 'amount', 'amount_currency'],
        'dates': ['date'],
    },
    'exchange_rates': {
        'model': ExchangeRate,
        'label': 'Exchange Rates (Valutakurser)',
        'default_sort': 'date',
        'required': ['date'],
        'amounts': ['dkk', 'eur', 'gbp', 'nok', 'usd'],
        'dates': ['date'],
    },
    'articles': {
        'model': Article,
        'label': 'Articles (Artikellista)',
        'default_sort': 'article_number',
        'required': ['article_number'],
        'amounts': ['wip_balance', 'cleared_balance', 'available_balance', 'total_balance'],
        'dates': [],
    },
    'minimum_stock': {
        'model': MinimumStock,
        'label': 'Minimum Stock',
        'default_sort': 'article_number',
        'required': ['article_number'],
        'amounts': ['ordered_quantity'],
        'dates': [],
    },
}


def _get_visible_columns(model):
    """Return list of column objects excluding hidden internal columns."""
    mapper = sa_inspect(model)
    return [c for c in mapper.columns if c.key not in _HIDDEN_COLS]


def _column_completeness(model, columns):
    """Return dict of column_name → completeness % (non-null ratio)."""
    total = db.session.query(func.count(model.id)).scalar() or 0
    if total == 0:
        return {c.key: 100.0 for c in columns}

    result = {}
    for col in columns:
        non_null = db.session.query(
            func.count(model.id)
        ).filter(col != None).scalar()  # noqa: E711
        result[col.key] = round(100.0 * non_null / total, 1)
    return result


def get_anomalies(table_key):
    """Detect data quality anomalies for a given table."""
    info = TABLE_REGISTRY.get(table_key)
    if not info:
        return []

    model = info['model']
    anomalies = []
    mapper = sa_inspect(model)
    col_map = {c.key: c for c in mapper.columns}

    # 1. Null required fields
    for field_name in info['required']:
        col = col_map.get(field_name)
        if col is None:
            continue
        count = db.session.query(func.count(model.id)).filter(
            col == None  # noqa: E711
        ).scalar()
        if count > 0:
            anomalies.append({
                'type': 'null_required',
                'message': f'{field_name} is NULL',
                'count': count,
            })

    # 2. Zero amounts (where amount should normally be non-zero)
    for field_name in info['amounts']:
        col = col_map.get(field_name)
        if col is None:
            continue
        count = db.session.query(func.count(model.id)).filter(
            col == 0
        ).scalar()
        if count > 0:
            anomalies.append({
                'type': 'zero_amount',
                'message': f'{field_name} is zero',
                'count': count,
            })

    # 3. Future dates (more than 1 year ahead)
    today = date.today()
    future_limit = today.replace(year=today.year + 1)
    for field_name in info['dates']:
        col = col_map.get(field_name)
        if col is None:
            continue
        count = db.session.query(func.count(model.id)).filter(
            col > future_limit
        ).scalar()
        if count > 0:
            anomalies.append({
                'type': 'future_date',
                'message': f'{field_name} is more than 1 year in the future',
                'count': count,
            })

    # 4. Verification-specific: both debit and credit non-zero on same row
    if table_key == 'verifications':
        count = db.session.query(func.count(Verification.id)).filter(
            Verification.debit != 0,
            Verification.credit != 0,
        ).scalar()
        if count > 0:
            anomalies.append({
                'type': 'debit_credit_both',
                'message': 'Both debit and credit are non-zero',
                'count': count,
            })

    return anomalies


def get_overall_summary():
    """Return summary data for all registered tables."""
    tables = []
    total_records = 0
    total_completeness_sum = 0.0
    total_anomalies = 0

    for key, info in TABLE_REGISTRY.items():
        model = info['model']
        count = db.session.query(func.count(model.id)).scalar() or 0
        total_records += count

        columns = _get_visible_columns(model)
        completeness = _column_completeness(model, columns)
        avg_completeness = (
            sum(completeness.values()) / len(completeness)
            if completeness else 100.0
        )
        total_completeness_sum += avg_completeness

        anomalies = get_anomalies(key)
        anomaly_count = sum(a['count'] for a in anomalies)
        total_anomalies += anomaly_count

        # Sample rows (first 5)
        sort_col = getattr(model, info['default_sort'], model.id)
        samples = model.query.order_by(sort_col).limit(5).all()
        sample_dicts = [s.to_dict() for s in samples]
        # Remove hidden keys from samples
        for d in sample_dicts:
            for k in list(d.keys()):
                if k in _HIDDEN_COLS:
                    del d[k]

        tables.append({
            'key': key,
            'label': info['label'],
            'count': count,
            'completeness': round(avg_completeness, 1),
            'column_completeness': completeness,
            'anomalies': anomalies,
            'anomaly_count': anomaly_count,
            'samples': sample_dicts,
        })

    overall_completeness = (
        round(total_completeness_sum / len(TABLE_REGISTRY), 1)
        if TABLE_REGISTRY else 100.0
    )

    return {
        'tables': tables,
        'total_records': total_records,
        'overall_completeness': overall_completeness,
        'total_anomalies': total_anomalies,
    }


def get_table_data(table_key, page=1, per_page=25, search=None,
                   sort_by=None, sort_dir='asc'):
    """Return paginated, searchable, sortable data for a table."""
    info = TABLE_REGISTRY.get(table_key)
    if not info:
        return None

    model = info['model']
    columns = _get_visible_columns(model)
    col_names = [c.key for c in columns]

    query = model.query

    # Text search across all string columns
    if search:
        search_term = f'%{search}%'
        string_filters = []
        for col in columns:
            if isinstance(col.type, String):
                string_filters.append(col.ilike(search_term))
            # Also cast Integer/Float cols for numeric search
        if string_filters:
            query = query.filter(or_(*string_filters))

    # Sorting
    sort_col_name = sort_by if sort_by in col_names else info['default_sort']
    sort_column = getattr(model, sort_col_name, model.id)
    if sort_dir == 'desc':
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    rows = []
    for item in pagination.items:
        d = item.to_dict()
        # Only keep visible columns
        row = {k: d.get(k) for k in col_names}
        rows.append(row)

    return {
        'columns': col_names,
        'rows': rows,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_prev': pagination.has_prev,
            'has_next': pagination.has_next,
        },
        'info': info,
    }
