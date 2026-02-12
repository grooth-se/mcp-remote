from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.models.accounting import FiscalYear, Account
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice, InvoiceLineItem
from app.models.bank import BankAccount
from app.models.audit import AuditLog
from app.forms.invoice import (SupplierForm, SupplierInvoiceForm, CustomerForm,
                                CustomerInvoiceForm, InvoiceLineItemForm)
from app.services import document_service
from app.services.accounting_service import create_verification
from app.services.invoice_pdf_service import create_customer_invoice_verification
from app.utils.currency import calculate_fx_gain_loss

invoices_bp = Blueprint('invoices', __name__)


# === Suppliers ===

@invoices_bp.route('/suppliers')
@login_required
def suppliers():
    company_id = session.get('active_company_id')
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = Supplier.query.filter_by(company_id=company_id, active=True)
    if search:
        query = query.filter(
            db.or_(Supplier.name.ilike(f'%{search}%'), Supplier.org_number.ilike(f'%{search}%'))
        )
    pagination = query.order_by(Supplier.name).paginate(page=page, per_page=25, error_out=False)
    return render_template('invoices/suppliers.html', pagination=pagination, search=search)


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
            default_currency=form.default_currency.data,
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


# === Supplier Invoice PDF Analysis ===

@invoices_bp.route('/api/analyze-invoice-pdf', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def api_analyze_invoice_pdf():
    """Analyze uploaded invoice PDF, return extracted fields as JSON."""
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'error': 'Inget företag valt'}), 400

    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Ingen fil'}), 400

    result = document_service.analyze_invoice_pdf(file)

    # Try to match supplier by org_number
    if result.get('org_number'):
        supplier = Supplier.query.filter_by(
            company_id=company_id, active=True
        ).filter(Supplier.org_number.ilike(f'%{result["org_number"]}%')).first()
        if supplier:
            result['supplier_id'] = supplier.id
            result['supplier_name'] = supplier.name

    return jsonify(result)


# === Supplier Invoices ===

