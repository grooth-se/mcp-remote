"""Accounts Receivable / Accounts Payable analysis service.

Provides aging analysis, DSO/DPO, and top customer/supplier rankings.
"""

from datetime import date as date_type, timedelta
from collections import OrderedDict

from sqlalchemy import func, case

from app.extensions import db
from app.models.invoice import CustomerInvoice, SupplierInvoice, Customer, Supplier
from app.services.report_service import _get_account_balances


def get_ar_aging_by_customer(company_id):
    """Accounts Receivable aging by customer.

    Returns list of customers with aging buckets for unpaid invoices.
    """
    today = date_type.today()

    invoices = (CustomerInvoice.query
                .filter_by(company_id=company_id)
                .filter(CustomerInvoice.status.in_(['sent', 'draft', 'overdue']))
                .all())

    customer_data = {}
    for inv in invoices:
        cid = inv.customer_id
        if cid not in customer_data:
            customer = db.session.get(Customer, cid)
            customer_data[cid] = {
                'customer_name': customer.name if customer else 'Okänd',
                'customer_id': cid,
                'current': 0.0,
                '1_30': 0.0,
                '31_60': 0.0,
                '61_90': 0.0,
                '90_plus': 0.0,
                'total': 0.0,
            }

        amount = float(inv.total_amount or 0)
        days = (today - inv.due_date).days if inv.due_date else 0

        if days <= 0:
            customer_data[cid]['current'] += amount
        elif days <= 30:
            customer_data[cid]['1_30'] += amount
        elif days <= 60:
            customer_data[cid]['31_60'] += amount
        elif days <= 90:
            customer_data[cid]['61_90'] += amount
        else:
            customer_data[cid]['90_plus'] += amount

        customer_data[cid]['total'] += amount

    rows = sorted(customer_data.values(), key=lambda r: -r['total'])

    # Round all values
    for row in rows:
        for key in ('current', '1_30', '31_60', '61_90', '90_plus', 'total'):
            row[key] = round(row[key], 2)

    totals = {
        'current': round(sum(r['current'] for r in rows), 2),
        '1_30': round(sum(r['1_30'] for r in rows), 2),
        '31_60': round(sum(r['31_60'] for r in rows), 2),
        '61_90': round(sum(r['61_90'] for r in rows), 2),
        '90_plus': round(sum(r['90_plus'] for r in rows), 2),
        'total': round(sum(r['total'] for r in rows), 2),
    }

    return {'rows': rows, 'totals': totals}


def get_ap_aging_by_supplier(company_id):
    """Accounts Payable aging by supplier.

    Returns list of suppliers with aging buckets for unpaid invoices.
    """
    today = date_type.today()

    invoices = (SupplierInvoice.query
                .filter_by(company_id=company_id)
                .filter(SupplierInvoice.status.in_(['pending', 'approved']))
                .all())

    supplier_data = {}
    for inv in invoices:
        sid = inv.supplier_id
        if sid not in supplier_data:
            supplier = db.session.get(Supplier, sid)
            supplier_data[sid] = {
                'supplier_name': supplier.name if supplier else 'Okänd',
                'supplier_id': sid,
                'current': 0.0,
                '1_30': 0.0,
                '31_60': 0.0,
                '61_90': 0.0,
                '90_plus': 0.0,
                'total': 0.0,
            }

        amount = float(inv.total_amount or 0)
        days = (today - inv.due_date).days if inv.due_date else 0

        if days <= 0:
            supplier_data[sid]['current'] += amount
        elif days <= 30:
            supplier_data[sid]['1_30'] += amount
        elif days <= 60:
            supplier_data[sid]['31_60'] += amount
        elif days <= 90:
            supplier_data[sid]['61_90'] += amount
        else:
            supplier_data[sid]['90_plus'] += amount

        supplier_data[sid]['total'] += amount

    rows = sorted(supplier_data.values(), key=lambda r: -r['total'])

    for row in rows:
        for key in ('current', '1_30', '31_60', '61_90', '90_plus', 'total'):
            row[key] = round(row[key], 2)

    totals = {
        'current': round(sum(r['current'] for r in rows), 2),
        '1_30': round(sum(r['1_30'] for r in rows), 2),
        '31_60': round(sum(r['31_60'] for r in rows), 2),
        '61_90': round(sum(r['61_90'] for r in rows), 2),
        '90_plus': round(sum(r['90_plus'] for r in rows), 2),
        'total': round(sum(r['total'] for r in rows), 2),
    }

    return {'rows': rows, 'totals': totals}


def get_dso(company_id, fiscal_year_id):
    """Days Sales Outstanding = (avg AR / revenue) * 365.

    Uses 15xx account balances for AR and 3xxx for revenue.
    """
    balances = _get_account_balances(company_id, fiscal_year_id)

    ar_balance = sum(b for a, b in balances if a.account_number[:2] in ('15', '16'))
    revenue = sum(-b for a, b in balances if a.account_number[0] == '3')

    if revenue and abs(revenue) > 0.01:
        return round((ar_balance / revenue) * 365, 1)
    return None


