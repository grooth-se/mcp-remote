"""Invoice PDF service: line items, totals, PDF generation."""

from decimal import Decimal
from datetime import datetime, timezone

from flask import render_template
from app.extensions import db
from app.models.invoice import CustomerInvoice, InvoiceLineItem
from app.models.company import Company
from app.models.audit import AuditLog


def generate_next_invoice_number(company_id):
    """Generate next sequential invoice number: PREFIX-YEAR-NNNN."""
    company = db.session.get(Company, company_id)
    year = datetime.now().year

    # Use first 3 chars of company name as prefix
    prefix = (company.name[:3].upper() if company else 'INV')

    # Find highest existing number for this prefix/year
    existing = CustomerInvoice.query.filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_number.like(f'{prefix}-{year}-%'),
    ).order_by(CustomerInvoice.invoice_number.desc()).first()

    if existing:
        try:
            last_num = int(existing.invoice_number.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    return f'{prefix}-{year}-{next_num:04d}'


def add_line_item(invoice_id, description, quantity, unit_price, vat_rate=25, unit='st'):
    """Add a line item to a customer invoice."""
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice:
        return None

    # Determine next line number
    max_line = db.session.query(
        db.func.coalesce(db.func.max(InvoiceLineItem.line_number), 0)
    ).filter_by(customer_invoice_id=invoice_id).scalar()

    qty = Decimal(str(quantity))
    price = Decimal(str(unit_price))
    rate = Decimal(str(vat_rate))

    amount = qty * price
    vat_amount = amount * rate / Decimal('100')

    item = InvoiceLineItem(
        customer_invoice_id=invoice_id,
        line_number=max_line + 1,
        description=description,
        quantity=qty,
        unit=unit,
        unit_price=price,
        vat_rate=rate,
        amount=amount,
        vat_amount=vat_amount,
    )
    db.session.add(item)
    db.session.commit()

    recalculate_invoice_totals(invoice_id)
    return item


def update_line_item(item_id, description=None, quantity=None, unit_price=None,
                     vat_rate=None, unit=None):
    item = db.session.get(InvoiceLineItem, item_id)
    if not item:
        return None

    if description is not None:
        item.description = description
    if quantity is not None:
        item.quantity = Decimal(str(quantity))
    if unit_price is not None:
        item.unit_price = Decimal(str(unit_price))
    if vat_rate is not None:
        item.vat_rate = Decimal(str(vat_rate))
    if unit is not None:
        item.unit = unit

    item.amount = item.quantity * item.unit_price
    item.vat_amount = item.amount * item.vat_rate / Decimal('100')

    db.session.commit()
    recalculate_invoice_totals(item.customer_invoice_id)
    return item


def remove_line_item(item_id):
    item = db.session.get(InvoiceLineItem, item_id)
    if not item:
        return False

    invoice_id = item.customer_invoice_id
    db.session.delete(item)
    db.session.commit()
    recalculate_invoice_totals(invoice_id)
    return True


def recalculate_invoice_totals(invoice_id):
    """Recalculate amount_excl_vat, vat_amount, total_amount from line items."""
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice:
        return

    items = InvoiceLineItem.query.filter_by(customer_invoice_id=invoice_id).all()

    if items:
        amount_excl = sum(item.amount or Decimal('0') for item in items)
        vat = sum(item.vat_amount or Decimal('0') for item in items)
        invoice.amount_excl_vat = amount_excl
        invoice.vat_amount = vat
        invoice.total_amount = amount_excl + vat
    else:
        # Don't reset to zero if line items were removed but invoice already has manual amounts
        pass

    db.session.commit()


def generate_invoice_pdf(invoice_id):
    """Generate PDF from invoice using weasyprint."""
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice:
        return None

    company = invoice.company
    customer = invoice.customer
    items = InvoiceLineItem.query.filter_by(
        customer_invoice_id=invoice_id
    ).order_by(InvoiceLineItem.line_number).all()

    # VAT breakdown by rate
    vat_breakdown = {}
    for item in items:
        rate = float(item.vat_rate or 0)
        if rate not in vat_breakdown:
            vat_breakdown[rate] = {'base': 0, 'vat': 0}
        vat_breakdown[rate]['base'] += float(item.amount or 0)
        vat_breakdown[rate]['vat'] += float(item.vat_amount or 0)

    html = render_template('invoices/invoice_pdf.html',
                           invoice=invoice, company=company,
                           customer=customer, items=items,
                           vat_breakdown=vat_breakdown)

    try:
        from weasyprint import HTML
    except ImportError:
        # weasyprint not installed - return HTML as fallback
        return html

    import os
    from flask import current_app

    pdf_dir = os.path.join(current_app.static_folder, 'invoices', str(company.id))
    os.makedirs(pdf_dir, exist_ok=True)

    filename = f'{invoice.invoice_number}.pdf'
    pdf_path = os.path.join(pdf_dir, filename)

    HTML(string=html).write_pdf(pdf_path)

    invoice.pdf_generated = True
    invoice.pdf_path = f'invoices/{company.id}/{filename}'
    db.session.commit()

    return pdf_path


def get_invoice_pdf_path(invoice_id):
    """Get the PDF file path for a generated invoice."""
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or not invoice.pdf_path:
        return None

    import os
    from flask import current_app
    return os.path.join(current_app.static_folder, invoice.pdf_path)


def mark_invoice_sent(invoice_id, user_id):
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice:
        return False

    invoice.status = 'sent'
    invoice.sent_at = datetime.now(timezone.utc)

    audit = AuditLog(
        company_id=invoice.company_id, user_id=user_id,
        action='update', entity_type='customer_invoice', entity_id=invoice.id,
        old_values={'status': 'draft'}, new_values={'status': 'sent'},
    )
    db.session.add(audit)
    db.session.commit()
    return True