@invoices_bp.route('/supplier-invoices')
@login_required
def supplier_invoices():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('companies.index'))

    status = request.args.get('status', '')
    if status and status not in ('pending', 'approved', 'paid', 'cancelled'):
        status = ''
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = SupplierInvoice.query.filter_by(company_id=company_id)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.join(Supplier).filter(
            db.or_(SupplierInvoice.invoice_number.ilike(f'%{search}%'), Supplier.name.ilike(f'%{search}%'))
        )
    pagination = query.order_by(SupplierInvoice.due_date.desc()).paginate(page=page, per_page=25, error_out=False)

    return render_template('invoices/supplier_invoices.html', pagination=pagination, status=status, search=search)


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
        supplier = db.session.get(Supplier, form.supplier_id.data)
        currency = form.currency.data
        is_foreign = currency != 'SEK'

        # Determine exchange rate
        ex_rate = Decimal('1.0')
        if is_foreign:
            if form.exchange_rate.data and form.exchange_rate.data != Decimal('1.0'):
                ex_rate = Decimal(str(form.exchange_rate.data))
            else:
                # Try to fetch rate from Riksbanken
                try:
                    from app.services.exchange_rate_service import get_rate
                    ex_rate = get_rate(currency, form.invoice_date.data)
                except (ValueError, Exception):
                    flash(f'Kunde inte hämta växelkurs för {currency}. Ange manuellt.', 'warning')
                    return render_template('invoices/new_supplier_invoice.html', form=form)

        total_foreign = Decimal(str(form.total_amount.data or 0))
        amount_sek = (total_foreign * ex_rate).quantize(Decimal('0.01')) if is_foreign else total_foreign

        invoice = SupplierInvoice(
            company_id=company_id,
            supplier_id=form.supplier_id.data,
            invoice_number=form.invoice_number.data,
            invoice_date=form.invoice_date.data,
            due_date=form.due_date.data,
            amount_excl_vat=form.amount_excl_vat.data,
            vat_amount=form.vat_amount.data,
            total_amount=form.total_amount.data,
            currency=currency,
            exchange_rate=ex_rate,
            amount_sek=amount_sek,
            status='pending',
        )
        db.session.add(invoice)
        db.session.flush()

        # Handle PDF upload
        uploaded_doc = None
        pdf_file = request.files.get('invoice_pdf')
        if pdf_file and pdf_file.filename:
            doc, error = document_service.upload_document(
                company_id=company_id,
                file=pdf_file,
                doc_type='faktura',
                description=f'Leverantörsfaktura {form.invoice_number.data}',
                invoice_id=invoice.id,
                user_id=current_user.id,
            )
            if doc:
                invoice.document_id = doc.id
                uploaded_doc = doc

        # Auto-create accounting verification (all amounts in SEK)
        fy = FiscalYear.query.filter_by(
            company_id=company_id, status='open'
        ).order_by(FiscalYear.year.desc()).first()

        if fy:
            expense_num = (supplier.default_account if supplier and supplier.default_account
                           else '4000')
            expense_acct = Account.query.filter_by(
                company_id=company_id, account_number=expense_num).first()
            vat_acct = Account.query.filter_by(
                company_id=company_id, account_number='2640').first()
            payable_acct = Account.query.filter_by(
                company_id=company_id, account_number='2440').first()

            if expense_acct and payable_acct:
                rows = []
                excl_foreign = Decimal(str(form.amount_excl_vat.data or 0))
                vat_foreign = Decimal(str(form.vat_amount.data or 0))

                # Convert to SEK
                excl_sek = (excl_foreign * ex_rate).quantize(Decimal('0.01')) if is_foreign else excl_foreign
                vat_sek = (vat_foreign * ex_rate).quantize(Decimal('0.01')) if is_foreign else vat_foreign

                # Handle öresavrundning — adjust expense to balance
                rounding = amount_sek - (excl_sek + vat_sek)
                adjusted_excl_sek = excl_sek + rounding

                # Currency metadata for audit trail
                fx_meta = {}
                if is_foreign:
                    fx_meta = {
                        'currency': currency,
                        'exchange_rate': str(ex_rate),
                    }

                rows.append({
                    'account_id': expense_acct.id,
                    'debit': adjusted_excl_sek,
                    'credit': Decimal('0'),
                    'description': form.invoice_number.data,
                    'foreign_amount_debit': excl_foreign if is_foreign else None,
                    **fx_meta,
                })
                if vat_sek > 0 and vat_acct:
                    rows.append({
                        'account_id': vat_acct.id,
                        'debit': vat_sek,
                        'credit': Decimal('0'),
                        'description': 'Ingående moms',
                        'foreign_amount_debit': vat_foreign if is_foreign else None,
                        **fx_meta,
                    })
                rows.append({
                    'account_id': payable_acct.id,
                    'debit': Decimal('0'),
                    'credit': amount_sek,
                    'description': form.invoice_number.data,
                    'foreign_amount_credit': total_foreign if is_foreign else None,
                    **fx_meta,
                })

                try:
                    supplier_name = supplier.name if supplier else ''
                    cur_label = f' ({currency})' if is_foreign else ''
                    ver = create_verification(
                        company_id=company_id,
                        fiscal_year_id=fy.id,
                        verification_date=form.invoice_date.data,
                        description=f'Lev.faktura {form.invoice_number.data} — {supplier_name}{cur_label}',
                        rows=rows,
                        verification_type='supplier',
                        created_by=current_user.id,
                        source='supplier_invoice',
                    )
                    invoice.verification_id = ver.id
                    if uploaded_doc:
                        uploaded_doc.verification_id = ver.id
                    db.session.commit()
                except ValueError as e:
                    db.session.commit()
                    flash(f'Faktura sparad, men verifikation kunde inte skapas: {e}', 'warning')
            else:
                db.session.commit()
                flash('Faktura sparad. Konton 4000/2440 saknas — ingen verifikation skapades.', 'warning')
        else:
            db.session.commit()
            flash('Faktura sparad. Inget öppet räkenskapsår — ingen verifikation skapades.', 'warning')

        flash('Leverantörsfaktura har skapats.', 'success')
        return redirect(url_for('invoices.supplier_invoices'))

    return render_template('invoices/new_supplier_invoice.html', form=form)


