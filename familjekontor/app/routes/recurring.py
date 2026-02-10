from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.extensions import db
from app.models.invoice import Customer, CustomerInvoice
from app.models.recurring_invoice import RecurringInvoiceTemplate, RecurringLineItem
from app.forms.recurring_invoice import RecurringInvoiceTemplateForm, RecurringLineItemForm
from app.services.recurring_invoice_service import (
    get_due_templates, get_due_count, generate_invoice_from_template, generate_all_due,
)

recurring_bp = Blueprint('recurring', __name__)


@recurring_bp.route('/')
@login_required
def recurring_list():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    templates = RecurringInvoiceTemplate.query.filter_by(
        company_id=company_id
    ).order_by(RecurringInvoiceTemplate.active.desc(), RecurringInvoiceTemplate.next_date).all()
    due_count = get_due_count(company_id)

    return render_template('recurring/list.html', templates=templates, due_count=due_count,
                           today=date.today())


@recurring_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_recurring():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet att skapa mallar.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    form = RecurringInvoiceTemplateForm()
    customers = Customer.query.filter_by(company_id=company_id, active=True).order_by(Customer.name).all()
    form.customer_id.choices = [(c.id, c.name) for c in customers]

    if form.validate_on_submit():
        template = RecurringInvoiceTemplate(
            company_id=company_id,
            customer_id=form.customer_id.data,
            name=form.name.data,
            currency=form.currency.data,
            vat_type=form.vat_type.data,
            interval=form.interval.data,
            payment_terms=form.payment_terms.data,
            start_date=form.start_date.data,
            next_date=form.start_date.data,
            end_date=form.end_date.data,
        )
        db.session.add(template)
        db.session.commit()
        flash(f'Återkommande fakturamall "{template.name}" har skapats.', 'success')
        return redirect(url_for('recurring.view_recurring', template_id=template.id))

    return render_template('recurring/form.html', form=form, is_edit=False)


@recurring_bp.route('/<int:template_id>')
@login_required
def view_recurring(template_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        flash('Mall hittades inte.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    line_form = RecurringLineItemForm()

    # Get generated invoices for this template's customer (approximation)
    generated_invoices = CustomerInvoice.query.filter_by(
        company_id=company_id,
        customer_id=template.customer_id,
    ).order_by(CustomerInvoice.invoice_date.desc()).limit(20).all()

    return render_template('recurring/view.html',
                           template=template, line_form=line_form,
                           generated_invoices=generated_invoices)


@recurring_bp.route('/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recurring(template_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        flash('Mall hittades inte.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    if current_user.is_readonly:
        flash('Du har inte behörighet att redigera mallar.', 'danger')
        return redirect(url_for('recurring.view_recurring', template_id=template_id))

    form = RecurringInvoiceTemplateForm(obj=template)
    customers = Customer.query.filter_by(company_id=company_id, active=True).order_by(Customer.name).all()
    form.customer_id.choices = [(c.id, c.name) for c in customers]

    if form.validate_on_submit():
        template.customer_id = form.customer_id.data
        template.name = form.name.data
        template.currency = form.currency.data
        template.vat_type = form.vat_type.data
        template.interval = form.interval.data
        template.payment_terms = form.payment_terms.data
        template.start_date = form.start_date.data
        template.end_date = form.end_date.data
        # Only update next_date if it hasn't been used yet
        if template.invoices_generated == 0:
            template.next_date = form.start_date.data
        db.session.commit()
        flash('Mallen har uppdaterats.', 'success')
        return redirect(url_for('recurring.view_recurring', template_id=template_id))

    return render_template('recurring/form.html', form=form, is_edit=True, template=template)


@recurring_bp.route('/<int:template_id>/toggle', methods=['POST'])
@login_required
def toggle_recurring(template_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        flash('Mall hittades inte.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    template.active = not template.active
    db.session.commit()
    status = 'aktiverad' if template.active else 'pausad'
    flash(f'Mallen har {status}.', 'success')
    return redirect(url_for('recurring.recurring_list'))


@recurring_bp.route('/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_recurring(template_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        flash('Mall hittades inte.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    name = template.name
    db.session.delete(template)
    db.session.commit()
    flash(f'Mallen "{name}" har tagits bort.', 'success')
    return redirect(url_for('recurring.recurring_list'))


@recurring_bp.route('/<int:template_id>/add-line', methods=['POST'])
@login_required
def add_line_item(template_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        return redirect(url_for('recurring.recurring_list'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('recurring.view_recurring', template_id=template_id))

    form = RecurringLineItemForm()
    if form.validate_on_submit():
        max_line = db.session.query(
            db.func.coalesce(db.func.max(RecurringLineItem.line_number), 0)
        ).filter_by(template_id=template_id).scalar()

        item = RecurringLineItem(
            template_id=template_id,
            line_number=max_line + 1,
            description=form.description.data,
            quantity=Decimal(str(form.quantity.data)),
            unit=form.unit.data,
            unit_price=Decimal(str(form.unit_price.data)),
            vat_rate=Decimal(form.vat_rate.data),
        )
        db.session.add(item)
        db.session.commit()
        flash('Rad har lagts till.', 'success')

    return redirect(url_for('recurring.view_recurring', template_id=template_id))


@recurring_bp.route('/<int:template_id>/remove-line/<int:line_id>', methods=['POST'])
@login_required
def remove_line_item(template_id, line_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        return redirect(url_for('recurring.recurring_list'))

    item = db.session.get(RecurringLineItem, line_id)
    if item and item.template_id == template_id:
        db.session.delete(item)
        db.session.commit()
        flash('Rad har tagits bort.', 'success')

    return redirect(url_for('recurring.view_recurring', template_id=template_id))


@recurring_bp.route('/<int:template_id>/generate', methods=['POST'])
@login_required
def generate_single(template_id):
    company_id = session.get('active_company_id')
    template = db.session.get(RecurringInvoiceTemplate, template_id)
    if not template or template.company_id != company_id:
        flash('Mall hittades inte.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('recurring.view_recurring', template_id=template_id))

    invoice = generate_invoice_from_template(template_id)
    if invoice:
        flash(f'Faktura {invoice.invoice_number} har genererats.', 'success')
    else:
        flash('Kunde inte generera faktura.', 'danger')

    return redirect(url_for('recurring.view_recurring', template_id=template_id))


@recurring_bp.route('/generate-all', methods=['POST'])
@login_required
def generate_all():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('recurring.recurring_list'))

    count = generate_all_due(company_id)
    if count > 0:
        flash(f'{count} fakturor har genererats.', 'success')
    else:
        flash('Inga fakturor att generera.', 'info')

    return redirect(url_for('recurring.recurring_list'))
