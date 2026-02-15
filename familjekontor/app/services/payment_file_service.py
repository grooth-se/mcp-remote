"""Payment file generation service — pain.001 XML and Bankgirot format."""

import io
import logging
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models.accounting import Account, FiscalYear, Verification, VerificationRow
from app.models.audit import AuditLog
from app.models.bank import BankAccount
from app.models.invoice import Supplier, SupplierInvoice
from app.models.payment_file import PaymentFile, PaymentInstruction

logger = logging.getLogger(__name__)

PAIN001_NS = 'urn:iso:std:iso:20022:tech:xsd:pain.001.001.03'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def determine_payment_method(supplier):
    """Determine best payment method from supplier's available details.

    Priority: bankgiro > plusgiro > iban.
    Returns (method, account, bic) or (None, None, None).
    """
    if supplier.bankgiro:
        return ('bankgiro', supplier.bankgiro, None)
    if supplier.plusgiro:
        return ('plusgiro', supplier.plusgiro, None)
    if supplier.iban:
        return ('iban', supplier.iban, getattr(supplier, 'bic', None))
    return (None, None, None)


def get_payable_invoices(company_id):
    """Get approved supplier invoices not yet in any active payment batch.

    Returns list of SupplierInvoice objects with status='approved' that are
    NOT linked to any PaymentInstruction in a non-cancelled PaymentFile.
    """
    # Sub-query: invoice IDs already in active batches
    active_instr = (
        db.session.query(PaymentInstruction.supplier_invoice_id)
        .join(PaymentFile)
        .filter(PaymentFile.status.notin_(['cancelled']))
        .subquery()
    )

    return (
        SupplierInvoice.query
        .filter_by(company_id=company_id, status='approved')
        .filter(SupplierInvoice.id.notin_(db.session.query(active_instr)))
        .join(Supplier)
        .order_by(SupplierInvoice.due_date)
        .all()
    )


def get_next_batch_reference(company_id):
    """Generate next sequential batch reference: PAY-YYYY-NNNN."""
    year = date.today().year
    prefix = f'PAY-{year}-'
    last = (
        PaymentFile.query
        .filter_by(company_id=company_id)
        .filter(PaymentFile.batch_reference.like(f'{prefix}%'))
        .order_by(PaymentFile.batch_reference.desc())
        .first()
    )
    if last:
        try:
            seq = int(last.batch_reference.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:04d}'


# ---------------------------------------------------------------------------
# Batch creation
# ---------------------------------------------------------------------------

def create_payment_batch(company_id, bank_account_id, invoice_ids,
                         execution_date, file_format, created_by):
    """Create a PaymentFile with PaymentInstructions for selected invoices.

    Returns (PaymentFile, errors_list).
    """
    errors = []

    bank_account = db.session.get(BankAccount, bank_account_id)
    if not bank_account or bank_account.company_id != company_id:
        errors.append('Ogiltigt bankkonto.')
        return None, errors

    if file_format not in ('pain001', 'bankgirot'):
        errors.append(f'Ogiltigt filformat: {file_format}')
        return None, errors

    invoices = SupplierInvoice.query.filter(
        SupplierInvoice.id.in_(invoice_ids),
        SupplierInvoice.company_id == company_id,
    ).all()

    if len(invoices) != len(invoice_ids):
        errors.append('En eller flera fakturor hittades inte eller tillhör inte företaget.')

    instructions = []
    total = Decimal('0')

    for inv in invoices:
        if inv.status != 'approved':
            errors.append(f'Faktura {inv.invoice_number} är inte godkänd (status: {inv.status}).')
            continue

        method, account, bic = determine_payment_method(inv.supplier)
        if not method:
            errors.append(
                f'Leverantör "{inv.supplier.name}" saknar betalningsuppgifter '
                f'(bankgiro/plusgiro/IBAN).'
            )
            continue

        amount = Decimal(str(inv.total_amount))
        total += amount

        instructions.append(PaymentInstruction(
            supplier_invoice_id=inv.id,
            amount=amount,
            currency=inv.currency or 'SEK',
            payment_method=method,
            creditor_account=account,
            creditor_bic=bic,
            creditor_name=inv.supplier.name,
            remittance_info=inv.invoice_number or '',
            end_to_end_id=(inv.invoice_number or '')[:35],
        ))

    if errors:
        return None, errors

    if not instructions:
        errors.append('Inga giltiga fakturor att betala.')
        return None, errors

    pf = PaymentFile(
        company_id=company_id,
        bank_account_id=bank_account_id,
        batch_reference=get_next_batch_reference(company_id),
        file_format=file_format,
        execution_date=execution_date,
        total_amount=total,
        currency='SEK',
        number_of_transactions=len(instructions),
        created_by=created_by,
    )
    db.session.add(pf)
    db.session.flush()

    for instr in instructions:
        instr.payment_file_id = pf.id
        db.session.add(instr)

    db.session.commit()
    return pf, []


