from datetime import date
from decimal import Decimal
from app.models.invoice import SupplierInvoice, CustomerInvoice
from app.models.tax import TaxPayment

PAYMENT_TYPE_LABELS = {
    'vat': 'Moms',
    'employer_tax': 'Arbetsgivaravgifter',
    'corporate_tax': 'Bolagsskatt',
    'preliminary_tax': 'F-skatt',
}


def get_all_payments(company_id, from_date=None, to_date=None, payment_type=None):
    """Get all payments across supplier invoices, customer invoices, and tax payments.

    Returns (payments_list, summary_dict) where summary has total_in, total_out, net.
    """
    payments = []

    # Supplier invoices (paid)
    if payment_type is None or payment_type == 'supplier':
        q = SupplierInvoice.query.filter_by(company_id=company_id, status='paid').filter(
            SupplierInvoice.paid_at.isnot(None)
        )
        if from_date:
            q = q.filter(SupplierInvoice.paid_at >= from_date)
        if to_date:
            q = q.filter(SupplierInvoice.paid_at <= to_date)
        for inv in q.all():
            payments.append({
                'date': inv.paid_at.date() if inv.paid_at else inv.invoice_date,
                'type': 'supplier',
                'description': f'{inv.supplier.name} - {inv.invoice_number or ""}',
                'amount': float(inv.total_amount or 0),
                'direction': 'out',
                'verification_id': inv.payment_verification_id,
                'source_id': inv.id,
                'source_type': 'supplier_invoice',
            })

    # Customer invoices (paid)
    if payment_type is None or payment_type == 'customer':
        q = CustomerInvoice.query.filter_by(company_id=company_id, status='paid').filter(
            CustomerInvoice.paid_at.isnot(None)
        )
        if from_date:
            q = q.filter(CustomerInvoice.paid_at >= from_date)
        if to_date:
            q = q.filter(CustomerInvoice.paid_at <= to_date)
        for inv in q.all():
            payments.append({
                'date': inv.paid_at.date() if inv.paid_at else inv.invoice_date,
                'type': 'customer',
                'description': f'{inv.customer.name} - {inv.invoice_number}',
                'amount': float(inv.total_amount or 0),
                'direction': 'in',
                'verification_id': inv.payment_verification_id,
                'source_id': inv.id,
                'source_type': 'customer_invoice',
            })

    # Tax payments
    if payment_type is None or payment_type == 'tax':
        q = TaxPayment.query.filter_by(company_id=company_id)
        if from_date:
            q = q.filter(TaxPayment.payment_date >= from_date)
        if to_date:
            q = q.filter(TaxPayment.payment_date <= to_date)
        for tp in q.all():
            label = PAYMENT_TYPE_LABELS.get(tp.payment_type, tp.payment_type)
            ref = f' ({tp.reference})' if tp.reference else ''
            payments.append({
                'date': tp.payment_date,
                'type': 'tax',
                'description': f'{label}{ref}',
                'amount': float(tp.amount or 0),
                'direction': 'out',
                'verification_id': tp.verification_id,
                'source_id': tp.id,
                'source_type': 'tax_payment',
            })

    # Sort by date descending
    payments.sort(key=lambda p: p['date'], reverse=True)

    # Summary
    total_in = sum(p['amount'] for p in payments if p['direction'] == 'in')
    total_out = sum(p['amount'] for p in payments if p['direction'] == 'out')
    summary = {
        'total_in': total_in,
        'total_out': total_out,
        'net': total_in - total_out,
    }

    return payments, summary
