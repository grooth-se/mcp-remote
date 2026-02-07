from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app.extensions import db
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.audit import AuditLog
from app.forms.invoice import SupplierForm, SupplierInvoiceForm, CustomerForm, CustomerInvoiceForm

invoices_bp = Blueprint('invoices', __name__)


# === Suppliers ===

@invoices_bp.route('/suppliers')
@login_required
def suppliers():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    suppliers = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.name).all()
    return render_template('invoices/suppliers.html', suppliers=suppliers)


@invoices_bp.route('/suppliers/new', methods=['GET', 'POST'])
@login_required
def new_supplier():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    form = SupplierForm()
    if form.validate_on_submit():
        supplier = Supplier(
            company_id=company_id,
            name=form.name.data,
            org_number=form.org_number.data,
            default_account=form.default_account.data,
            payment_terms=int(form.payment_terms.data or 30),
            bankgiro=form.bankgiro.data,
            plusgiro=form.plusgiro.data,
            iban=form.iban.data,
            bic=form.bic.data,
        )
        db.session.add(supplier)
        db.session.commit()
        flash(f'Leverantör {supplier.name} har skapats.', 'success')
        return redirect(url_for('invoices.suppliers'))

    return render_template('invoices/new_supplier.html', form=form)


# === Supplier Invoices ===

@invoices_bp.route('/supplier-invoices')
@login_required
def supplier_invoices():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    status = request.args.get('status', '')
    query = SupplierInvoice.query.filter_by(company_id=company_id)
    if status:
        query = query.filter_by(status=status)
    invoices = query.order_by(SupplierInvoice.due_date.desc()).all()

    return render_template('invoices/supplier_invoices.html', invoices=invoices, status=status)


@invoices_bp.route('/supplier-invoices/new', methods=['GET', 'POST'])
@login_required
def new_supplier_invoice():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    form = SupplierInvoiceForm()
    suppliers = Supplier.query.filter_by(company_id=company_id, active=True).order_by(Supplier.name).all()
    form.supplier_id.choices = [(s.id, s.name) for s in suppliers]

    if form.validate_on_submit():
        invoice = SupplierInvoice(
            company_id=company_id,
            supplier_id=form.supplier_id.data,
            invoice_number=form.invoice_number.data,
            invoice_date=form.invoice_date.data,
            due_date=form.due_date.data,
            amount_excl_vat=form.amount_excl_vat.data,
            vat_amount=form.vat_amount.data,
            total_amount=form.total_amount.data,
            currency=form.currency.data,
            status='pending',
        )
        db.session.add(invoice)
        db.session.commit()
        flash('Leverantörsfaktura har skapats.', 'success')
        return redirect(url_for('invoices.supplier_invoices'))

    return render_template('invoices/new_supplier_invoice.html', form=form)


@invoices_bp.route('/supplier-invoices/<int:invoice_id>/approve', methods=['POST'])
@login_required
def approve_supplier_invoice(invoice_id):
    invoice = db.session.get(SupplierInvoice, invoice_id)
    if invoice:
        invoice.status = 'approved'
        audit = AuditLog(
            company_id=invoice.company_id, user_id=current_user.id,
            action='update', entity_type='supplier_invoice', entity_id=invoice.id,
            old_values={'status': 'pending'}, new_values={'status': 'approved'},
        )
        db.session.add(audit)
        db.session.commit()
        flash('Fakturan har godkänts.', 'success')
    return redirect(url_for('invoices.supplier_invoices'))


@invoices_bp.route('/supplier-invoices/<int:invoice_id>/pay', methods=['POST'])
@login_required
def pay_supplier_invoice(invoice_id):
    invoice = db.session.get(SupplierInvoice, invoice_id)
    if invoice:
        old_status = invoice.status
        invoice.status = 'paid'
        audit = AuditLog(
            company_id=invoice.company_id, user_id=current_user.id,
            action='update', entity_type='supplier_invoice', entity_id=invoice.id,
            old_values={'status': old_status}, new_values={'status': 'paid'},
        )
        db.session.add(audit)
        db.session.commit()
        flash('Fakturan har markerats som betald.', 'success')
    return redirect(url_for('invoices.supplier_invoices'))


# === Customers ===

@invoices_bp.route('/customers')
@login_required
def customers():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    customers = Customer.query.filter_by(company_id=company_id, active=True).order_by(Customer.name).all()
    return render_template('invoices/customers.html', customers=customers)


@invoices_bp.route('/customers/new', methods=['GET', 'POST'])
@login_required
def new_customer():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    form = CustomerForm()
    if form.validate_on_submit():
        customer = Customer(
            company_id=company_id,
            name=form.name.data,
            org_number=form.org_number.data,
            country=form.country.data,
            vat_number=form.vat_number.data,
            address=form.address.data,
            postal_code=form.postal_code.data,
            city=form.city.data,
            email=form.email.data,
            payment_terms=int(form.payment_terms.data or 30),
            default_currency=form.default_currency.data,
        )
        db.session.add(customer)
        db.session.commit()
        flash(f'Kund {customer.name} har skapats.', 'success')
        return redirect(url_for('invoices.customers'))

    return render_template('invoices/new_customer.html', form=form)


# === Customer Invoices ===

@invoices_bp.route('/customer-invoices')
@login_required
def customer_invoices():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    status = request.args.get('status', '')
    query = CustomerInvoice.query.filter_by(company_id=company_id)
    if status:
        query = query.filter_by(status=status)
    invoices = query.order_by(CustomerInvoice.invoice_date.desc()).all()

    return render_template('invoices/customer_invoices.html', invoices=invoices, status=status)


@invoices_bp.route('/customer-invoices/new', methods=['GET', 'POST'])
@login_required
def new_customer_invoice():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    form = CustomerInvoiceForm()
    cust_list = Customer.query.filter_by(company_id=company_id, active=True).order_by(Customer.name).all()
    form.customer_id.choices = [(c.id, c.name) for c in cust_list]

    if form.validate_on_submit():
        invoice = CustomerInvoice(
            company_id=company_id,
            customer_id=form.customer_id.data,
            invoice_number=form.invoice_number.data,
            invoice_date=form.invoice_date.data,
            due_date=form.due_date.data,
            currency=form.currency.data,
            amount_excl_vat=form.amount_excl_vat.data,
            vat_amount=form.vat_amount.data,
            total_amount=form.total_amount.data,
            vat_type=form.vat_type.data,
            status='draft',
        )
        db.session.add(invoice)
        db.session.commit()
        flash('Kundfaktura har skapats.', 'success')
        return redirect(url_for('invoices.customer_invoices'))

    return render_template('invoices/new_customer_invoice.html', form=form)


@invoices_bp.route('/customer-invoices/<int:invoice_id>/send', methods=['POST'])
@login_required
def send_customer_invoice(invoice_id):
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if invoice:
        invoice.status = 'sent'
        from datetime import datetime, timezone
        invoice.sent_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('Fakturan har markerats som skickad.', 'success')
    return redirect(url_for('invoices.customer_invoices'))


@invoices_bp.route('/customer-invoices/<int:invoice_id>/mark-paid', methods=['POST'])
@login_required
def mark_customer_invoice_paid(invoice_id):
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if invoice:
        invoice.status = 'paid'
        from datetime import datetime, timezone
        invoice.paid_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('Fakturan har markerats som betald.', 'success')
    return redirect(url_for('invoices.customer_invoices'))