def get_batch_summary(payment_file_id):
    """Get summary data for a batch."""
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf:
        return None

    by_method = {}
    for instr in pf.instructions:
        method = instr.payment_method
        if method not in by_method:
            by_method[method] = {'count': 0, 'total': Decimal('0')}
        by_method[method]['count'] += 1
        by_method[method]['total'] += Decimal(str(instr.amount))

    return {
        'batch_reference': pf.batch_reference,
        'status': pf.status,
        'total_amount': pf.total_amount,
        'number_of_transactions': pf.number_of_transactions,
        'by_method': by_method,
    }


# ---------------------------------------------------------------------------
# File generation — pain.001 XML
# ---------------------------------------------------------------------------

def _sub(parent, tag, text=None):
    """Helper to create XML subelement with optional text."""
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def generate_pain001_xml(payment_file_id):
    """Generate ISO 20022 pain.001.001.03 XML.

    Returns BytesIO with UTF-8 encoded XML.
    """
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf:
        raise ValueError('Betalningsbatch hittades inte.')

    company = pf.company
    bank_acct = pf.bank_account

    ET.register_namespace('', PAIN001_NS)
    doc = ET.Element(f'{{{PAIN001_NS}}}Document')
    root = _sub(doc, f'{{{PAIN001_NS}}}CstmrCdtTrfInitn')

    # Group Header
    grp_hdr = _sub(root, 'GrpHdr')
    _sub(grp_hdr, 'MsgId', pf.batch_reference)
    _sub(grp_hdr, 'CreDtTm', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'))
    _sub(grp_hdr, 'NbOfTxs', str(pf.number_of_transactions))
    _sub(grp_hdr, 'CtrlSum', f'{pf.total_amount:.2f}')

    initg_pty = _sub(grp_hdr, 'InitgPty')
    _sub(initg_pty, 'Nm', company.name)
    if company.org_number:
        id_el = _sub(initg_pty, 'Id')
        org_id = _sub(id_el, 'OrgId')
        othr = _sub(org_id, 'Othr')
        _sub(othr, 'Id', company.org_number.replace('-', ''))

    # Payment Information
    pmt_inf = _sub(root, 'PmtInf')
    _sub(pmt_inf, 'PmtInfId', pf.batch_reference)
    _sub(pmt_inf, 'PmtMtd', 'TRF')
    _sub(pmt_inf, 'NbOfTxs', str(pf.number_of_transactions))
    _sub(pmt_inf, 'CtrlSum', f'{pf.total_amount:.2f}')

    pmt_tp_inf = _sub(pmt_inf, 'PmtTpInf')
    svc_lvl = _sub(pmt_tp_inf, 'SvcLvl')
    _sub(svc_lvl, 'Cd', 'NURG')

    _sub(pmt_inf, 'ReqdExctnDt', pf.execution_date.isoformat())

    # Debtor
    dbtr = _sub(pmt_inf, 'Dbtr')
    _sub(dbtr, 'Nm', company.name)
    pstl = _sub(dbtr, 'PstlAdr')
    _sub(pstl, 'Ctry', 'SE')

    dbtr_acct = _sub(pmt_inf, 'DbtrAcct')
    dbtr_acct_id = _sub(dbtr_acct, 'Id')
    if bank_acct.iban:
        _sub(dbtr_acct_id, 'IBAN', bank_acct.iban.replace(' ', ''))
    else:
        othr = _sub(dbtr_acct_id, 'Othr')
        _sub(othr, 'Id', bank_acct.account_number)

    dbtr_agt = _sub(pmt_inf, 'DbtrAgt')
    fin_inst = _sub(dbtr_agt, 'FinInstnId')
    if bank_acct.bic:
        _sub(fin_inst, 'BIC', bank_acct.bic)
    else:
        _sub(fin_inst, 'Nm', bank_acct.bank_name)

    # Credit Transfer Transactions
    for instr in pf.instructions:
        tx = _sub(pmt_inf, 'CdtTrfTxInf')

        pmt_id = _sub(tx, 'PmtId')
        _sub(pmt_id, 'EndToEndId', instr.end_to_end_id or 'NOTPROVIDED')

        amt = _sub(tx, 'Amt')
        instd = _sub(amt, 'InstdAmt', f'{instr.amount:.2f}')
        instd.set('Ccy', instr.currency or 'SEK')

        # Creditor agent (for IBAN payments)
        if instr.payment_method == 'iban' and instr.creditor_bic:
            cdtr_agt = _sub(tx, 'CdtrAgt')
            cdtr_fin = _sub(cdtr_agt, 'FinInstnId')
            _sub(cdtr_fin, 'BIC', instr.creditor_bic)

        # Creditor
        cdtr = _sub(tx, 'Cdtr')
        _sub(cdtr, 'Nm', instr.creditor_name)

        # Creditor account
        cdtr_acct = _sub(tx, 'CdtrAcct')
        cdtr_acct_id = _sub(cdtr_acct, 'Id')

        if instr.payment_method == 'iban':
            _sub(cdtr_acct_id, 'IBAN', instr.creditor_account.replace(' ', ''))
        else:
            othr = _sub(cdtr_acct_id, 'Othr')
            _sub(othr, 'Id', instr.creditor_account.replace('-', ''))
            schme = _sub(othr, 'SchmeNm')
            if instr.payment_method == 'bankgiro':
                _sub(schme, 'Prtry', 'BGNR')
            else:
                _sub(schme, 'Prtry', 'PGNR')

        # Remittance info
        if instr.remittance_info:
            rmt = _sub(tx, 'RmtInf')
            _sub(rmt, 'Ustrd', instr.remittance_info)

    buf = io.BytesIO()
    tree = ET.ElementTree(doc)
    ET.indent(tree, space='  ')
    tree.write(buf, encoding='utf-8', xml_declaration=True)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# File generation — Bankgirot
# ---------------------------------------------------------------------------

def generate_bankgirot_file(payment_file_id):
    """Generate Bankgirot fixed-width text file (leverantorsbetalningar).

    Returns BytesIO with ISO-8859-1 encoded content.
    """
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf:
        raise ValueError('Betalningsbatch hittades inte.')

    lines = []
    today_str = date.today().strftime('%Y%m%d')
    exec_str = pf.execution_date.strftime('%Y%m%d')

    # Determine sender bankgiro from bank account or company
    sender_bg = ''
    if pf.bank_account.account_number:
        sender_bg = pf.bank_account.account_number.replace('-', '').ljust(10)

    # Record 01 — Opening
    rec01 = f'01{today_str}  LEVERANTORSBETALNINGAR'
    lines.append(rec01.ljust(80))

    # Record 20 — Sender
    rec20 = f'20{sender_bg[:10].ljust(10)}{exec_str}LBOUT'
    lines.append(rec20.ljust(80))

    total_ore = 0
    pay_count = 0

    for instr in pf.instructions:
        if instr.payment_method not in ('bankgiro', 'plusgiro'):
            continue

        creditor_acct = instr.creditor_account.replace('-', '').ljust(10)
        amount_ore = int(Decimal(str(instr.amount)) * 100)
        total_ore += amount_ore
        pay_count += 1

        ref = (instr.remittance_info or '').ljust(25)
        exec_short = pf.execution_date.strftime('%y%m%d')

        # Record 26 — Payment
        rec26 = f'26{creditor_acct[:10]}{ref[:25]}{amount_ore:012d}{exec_short}'
        lines.append(rec26.ljust(80))

    # Record 09 — Closing
    rec09 = f'09{pay_count:08d}{total_ore:012d}'
    lines.append(rec09.ljust(80))

    content = '\n'.join(lines) + '\n'
    buf = io.BytesIO(content.encode('iso-8859-1'))
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# File generation — dispatcher
# ---------------------------------------------------------------------------

def generate_payment_file(payment_file_id):
    """Generate payment file, save to disk, update status.

    Returns file path or None on error.
    """
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf:
        return None

    if pf.status not in ('draft',):
        return None

    if pf.file_format == 'pain001':
        buf = generate_pain001_xml(payment_file_id)
        ext = 'xml'
    elif pf.file_format == 'bankgirot':
        buf = generate_bankgirot_file(payment_file_id)
        ext = 'txt'
    else:
        return None

    # Save file
    from flask import current_app
    base_dir = current_app.config.get('GENERATED_FOLDER', 'data/generated')
    payment_dir = os.path.join(base_dir, 'payments', str(pf.company_id))
    os.makedirs(payment_dir, exist_ok=True)

    filename = f'{pf.batch_reference}.{ext}'
    filepath = os.path.join(payment_dir, filename)

    with open(filepath, 'wb') as f:
        f.write(buf.read())

    pf.file_path = filepath
    pf.status = 'generated'
    db.session.commit()

    return filepath


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

def mark_batch_uploaded(payment_file_id, user_id):
    """Mark batch as uploaded to bank. Status: generated -> uploaded."""
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf or pf.status != 'generated':
        return False
    pf.status = 'uploaded'
    db.session.commit()
    return True


def create_supplier_payment_verification(invoice, user_id, bank_account=None):
    """Create payment verification for a supplier invoice.

    Handles FX gain/loss. Returns Verification or None.
    Extracted from invoices.py for reuse in batch confirm.
    """
    from app.services.accounting_service import create_verification

    company_id = invoice.company_id
    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).order_by(FiscalYear.year.desc()).first()

    if not fy or not invoice.total_amount:
        return None

    payable_acct = Account.query.filter_by(
        company_id=company_id, account_number='2440').first()

    if not bank_account:
        bank_account = BankAccount.query.filter_by(company_id=company_id).first()
    bank_num = bank_account.ledger_account if bank_account else '1930'
    bank_acct = Account.query.filter_by(
        company_id=company_id, account_number=bank_num).first()

    if not payable_acct or not bank_acct:
        return None

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

        from app.utils.currency import calculate_fx_gain_loss
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

    if abs(fx_diff) >= Decimal('0.01'):
        if fx_diff > 0:
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
            created_by=user_id,
            source='supplier_invoice_payment',
        )
        return ver
    except ValueError:
        return None