@invoices_bp.route('/supplier-invoices/<int:invoice_id>/approve', methods=['POST'])
@login_required
def approve_supplier_invoice(invoice_id):
    company_id = session.get('active_company_id')
    invoice = db.session.get(SupplierInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.supplier_invoices'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('invoices.supplier_invoices'))
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
    company_id = session.get('active_company_id')
    invoice = db.session.get(SupplierInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.supplier_invoices'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('invoices.supplier_invoices'))
    if invoice:
        old_status = invoice.status
        invoice.status = 'paid'
        from datetime import datetime, timezone
        invoice.paid_at = datetime.now(timezone.utc)

        audit = AuditLog(
            company_id=invoice.company_id, user_id=current_user.id,
            action='update', entity_type='supplier_invoice', entity_id=invoice.id,
            old_values={'status': old_status}, new_values={'status': 'paid'},
        )
        db.session.add(audit)

        # Auto-create payment verification
        company_id = invoice.company_id
        fy = FiscalYear.query.filter_by(
            company_id=company_id, status='open'
        ).order_by(FiscalYear.year.desc()).first()

        if fy and invoice.total_amount:
            payable_acct = Account.query.filter_by(
                company_id=company_id, account_number='2440').first()

            # Use bank account's ledger account, default to 1930
            bank_account = BankAccount.query.filter_by(company_id=company_id).first()
            bank_num = bank_account.ledger_account if bank_account else '1930'
            bank_acct = Account.query.filter_by(
                company_id=company_id, account_number=bank_num).first()

            if payable_acct and bank_acct:
                is_foreign = invoice.currency and invoice.currency != 'SEK'
                invoice_sek = Decimal(str(invoice.amount_sek or invoice.total_amount))

                if is_foreign:
                    # Get payment-date rate
                    try:
                        from app.services.exchange_rate_service import get_rate
                        payment_rate = get_rate(invoice.currency, invoice.paid_at.date())
                    except (ValueError, Exception):
                        payment_rate = Decimal(str(invoice.exchange_rate or 1))

                    total_foreign = Decimal(str(invoice.total_amount))
                    payment_sek = (total_foreign * payment_rate).quantize(Decimal('0.01'))
                    fx_diff = calculate_fx_gain_loss(invoice_sek, payment_sek)
                else:
                    payment_sek = invoice_sek
                    fx_diff = Decimal('0')

                rows = [
                    {'account_id': payable_acct.id, 'debit': invoice_sek, 'credit': Decimal('0'),
                     'description': invoice.invoice_number},
                    {'account_id': bank_acct.id, 'debit': Decimal('0'), 'credit': payment_sek,
                     'description': invoice.invoice_number},
                ]

                # FX gain/loss row
                if abs(fx_diff) >= Decimal('0.01'):
                    if fx_diff > 0:
                        # Loss: paid more SEK → debit 6991
                        fx_acct = Account.query.filter_by(
                            company_id=company_id, account_number='6991').first()
                        if not fx_acct:
                            fx_acct = Account(company_id=company_id, account_number='6991',
                                              name='Valutakursförluster', account_type='expense')
                            db.session.add(fx_acct)
                            db.session.flush()
                        rows.append({
                            'account_id': fx_acct.id,
                            'debit': abs(fx_diff), 'credit': Decimal('0'),
                            'description': f'Kursförlust {invoice.currency}',
                        })
                    else:
                        # Gain: paid less SEK → credit 3960
                        fx_acct = Account.query.filter_by(
                            company_id=company_id, account_number='3960').first()
                        if not fx_acct:
                            fx_acct = Account(company_id=company_id, account_number='3960',
                                              name='Valutakursvinster', account_type='revenue')
                            db.session.add(fx_acct)
                            db.session.flush()
                        rows.append({
                            'account_id': fx_acct.id,
                            'debit': Decimal('0'), 'credit': abs(fx_diff),
                            'description': f'Kursvinst {invoice.currency}',
                        })

                try:
                    ver = create_verification(
                        company_id=company_id,
                        fiscal_year_id=fy.id,
                        verification_date=invoice.paid_at.date(),
                        description=f'Betalning lev.faktura {invoice.invoice_number}',
                        rows=rows,
                        verification_type='bank',
                        created_by=current_user.id,
                        source='supplier_invoice_payment',
                    )
                    invoice.payment_verification_id = ver.id
                except ValueError as e:
                    flash(f'Betalningsverifikation kunde inte skapas: {e}', 'warning')
            else:
                flash('Konto 2440 eller bankkonto saknas — ingen betalningsverifikation skapades.', 'warning')
        elif not fy:
            flash('Inget öppet räkenskapsår — ingen betalningsverifikation skapades.', 'warning')

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

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = Customer.query.filter_by(company_id=company_id, active=True)
    if search:
        query = query.filter(
            db.or_(Customer.name.ilike(f'%{search}%'), Customer.org_number.ilike(f'%{search}%'))
        )
    pagination = query.order_by(Customer.name).paginate(page=page, per_page=25, error_out=False)
    return render_template('invoices/customers.html', pagination=pagination, search=search)


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
    if status and status not in ('draft', 'sent', 'paid', 'overdue', 'cancelled'):
        status = ''
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = CustomerInvoice.query.filter_by(company_id=company_id)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.join(Customer).filter(
            db.or_(CustomerInvoice.invoice_number.ilike(f'%{search}%'), Customer.name.ilike(f'%{search}%'))
        )
    pagination = query.order_by(CustomerInvoice.invoice_date.desc()).paginate(page=page, per_page=25, error_out=False)

    return render_template('invoices/customer_invoices.html', pagination=pagination, status=status, search=search)


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
        currency = form.currency.data
        is_foreign = currency != 'SEK'

        # Determine exchange rate
        ex_rate = Decimal('1.0')
        if is_foreign:
            if form.exchange_rate.data and form.exchange_rate.data != Decimal('1.0'):
                ex_rate = Decimal(str(form.exchange_rate.data))
            else:
                try:
                    from app.services.exchange_rate_service import get_rate
                    ex_rate = get_rate(currency, form.invoice_date.data)
                except (ValueError, Exception):
                    flash(f'Kunde inte hämta växelkurs för {currency}. Ange manuellt.', 'warning')
                    return render_template('invoices/new_customer_invoice.html', form=form)

        total_foreign = Decimal(str(form.total_amount.data or 0))
        amount_sek = (total_foreign * ex_rate).quantize(Decimal('0.01')) if is_foreign else total_foreign

        invoice = CustomerInvoice(
            company_id=company_id,
            customer_id=form.customer_id.data,
            invoice_number=form.invoice_number.data,
            invoice_date=form.invoice_date.data,
            due_date=form.due_date.data,
            currency=currency,
            exchange_rate=ex_rate,
            amount_sek=amount_sek,
            amount_excl_vat=form.amount_excl_vat.data,
            vat_amount=form.vat_amount.data,
            total_amount=form.total_amount.data,
            vat_type=form.vat_type.data,
            status='draft',
        )
        db.session.add(invoice)
        db.session.flush()

        # Auto-create accounting verification
        fy = FiscalYear.query.filter_by(
            company_id=company_id, status='open'
        ).order_by(FiscalYear.year.desc()).first()

        if fy:
            ver, reason = create_customer_invoice_verification(
                invoice, company_id, fy.id, created_by=current_user.id)
            if ver:
                db.session.commit()
            else:
                db.session.commit()
                flash(f'Faktura sparad, men verifikation kunde inte skapas: {reason}', 'warning')
        else:
            db.session.commit()
            flash('Faktura sparad. Inget öppet räkenskapsår — ingen verifikation skapades.', 'warning')

        flash('Kundfaktura har skapats.', 'success')
        return redirect(url_for('invoices.customer_invoices'))

    return render_template('invoices/new_customer_invoice.html', form=form)


@invoices_bp.route('/customer-invoices/<int:invoice_id>/send', methods=['POST'])
@login_required
def send_customer_invoice(invoice_id):
    company_id = session.get('active_company_id')
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
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
    company_id = session.get('active_company_id')
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
    if invoice:
        invoice.status = 'paid'
        from datetime import datetime, timezone
        invoice.paid_at = datetime.now(timezone.utc)

        # Auto-create payment verification
        company_id = invoice.company_id
        fy = FiscalYear.query.filter_by(
            company_id=company_id, status='open'
        ).order_by(FiscalYear.year.desc()).first()

        if fy and invoice.total_amount:
            receivable_acct = Account.query.filter_by(
                company_id=company_id, account_number='1510').first()

            bank_account = BankAccount.query.filter_by(company_id=company_id).first()
            bank_num = bank_account.ledger_account if bank_account else '1930'
            bank_acct = Account.query.filter_by(
                company_id=company_id, account_number=bank_num).first()

            if receivable_acct and bank_acct:
                is_foreign = invoice.currency and invoice.currency != 'SEK'
                invoice_sek = Decimal(str(invoice.amount_sek or invoice.total_amount))

                if is_foreign:
                    try:
                        from app.services.exchange_rate_service import get_rate
                        payment_rate = get_rate(invoice.currency, invoice.paid_at.date())
                    except (ValueError, Exception):
                        payment_rate = Decimal(str(invoice.exchange_rate or 1))

                    total_foreign = Decimal(str(invoice.total_amount))
                    payment_sek = (total_foreign * payment_rate).quantize(Decimal('0.01'))
                    fx_diff = calculate_fx_gain_loss(invoice_sek, payment_sek)
                else:
                    payment_sek = invoice_sek
                    fx_diff = Decimal('0')

                rows = [
                    {'account_id': bank_acct.id, 'debit': payment_sek, 'credit': Decimal('0'),
                     'description': invoice.invoice_number},
                    {'account_id': receivable_acct.id, 'debit': Decimal('0'), 'credit': invoice_sek,
                     'description': invoice.invoice_number},
                ]

                # FX gain/loss row
                if abs(fx_diff) >= Decimal('0.01'):
                    if fx_diff > 0:
                        # Received more SEK than booked → credit 3960 (gain)
                        fx_acct = Account.query.filter_by(
                            company_id=company_id, account_number='3960').first()
                        if not fx_acct:
                            fx_acct = Account(company_id=company_id, account_number='3960',
                                              name='Valutakursvinster', account_type='revenue')
                            db.session.add(fx_acct)
                            db.session.flush()
                        rows.append({
                            'account_id': fx_acct.id,
                            'debit': Decimal('0'), 'credit': abs(fx_diff),
                            'description': f'Kursvinst {invoice.currency}',
                        })
                    else:
                        # Received less SEK than booked → debit 6991 (loss)
                        fx_acct = Account.query.filter_by(
                            company_id=company_id, account_number='6991').first()
                        if not fx_acct:
                            fx_acct = Account(company_id=company_id, account_number='6991',
                                              name='Valutakursförluster', account_type='expense')
                            db.session.add(fx_acct)
                            db.session.flush()
                        rows.append({
                            'account_id': fx_acct.id,
                            'debit': abs(fx_diff), 'credit': Decimal('0'),
                            'description': f'Kursförlust {invoice.currency}',
                        })

                try:
                    ver = create_verification(
                        company_id=company_id,
                        fiscal_year_id=fy.id,
                        verification_date=invoice.paid_at.date(),
                        description=f'Betalning kundfaktura {invoice.invoice_number}',
                        rows=rows,
                        verification_type='customer',
                        created_by=current_user.id,
                        source='customer_invoice_payment',
                    )
                    invoice.payment_verification_id = ver.id
                except ValueError as e:
                    flash(f'Betalningsverifikation kunde inte skapas: {e}', 'warning')
            else:
                flash('Konto 1510 eller bankkonto saknas — ingen betalningsverifikation skapades.', 'warning')
        elif not fy:
            flash('Inget öppet räkenskapsår — ingen betalningsverifikation skapades.', 'warning')

        db.session.commit()
        flash('Fakturan har markerats som betald.', 'success')
    return redirect(url_for('invoices.customer_invoices'))


# === Customer Invoice Detail + Line Items (Phase 4F) ===

@invoices_bp.route('/customer-invoices/<int:invoice_id>')
@login_required
def customer_invoice_detail(invoice_id):
    company_id = session.get('active_company_id')
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))

    form = InvoiceLineItemForm()
    return render_template('invoices/customer_invoice_detail.html',
                           invoice=invoice, form=form)


