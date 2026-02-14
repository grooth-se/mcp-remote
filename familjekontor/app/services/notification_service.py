"""Notification center service (Phase 7B)."""

from datetime import date, timedelta

from flask import url_for

from app.extensions import db
from app.models.notification import Notification


def generate_notifications(user_id, company_id):
    """Check all conditions and create new notifications. Returns count created."""
    count = 0
    count += len(_check_overdue_invoices(user_id, company_id))
    count += len(_check_upcoming_deadlines(user_id, company_id))
    count += len(_check_document_expiry(user_id, company_id))
    count += len(_check_budget_variance(user_id, company_id))
    count += len(_check_fy_closing(user_id, company_id))
    if count > 0:
        db.session.commit()
    return count


def get_unread_count(user_id, company_id):
    """Return count of unread notifications."""
    return Notification.query.filter_by(
        user_id=user_id, company_id=company_id, read=False
    ).count()


def get_recent_notifications(user_id, company_id, limit=10):
    """Return recent notifications (unread first, then by date)."""
    return (
        Notification.query
        .filter_by(user_id=user_id, company_id=company_id)
        .order_by(Notification.read.asc(), Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def get_all_notifications(user_id, company_id, page=1, per_page=25,
                          filter_type=None, filter_read=None):
    """Paginated list of all notifications with optional filters."""
    q = Notification.query.filter_by(user_id=user_id, company_id=company_id)
    if filter_type:
        q = q.filter_by(notification_type=filter_type)
    if filter_read is not None:
        q = q.filter_by(read=filter_read)
    return q.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )


def mark_as_read(notification_id, user_id):
    """Mark single notification as read. Returns True if found and updated."""
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return False
    n.read = True
    db.session.commit()
    return True


def mark_all_read(user_id, company_id):
    """Mark all unread notifications as read. Returns count updated."""
    count = Notification.query.filter_by(
        user_id=user_id, company_id=company_id, read=False
    ).update({'read': True})
    db.session.commit()
    return count


# ---------------------------------------------------------------------------
# Internal checkers — deduplicate by entity_type + entity_id + type
# ---------------------------------------------------------------------------

def _exists(user_id, company_id, notification_type, entity_type, entity_id):
    """Check if an unread notification already exists for this entity."""
    return Notification.query.filter_by(
        user_id=user_id, company_id=company_id,
        notification_type=notification_type,
        entity_type=entity_type, entity_id=entity_id,
        read=False,
    ).first() is not None


def _check_overdue_invoices(user_id, company_id):
    """Create notifications for unpaid supplier invoices past due_date."""
    from app.models.invoice import SupplierInvoice
    today = date.today()
    overdue = SupplierInvoice.query.filter(
        SupplierInvoice.company_id == company_id,
        SupplierInvoice.status.in_(['pending', 'approved']),
        SupplierInvoice.due_date < today,
    ).all()

    created = []
    for inv in overdue:
        if _exists(user_id, company_id, 'overdue_invoice',
                   'supplier_invoice', inv.id):
            continue
        days = (today - inv.due_date).days
        n = Notification(
            user_id=user_id, company_id=company_id,
            notification_type='overdue_invoice',
            title=f'Förfallen faktura: {inv.invoice_number or inv.id}',
            message=f'{days} dagar förfallen. Belopp: {inv.total_amount} kr',
            link=url_for('invoices.supplier_invoices'),
            icon='bi-exclamation-triangle-fill',
            entity_type='supplier_invoice', entity_id=inv.id,
        )
        db.session.add(n)
        created.append(n)
    return created


def _check_upcoming_deadlines(user_id, company_id, days_ahead=7):
    """Create notifications for tax deadlines within N days."""
    from app.models.tax import Deadline
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    deadlines = Deadline.query.filter(
        Deadline.company_id == company_id,
        Deadline.due_date >= today,
        Deadline.due_date <= cutoff,
        Deadline.status != 'completed',
    ).all()

    created = []
    for dl in deadlines:
        if _exists(user_id, company_id, 'upcoming_deadline',
                   'deadline', dl.id):
            continue
        days = (dl.due_date - today).days
        n = Notification(
            user_id=user_id, company_id=company_id,
            notification_type='upcoming_deadline',
            title=f'Deadline om {days} dagar: {dl.description or dl.deadline_type}',
            message=f'Förfaller {dl.due_date.strftime("%Y-%m-%d")}',
            link=url_for('tax.deadlines_index'),
            icon='bi-calendar-event',
            entity_type='deadline', entity_id=dl.id,
        )
        db.session.add(n)
        created.append(n)
    return created


def _check_document_expiry(user_id, company_id, days_ahead=30):
    """Create notifications for documents with expiry_date approaching."""
    from app.models.document import Document
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    docs = Document.query.filter(
        Document.company_id == company_id,
        Document.expiry_date != None,  # noqa: E711
        Document.expiry_date >= today,
        Document.expiry_date <= cutoff,
    ).all()

    created = []
    for doc in docs:
        if _exists(user_id, company_id, 'document_expiry',
                   'document', doc.id):
            continue
        days = (doc.expiry_date - today).days
        n = Notification(
            user_id=user_id, company_id=company_id,
            notification_type='document_expiry',
            title=f'Dokument upphör snart: {doc.file_name or doc.id}',
            message=f'Upphör om {days} dagar ({doc.expiry_date.strftime("%Y-%m-%d")})',
            link=url_for('documents.view', doc_id=doc.id),
            icon='bi-file-earmark-x',
            entity_type='document', entity_id=doc.id,
        )
        db.session.add(n)
        created.append(n)
    return created


def _check_budget_variance(user_id, company_id, threshold=20.0):
    """Create notifications for accounts with budget variance exceeding threshold %."""
    from app.models.budget import BudgetLine
    from app.models.accounting import FiscalYear, Account, VerificationRow
    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).first()
    if not fy:
        return []

    # Sum budget per account
    budget_sums = db.session.query(
        BudgetLine.account_id,
        db.func.sum(BudgetLine.amount).label('total_budget'),
    ).filter_by(
        company_id=company_id, fiscal_year_id=fy.id,
    ).group_by(BudgetLine.account_id).all()

    created = []
    for account_id, total_budget in budget_sums:
        if not total_budget or total_budget == 0:
            continue

        # Get actual from verification rows
        actual = db.session.query(
            db.func.coalesce(
                db.func.sum(VerificationRow.debit - VerificationRow.credit), 0
            )
        ).filter(
            VerificationRow.account_id == account_id,
            VerificationRow.verification.has(fiscal_year_id=fy.id),
        ).scalar() or 0

        variance_pct = abs(float(actual - total_budget) / float(total_budget)) * 100
        if variance_pct > threshold:
            if _exists(user_id, company_id, 'budget_variance',
                       'account', account_id):
                continue
            acct = db.session.get(Account, account_id)
            acct_num = acct.account_number if acct else str(account_id)
            n = Notification(
                user_id=user_id, company_id=company_id,
                notification_type='budget_variance',
                title=f'Budgetavvikelse: konto {acct_num}',
                message=f'Avvikelse {variance_pct:.0f}% (budget: {total_budget}, utfall: {actual})',
                link=url_for('budget.variance'),
                icon='bi-graph-down-arrow',
                entity_type='account', entity_id=account_id,
            )
            db.session.add(n)
            created.append(n)
    return created


def _check_fy_closing(user_id, company_id):
    """Create notification if in last month of open fiscal year."""
    from app.models.accounting import FiscalYear
    today = date.today()
    fy = FiscalYear.query.filter_by(
        company_id=company_id, status='open'
    ).first()
    if not fy:
        return []

    days_left = (fy.end_date - today).days
    if days_left < 0 or days_left > 30:
        return []

    if _exists(user_id, company_id, 'fy_closing_reminder',
               'fiscal_year', fy.id):
        return []

    n = Notification(
        user_id=user_id, company_id=company_id,
        notification_type='fy_closing_reminder',
        title=f'Räkenskapsåret {fy.year} avslutas snart',
        message=f'{days_left} dagar kvar till {fy.end_date.strftime("%Y-%m-%d")}',
        link=url_for('closing.index'),
        icon='bi-calendar-check',
        entity_type='fiscal_year', entity_id=fy.id,
    )
    db.session.add(n)
    return [n]