def confirm_batch_paid(payment_file_id, user_id):
    """Confirm all payments in batch were executed by bank.

    Marks all invoices as paid, creates payment verifications.
    Returns (success, errors).
    """
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf or pf.status not in ('uploaded', 'generated'):
        return False, ['Batch kan inte bekräftas i nuvarande status.']

    errors = []
    now = datetime.now(timezone.utc)

    for instr in pf.instructions:
        invoice = db.session.get(SupplierInvoice, instr.supplier_invoice_id)
        if not invoice:
            errors.append(f'Faktura ID {instr.supplier_invoice_id} hittades inte.')
            continue

        if invoice.status == 'paid':
            instr.status = 'paid'
            continue

        old_status = invoice.status
        invoice.status = 'paid'
        invoice.paid_at = now

        audit = AuditLog(
            company_id=invoice.company_id, user_id=user_id,
            action='update', entity_type='supplier_invoice', entity_id=invoice.id,
            old_values={'status': old_status}, new_values={'status': 'paid'},
        )
        db.session.add(audit)

        ver = create_supplier_payment_verification(
            invoice, user_id, bank_account=pf.bank_account
        )
        if ver:
            invoice.payment_verification_id = ver.id

        instr.status = 'paid'

    pf.status = 'confirmed'
    pf.confirmed_at = now
    pf.confirmed_by = user_id
    db.session.commit()

    return True, errors


def cancel_batch(payment_file_id, user_id):
    """Cancel a batch (only from draft or generated status)."""
    pf = db.session.get(PaymentFile, payment_file_id)
    if not pf or pf.status not in ('draft', 'generated'):
        return False
    pf.status = 'cancelled'
    db.session.commit()
    return True