def get_dpo(company_id, fiscal_year_id):
    """Days Payable Outstanding = (avg AP / COGS) * 365.

    Uses 24xx account balances for AP and 4xxx for COGS.
    """
    balances = _get_account_balances(company_id, fiscal_year_id)

    ap_balance = sum(-b for a, b in balances if a.account_number[:2] in ('24', '25', '26'))
    cogs = sum(b for a, b in balances if a.account_number[0] == '4')

    if cogs and abs(cogs) > 0.01:
        return round((ap_balance / cogs) * 365, 1)
    return None


def get_top_customers(company_id, fiscal_year_id, limit=10):
    """Top customers by invoiced amount with average payment days."""
    from app.models.accounting import FiscalYear
    fy = db.session.get(FiscalYear, fiscal_year_id)

    invoices = (CustomerInvoice.query
                .filter_by(company_id=company_id)
                .filter(
                    CustomerInvoice.invoice_date >= fy.start_date,
                    CustomerInvoice.invoice_date <= fy.end_date,
                ).all())

    customer_totals = {}
    for inv in invoices:
        cid = inv.customer_id
        if cid not in customer_totals:
            customer = db.session.get(Customer, cid)
            customer_totals[cid] = {
                'customer_name': customer.name if customer else 'Okänd',
                'total_amount': 0.0,
                'invoice_count': 0,
                'payment_days': [],
            }

        customer_totals[cid]['total_amount'] += float(inv.total_amount or 0)
        customer_totals[cid]['invoice_count'] += 1

        if inv.paid_at and inv.invoice_date:
            days = (inv.paid_at.date() - inv.invoice_date).days
            customer_totals[cid]['payment_days'].append(days)

    result = []
    for cid, data in customer_totals.items():
        avg_days = None
        if data['payment_days']:
            avg_days = round(sum(data['payment_days']) / len(data['payment_days']), 0)
        result.append({
            'customer_name': data['customer_name'],
            'total_amount': round(data['total_amount'], 2),
            'invoice_count': data['invoice_count'],
            'avg_payment_days': avg_days,
        })

    result.sort(key=lambda r: -r['total_amount'])
    return result[:limit]


def get_top_suppliers(company_id, fiscal_year_id, limit=10):
    """Top suppliers by invoiced amount with average payment days."""
    from app.models.accounting import FiscalYear  # noqa: F811
    fy = db.session.get(FiscalYear, fiscal_year_id)

    invoices = (SupplierInvoice.query
                .filter_by(company_id=company_id)
                .filter(
                    SupplierInvoice.invoice_date >= fy.start_date,
                    SupplierInvoice.invoice_date <= fy.end_date,
                ).all())

    supplier_totals = {}
    for inv in invoices:
        sid = inv.supplier_id
        if sid not in supplier_totals:
            supplier = db.session.get(Supplier, sid)
            supplier_totals[sid] = {
                'supplier_name': supplier.name if supplier else 'Okänd',
                'total_amount': 0.0,
                'invoice_count': 0,
                'payment_days': [],
            }

        supplier_totals[sid]['total_amount'] += float(inv.total_amount or 0)
        supplier_totals[sid]['invoice_count'] += 1

        if inv.paid_at and inv.invoice_date:
            days = (inv.paid_at.date() - inv.invoice_date).days
            supplier_totals[sid]['payment_days'].append(days)

    result = []
    for sid, data in supplier_totals.items():
        avg_days = None
        if data['payment_days']:
            avg_days = round(sum(data['payment_days']) / len(data['payment_days']), 0)
        result.append({
            'supplier_name': data['supplier_name'],
            'total_amount': round(data['total_amount'], 2),
            'invoice_count': data['invoice_count'],
            'avg_payment_days': avg_days,
        })

    result.sort(key=lambda r: -r['total_amount'])
    return result[:limit]


def get_customer_revenue_breakdown(company_id, fiscal_year_id, limit=10):
    """Revenue breakdown by customer for doughnut chart.

    Returns top N customers + 'Övriga' bucket.
    """
    top = get_top_customers(company_id, fiscal_year_id, limit=limit + 5)
    if not top:
        return {'labels': [], 'values': []}

    total_all = sum(c['total_amount'] for c in top)
    labels = []
    values = []
    others = 0.0

    for i, c in enumerate(top):
        if i < limit:
            labels.append(c['customer_name'])
            values.append(c['total_amount'])
        else:
            others += c['total_amount']

    if others > 0:
        labels.append('Övriga')
        values.append(round(others, 2))

    return {'labels': labels, 'values': values}