@invoices_bp.route('/customer-invoices/<int:invoice_id>/add-line', methods=['POST'])
@login_required
def add_line_item(invoice_id):
    company_id = session.get('active_company_id')
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        return redirect(url_for('invoices.customer_invoices'))

    form = InvoiceLineItemForm()
    if form.validate_on_submit():
        from app.services.invoice_pdf_service import add_line_item as svc_add_line
        svc_add_line(
            invoice_id=invoice_id,
            description=form.description.data,
            quantity=form.quantity.data,
            unit_price=form.unit_price.data,
            vat_rate=int(form.vat_rate.data),
            unit=form.unit.data,
        )
        flash('Rad har lagts till.', 'success')

    return redirect(url_for('invoices.customer_invoice_detail', invoice_id=invoice_id))


@invoices_bp.route('/customer-invoices/<int:invoice_id>/lines/<int:line_id>/delete', methods=['POST'])
@login_required
def delete_line_item(invoice_id, line_id):
    company_id = session.get('active_company_id')
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('invoices.customer_invoice_detail', invoice_id=invoice_id))
    from app.services.invoice_pdf_service import remove_line_item
    remove_line_item(line_id)
    flash('Rad har tagits bort.', 'success')
    return redirect(url_for('invoices.customer_invoice_detail', invoice_id=invoice_id))


