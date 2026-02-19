"""REST API routes for consuming applications."""

from flask import jsonify, request, current_app
from app.api import api_bp
from app.extensions import db
from app.models.accounting import Account, Verification
from app.models.projects import (
    Project, ProjectAdjustment, TimeTracking, CustomerOrderProjectMap
)
from app.models.orders import CustomerOrder, PurchaseOrder, Quote, OrderIntake
from app.models.invoicing import InvoiceLog, ExchangeRate
from app.models.inventory import Article, MinimumStock
from app.models.extraction import ExtractionLog
from app.services.import_service import ImportService
from datetime import datetime


def paginate(query, default_per_page=50):
    """Apply pagination to a query. Returns dict with items + metadata."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', default_per_page, type=int)
    per_page = min(per_page, 1000)  # cap at 1000

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [item.to_dict() for item in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def parse_date(date_str):
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None


# --- Health & Status ---

@api_bp.route('/health')
def health():
    counts = {
        'accounts': db.session.query(Account).count(),
        'verifications': db.session.query(Verification).count(),
        'projects': db.session.query(Project).count(),
        'customer_orders': db.session.query(CustomerOrder).count(),
        'purchase_orders': db.session.query(PurchaseOrder).count(),
        'quotes': db.session.query(Quote).count(),
        'order_intake': db.session.query(OrderIntake).count(),
        'invoice_log': db.session.query(InvoiceLog).count(),
        'exchange_rates': db.session.query(ExchangeRate).count(),
        'articles': db.session.query(Article).count(),
    }
    last_extraction = db.session.query(ExtractionLog).order_by(
        ExtractionLog.started_at.desc()
    ).first()
    return jsonify({
        'status': 'ok',
        'record_counts': counts,
        'total_records': sum(counts.values()),
        'last_extraction': last_extraction.to_dict() if last_extraction else None,
    })


# --- Accounts ---

@api_bp.route('/accounts')
def get_accounts():
    query = Account.query.order_by(Account.account_number)
    account_type = request.args.get('type')
    if account_type:
        query = query.filter(Account.account_type == account_type)
    return jsonify(paginate(query, default_per_page=200))


@api_bp.route('/accounts/<int:number>')
def get_account(number):
    account = Account.query.filter_by(account_number=number).first_or_404()
    return jsonify(account.to_dict())


# --- Verifications ---

@api_bp.route('/verifications')
def get_verifications():
    query = Verification.query.order_by(Verification.date.desc(), Verification.id)

    from_date = parse_date(request.args.get('from_date'))
    to_date = parse_date(request.args.get('to_date'))
    project = request.args.get('project')
    account = request.args.get('account', type=int)

    if from_date:
        query = query.filter(Verification.date >= from_date)
    if to_date:
        query = query.filter(Verification.date <= to_date)
    if project:
        query = query.filter(Verification.project == project)
    if account:
        query = query.filter(Verification.account == account)

    return jsonify(paginate(query))


@api_bp.route('/verifications/<ver_nr>')
def get_verification(ver_nr):
    rows = Verification.query.filter_by(
        verification_number=ver_nr
    ).order_by(Verification.id).all()
    if not rows:
        return jsonify({'error': 'Not found'}), 404
    return jsonify([r.to_dict() for r in rows])


# --- Projects ---

@api_bp.route('/projects')
def get_projects():
    query = Project.query.order_by(Project.project_number)
    customer = request.args.get('customer')
    if customer:
        query = query.filter(Project.customer.ilike(f'%{customer}%'))
    return jsonify(paginate(query, default_per_page=200))


@api_bp.route('/projects/<code>')
def get_project(code):
    project = Project.query.filter_by(project_number=code).first_or_404()
    result = project.to_dict()
    result['adjustments'] = [a.to_dict() for a in project.adjustments.all()]
    result['time_tracking'] = [t.to_dict() for t in project.time_entries.all()]
    return jsonify(result)


@api_bp.route('/projects/<code>/verifications')
def get_project_verifications(code):
    query = Verification.query.filter_by(project=code).order_by(
        Verification.date.desc()
    )
    from_date = parse_date(request.args.get('from_date'))
    to_date = parse_date(request.args.get('to_date'))
    if from_date:
        query = query.filter(Verification.date >= from_date)
    if to_date:
        query = query.filter(Verification.date <= to_date)
    return jsonify(paginate(query))


@api_bp.route('/projects/<code>/orders')
def get_project_orders(code):
    customer_orders = CustomerOrder.query.filter_by(project=code).all()
    purchase_orders = PurchaseOrder.query.filter_by(project=code).all()
    return jsonify({
        'customer_orders': [o.to_dict() for o in customer_orders],
        'purchase_orders': [o.to_dict() for o in purchase_orders],
    })


# --- Customer Orders ---

@api_bp.route('/customer-orders')
def get_customer_orders():
    query = CustomerOrder.query.order_by(CustomerOrder.order_number)
    project = request.args.get('project')
    customer = request.args.get('customer')
    if project:
        query = query.filter(CustomerOrder.project == project)
    if customer:
        query = query.filter(CustomerOrder.customer_name.ilike(f'%{customer}%'))
    return jsonify(paginate(query))


# --- Purchase Orders ---

@api_bp.route('/purchase-orders')
def get_purchase_orders():
    query = PurchaseOrder.query.order_by(PurchaseOrder.order_number)
    project = request.args.get('project')
    supplier = request.args.get('supplier')
    if project:
        query = query.filter(PurchaseOrder.project == project)
    if supplier:
        query = query.filter(PurchaseOrder.supplier_name.ilike(f'%{supplier}%'))
    return jsonify(paginate(query))


# --- Quotes ---

@api_bp.route('/quotes')
def get_quotes():
    query = Quote.query.order_by(Quote.quote_number)
    customer = request.args.get('customer')
    status = request.args.get('status')
    if customer:
        query = query.filter(Quote.customer_name.ilike(f'%{customer}%'))
    if status:
        query = query.filter(Quote.status.ilike(f'%{status}%'))
    return jsonify(paginate(query))


# --- Order Intake ---

@api_bp.route('/order-intake')
def get_order_intake():
    query = OrderIntake.query.order_by(OrderIntake.log_date.desc())
    from_date = parse_date(request.args.get('from_date'))
    to_date = parse_date(request.args.get('to_date'))
    if from_date:
        query = query.filter(OrderIntake.log_date >= from_date)
    if to_date:
        query = query.filter(OrderIntake.log_date <= to_date)
    return jsonify(paginate(query))


# --- Invoices ---

@api_bp.route('/invoices')
def get_invoices():
    query = InvoiceLog.query.order_by(InvoiceLog.date.desc())
    from_date = parse_date(request.args.get('from_date'))
    to_date = parse_date(request.args.get('to_date'))
    project = request.args.get('project')
    customer = request.args.get('customer')
    if from_date:
        query = query.filter(InvoiceLog.date >= from_date)
    if to_date:
        query = query.filter(InvoiceLog.date <= to_date)
    if project:
        query = query.filter(InvoiceLog.project == project)
    if customer:
        query = query.filter(InvoiceLog.customer_name.ilike(f'%{customer}%'))
    return jsonify(paginate(query))


# --- Exchange Rates ---

@api_bp.route('/exchange-rates')
def get_exchange_rates():
    query = ExchangeRate.query.order_by(ExchangeRate.date.desc())
    return jsonify(paginate(query, default_per_page=100))


@api_bp.route('/exchange-rates/latest')
def get_latest_exchange_rate():
    rate = ExchangeRate.query.order_by(ExchangeRate.date.desc()).first()
    if not rate:
        return jsonify({'error': 'No exchange rates found'}), 404
    return jsonify(rate.to_dict())


# --- Articles ---

@api_bp.route('/articles')
def get_articles():
    query = Article.query.order_by(Article.article_number)
    return jsonify(paginate(query))


@api_bp.route('/articles/<path:number>')
def get_article(number):
    article = Article.query.filter_by(article_number=number).first_or_404()
    result = article.to_dict()
    min_stock = MinimumStock.query.filter_by(article_number=number).first()
    result['minimum_stock'] = min_stock.to_dict() if min_stock else None
    return jsonify(result)


# --- Cross References ---

@api_bp.route('/order-project-map')
def get_order_project_map():
    items = CustomerOrderProjectMap.query.order_by(
        CustomerOrderProjectMap.order_number
    ).all()
    return jsonify([item.to_dict() for item in items])


# --- Aggregated endpoint for Accrued Income app ---

@api_bp.route('/accrued-income-data')
def get_accrued_income_data():
    """Returns all data needed for accrued income calculation in one call.

    Includes pre-aggregated GL summary (income/cost by project) so the
    consumer doesn't need raw verification rows.
    """
    projects = Project.query.all()
    adjustments = ProjectAdjustment.query.all()
    time_data = TimeTracking.query.all()
    co_map = CustomerOrderProjectMap.query.all()
    customer_orders = CustomerOrder.query.all()
    purchase_orders = PurchaseOrder.query.all()
    invoices = InvoiceLog.query.all()
    rates = ExchangeRate.query.order_by(ExchangeRate.date.desc()).first()

    # Pre-aggregate GL data by project:
    # Income = accounts 3000-3999 (credit - debit)
    # Cost = accounts 4000-6999 excl 4940/4950 (debit - credit)
    from sqlalchemy import func
    income_q = db.session.query(
        Verification.project,
        func.sum(Verification.credit - Verification.debit).label('net')
    ).filter(
        Verification.account >= 3000,
        Verification.account <= 3999,
        Verification.project.isnot(None),
        Verification.project != ''
    ).group_by(Verification.project).all()

    cost_q = db.session.query(
        Verification.project,
        func.sum(Verification.debit - Verification.credit).label('net')
    ).filter(
        Verification.account >= 4000,
        Verification.account <= 6999,
        Verification.account != 4940,
        Verification.account != 4950,
        Verification.project.isnot(None),
        Verification.project != ''
    ).group_by(Verification.project).all()

    gl_summary = {
        'income_by_project': {row.project: float(row.net or 0) for row in income_q},
        'cost_by_project': {row.project: float(row.net or 0) for row in cost_q},
    }

    return jsonify({
        'projects': [p.to_dict() for p in projects],
        'adjustments': [a.to_dict() for a in adjustments],
        'time_tracking': [t.to_dict() for t in time_data],
        'co_project_map': [m.to_dict() for m in co_map],
        'customer_orders': [o.to_dict() for o in customer_orders],
        'purchase_orders': [o.to_dict() for o in purchase_orders],
        'invoice_log': [i.to_dict() for i in invoices],
        'gl_summary': gl_summary,
        'exchange_rates': rates.to_dict() if rates else None,
    })


# --- Import Control ---

@api_bp.route('/extract/trigger', methods=['POST'])
def trigger_extraction():
    folder = current_app.config['EXCEL_EXPORTS_FOLDER']
    service = ImportService()
    log = service.run_full_import(folder)
    return jsonify(log.to_dict()), 201


@api_bp.route('/extract/status')
def extraction_status():
    log = db.session.query(ExtractionLog).order_by(
        ExtractionLog.started_at.desc()
    ).first()
    if not log:
        return jsonify({'status': 'no_extractions'})
    return jsonify(log.to_dict())


@api_bp.route('/extract/history')
def extraction_history():
    logs = ExtractionLog.query.order_by(
        ExtractionLog.started_at.desc()
    ).limit(20).all()
    return jsonify([l.to_dict() for l in logs])
