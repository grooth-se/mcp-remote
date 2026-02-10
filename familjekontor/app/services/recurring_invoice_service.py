"""Recurring invoice service: template management and invoice generation."""

from datetime import date, datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models.recurring_invoice import RecurringInvoiceTemplate, RecurringLineItem
from app.models.invoice import CustomerInvoice, InvoiceLineItem
from app.services.invoice_pdf_service import generate_next_invoice_number, recalculate_invoice_totals


def get_due_templates(company_id):
    """Return templates where next_date <= today, active, and not past end_date."""
    today = date.today()
    query = RecurringInvoiceTemplate.query.filter(
        RecurringInvoiceTemplate.company_id == company_id,
        RecurringInvoiceTemplate.active == True,
        RecurringInvoiceTemplate.next_date <= today,
    ).filter(
        db.or_(
            RecurringInvoiceTemplate.end_date.is_(None),
            RecurringInvoiceTemplate.end_date >= today,
        )
    )
    return query.order_by(RecurringInvoiceTemplate.next_date).all()


def get_due_count(company_id):
    """Count of templates due for generation."""
    today = date.today()
    return RecurringInvoiceTemplate.query.filter(
        RecurringInvoiceTemplate.company_id == company_id,
        RecurringInvoiceTemplate.active == True,
        RecurringInvoiceTemplate.next_date <= today,
    ).filter(
        db.or_(
            RecurringInvoiceTemplate.end_date.is_(None),
            RecurringInvoiceTemplate.end_date >= today,
        )
    ).count()


def advance_next_date(current_date, interval):
    """Advance a date by the given interval.

    monthly:   +1 month (clamp day to month end)
    quarterly: +3 months
    yearly:    +1 year
    """
    year = current_date.year
    month = current_date.month
    day = current_date.day

    if interval == 'monthly':
        month += 1
    elif interval == 'quarterly':
        month += 3
    elif interval == 'yearly':
        year += 1
    else:
        month += 1  # default to monthly

    # Handle month overflow
    while month > 12:
        month -= 12
        year += 1

    # Clamp day to valid range for target month
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = min(day, max_day)

    return date(year, month, day)


def generate_invoice_from_template(template_id):
    """Generate a CustomerInvoice from a recurring template.

    - Creates CustomerInvoice with status 'draft'
    - Copies RecurringLineItems -> InvoiceLineItems
    - Recalculates totals
    - Handles FX for non-SEK currencies
    - Advances template's next_date
    - Returns the created invoice or None on error
    """
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template:
        return None

    invoice_date = template.next_date
    from datetime import timedelta
    due_date = invoice_date + timedelta(days=template.payment_terms)

    # Generate invoice number
    invoice_number = generate_next_invoice_number(template.company_id)

    # Handle exchange rate for foreign currencies
    currency = template.currency or 'SEK'
    is_foreign = currency != 'SEK'
    ex_rate = Decimal('1.0')

    if is_foreign:
        try:
            from app.services.exchange_rate_service import get_rate
            ex_rate = get_rate(currency, invoice_date)
        except (ValueError, Exception):
            # Fallback: rate 1.0, user can adjust later
            pass

    invoice = CustomerInvoice(
        company_id=template.company_id,
        customer_id=template.customer_id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        currency=currency,
        exchange_rate=ex_rate,
        vat_type=template.vat_type,
        status='draft',
    )
    db.session.add(invoice)
    db.session.flush()

    # Copy line items
    for rli in template.line_items:
        qty = Decimal(str(rli.quantity))
        price = Decimal(str(rli.unit_price))
        rate = Decimal(str(rli.vat_rate))
        amount = qty * price
        vat_amount = amount * rate / Decimal('100')

        item = InvoiceLineItem(
            customer_invoice_id=invoice.id,
            line_number=rli.line_number,
            description=rli.description,
            quantity=qty,
            unit=rli.unit,
            unit_price=price,
            vat_rate=rate,
            amount=amount,
            vat_amount=vat_amount,
        )
        db.session.add(item)

    db.session.flush()
    recalculate_invoice_totals(invoice.id)

    # Set amount_sek for foreign currency
    db.session.refresh(invoice)
    if is_foreign and invoice.total_amount:
        invoice.amount_sek = (Decimal(str(invoice.total_amount)) * ex_rate).quantize(Decimal('0.01'))

    # Advance template
    template.next_date = advance_next_date(invoice_date, template.interval)
    template.last_generated_at = datetime.now(timezone.utc)
    template.invoices_generated = (template.invoices_generated or 0) + 1

    db.session.commit()
    return invoice


def generate_all_due(company_id):
    """Generate invoices for all due templates. Returns count of generated invoices."""
    templates = get_due_templates(company_id)
    count = 0
    for t in templates:
        invoice = generate_invoice_from_template(t.id)
        if invoice:
            count += 1
    return count