@invoices_bp.route('/customer-invoices/<int:invoice_id>/preview')
@login_required
def preview_invoice_pdf(invoice_id):
    company_id = session.get('active_company_id')
    invoice = db.session.get(CustomerInvoice, invoice_id)
    if not invoice or invoice.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
    from app.services.invoice_pdf_service import generate_invoice_pdf, get_invoice_pdf_path

    path = get_invoice_pdf_path(invoice_id)
    if not path:
        # Generate it first
        result = generate_invoice_pdf(invoice_id)
        if isinstance(result, str) and result.endswith('.pdf'):
            path = result
        else:
            # weasyprint not available, return HTML
            return result

    import os
    if path and os.path.exists(path):
        return send_file(path, mimetype='application/pdf')
    else:
        flash('Kunde inte generera PDF.', 'danger')
        return redirect(url_for('invoices.customer_invoice_detail', invoice_id=invoice_id))


@invoices_bp.route('/customer-invoices/<int:invoice_id>/pdf')
@login_required
def download_invoice_pdf(invoice_id):
    company_id = session.get('active_company_id')
    invoice_obj = db.session.get(CustomerInvoice, invoice_id)
    if not invoice_obj or invoice_obj.company_id != company_id:
        flash('Faktura hittades inte.', 'danger')
        return redirect(url_for('invoices.customer_invoices'))
    from app.services.invoice_pdf_service import generate_invoice_pdf, get_invoice_pdf_path

    path = get_invoice_pdf_path(invoice_id)
    if not path:
        result = generate_invoice_pdf(invoice_id)
        if isinstance(result, str) and result.endswith('.pdf'):
            path = result

    import os
    if path and os.path.exists(path):
        invoice = db.session.get(CustomerInvoice, invoice_id)
        return send_file(path, as_attachment=True,
                         download_name=f'{invoice.invoice_number}.pdf',
                         mimetype='application/pdf')
    else:
        flash('Kunde inte generera PDF.', 'danger')
        return redirect(url_for('invoices.customer_invoice_detail', invoice_id=invoice_id))
