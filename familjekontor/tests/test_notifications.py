"""Tests for Notification Center (Phase 7B)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.user import User
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice
from app.models.document import Document
from app.models.tax import Deadline
from app.models.budget import BudgetLine
from app.models.notification import Notification
from app.services.notification_service import (
    generate_notifications, get_unread_count, get_recent_notifications,
    mark_as_read, mark_all_read,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def notif_company(db):
    """Company with data triggering various notification types."""
    co = Company(name='Notif AB', org_number='556900-0077', company_type='AB')
    db.session.add(co)
    db.session.flush()

    today = date.today()
    fy = FiscalYear(
        company_id=co.id, year=today.year,
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.flush()

    # Account for budget variance
    acct = Account(company_id=co.id, account_number='5010', name='Lokalhyra', account_type='expense')
    db.session.add(acct)
    db.session.flush()

    # Overdue supplier invoice (due yesterday)
    sup = Supplier(company_id=co.id, name='Leverantör Test', org_number='556100-9999')
    db.session.add(sup)
    db.session.flush()
    si = SupplierInvoice(
        company_id=co.id, supplier_id=sup.id,
        invoice_number='OVER-001', invoice_date=today - timedelta(days=30),
        due_date=today - timedelta(days=1), total_amount=Decimal('5000'),
        status='pending',
    )
    db.session.add(si)

    # Upcoming tax deadline (in 3 days)
    dl = Deadline(
        company_id=co.id, deadline_type='moms',
        description='Momsdeklaration', due_date=today + timedelta(days=3),
        status='pending',
    )
    db.session.add(dl)

    # Document expiring in 10 days
    doc = Document(
        company_id=co.id, file_name='avtal.pdf',
        expiry_date=today + timedelta(days=10),
    )
    db.session.add(doc)

    # Budget lines with large variance (12 months, 10k/month = 120k total)
    for m in range(1, 13):
        bl = BudgetLine(
            company_id=co.id, fiscal_year_id=fy.id,
            account_id=acct.id, period_month=m, amount=Decimal('10000'),
        )
        db.session.add(bl)

    # Actual spending far exceeding budget — create verification
    v = Verification(
        company_id=co.id, fiscal_year_id=fy.id,
        verification_number=1, verification_date=today - timedelta(days=5),
    )
    db.session.add(v)
    db.session.flush()
    db.session.add(VerificationRow(
        verification_id=v.id, account_id=acct.id,
        debit=Decimal('150000'), credit=Decimal('0'),
    ))

    db.session.commit()

    user = User.query.filter_by(username='admin').first()
    if not user:
        user = User(username='notif_admin', email='notif@test.com', role='admin')
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()

    return {
        'company': co, 'fy': fy, 'user': user,
        'supplier_invoice': si, 'deadline': dl, 'document': doc,
        'account': acct,
    }


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestNotificationModel:
    def test_creation(self, app, db, notif_company):
        with app.app_context():
            d = notif_company
            n = Notification(
                user_id=d['user'].id, company_id=d['company'].id,
                notification_type='info', title='Test avisering',
                message='Testmeddelande', icon='bi-info-circle',
            )
            db.session.add(n)
            db.session.commit()
            assert n.id is not None
            assert n.read is False
            assert repr(n) == '<Notification Test avisering (info)>'


# ---------------------------------------------------------------------------
# Generator Tests
# ---------------------------------------------------------------------------

class TestNotificationGenerators:
    def test_generate_overdue_invoices(self, app, notif_company):
        with app.app_context():
            d = notif_company
            count = generate_notifications(d['user'].id, d['company'].id)
            assert count >= 1
            # Check overdue notification exists
            n = Notification.query.filter_by(
                notification_type='overdue_invoice',
                entity_id=d['supplier_invoice'].id,
            ).first()
            assert n is not None
            assert 'OVER-001' in n.title

    def test_no_duplicate_overdue(self, app, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            count1 = Notification.query.filter_by(
                notification_type='overdue_invoice',
                entity_id=d['supplier_invoice'].id,
            ).count()
            # Run again — should not create duplicate
            generate_notifications(d['user'].id, d['company'].id)
            count2 = Notification.query.filter_by(
                notification_type='overdue_invoice',
                entity_id=d['supplier_invoice'].id,
            ).count()
            assert count2 == count1

    def test_generate_upcoming_deadline(self, app, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            n = Notification.query.filter_by(
                notification_type='upcoming_deadline',
                entity_id=d['deadline'].id,
            ).first()
            assert n is not None
            assert 'Deadline' in n.title

    def test_generate_document_expiry(self, app, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            n = Notification.query.filter_by(
                notification_type='document_expiry',
                entity_id=d['document'].id,
            ).first()
            assert n is not None
            assert 'avtal.pdf' in n.title

    def test_generate_budget_variance(self, app, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            n = Notification.query.filter_by(
                notification_type='budget_variance',
            ).first()
            assert n is not None
            assert '5010' in n.title

    def test_generate_returns_count(self, app, notif_company):
        with app.app_context():
            d = notif_company
            count = generate_notifications(d['user'].id, d['company'].id)
            assert count >= 4  # overdue + deadline + doc_expiry + budget_variance


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestNotificationService:
    def test_get_unread_count(self, app, db, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            count = get_unread_count(d['user'].id, d['company'].id)
            assert count >= 4

    def test_get_recent_notifications(self, app, db, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            recent = get_recent_notifications(d['user'].id, d['company'].id)
            assert len(recent) >= 4
            # All should be unread initially
            assert all(not n.read for n in recent)

    def test_mark_as_read(self, app, db, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            n = Notification.query.filter_by(user_id=d['user'].id).first()
            assert mark_as_read(n.id, d['user'].id) is True
            assert db.session.get(Notification, n.id).read is True

    def test_mark_as_read_wrong_user(self, app, db, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            n = Notification.query.filter_by(user_id=d['user'].id).first()
            assert mark_as_read(n.id, d['user'].id + 999) is False

    def test_mark_all_read(self, app, db, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            count = mark_all_read(d['user'].id, d['company'].id)
            assert count >= 4
            assert get_unread_count(d['user'].id, d['company'].id) == 0

    def test_notification_link_valid(self, app, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            notifs = Notification.query.filter_by(user_id=d['user'].id).all()
            for n in notifs:
                assert n.link is not None
                assert n.link.startswith('/')

    def test_notification_icon_set(self, app, notif_company):
        with app.app_context():
            d = notif_company
            generate_notifications(d['user'].id, d['company'].id)
            notifs = Notification.query.filter_by(user_id=d['user'].id).all()
            for n in notifs:
                assert n.icon is not None
                assert n.icon.startswith('bi-')


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestNotificationRoutes:
    def test_notifications_require_login(self, client):
        resp = client.get('/notifications/')
        assert resp.status_code == 302

    def test_notifications_index(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/notifications/')
        assert resp.status_code == 200
        assert 'Aviseringar' in resp.data.decode()

    def test_api_count(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/notifications/api/count')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'count' in data

    def test_api_recent(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/notifications/api/recent')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'notifications' in data

    def test_mark_read_route(self, logged_in_client, db, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id

        # Generate first
        from app.services.notification_service import generate_notifications
        with logged_in_client.application.app_context():
            generate_notifications(d['user'].id, d['company'].id)
            n = Notification.query.filter_by(user_id=d['user'].id).first()
            nid = n.id

        resp = logged_in_client.post(f'/notifications/{nid}/read',
                                      follow_redirects=True)
        assert resp.status_code == 200

    def test_mark_all_read_route(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.post('/notifications/mark-all-read',
                                      follow_redirects=True)
        assert resp.status_code == 200

    def test_filter_by_type(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/notifications/?type=overdue_invoice')
        assert resp.status_code == 200

    def test_filter_by_read(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/notifications/?read=0')
        assert resp.status_code == 200

    def test_notification_respects_company(self, app, db, notif_company):
        """Notifications are scoped to the active company."""
        with app.app_context():
            d = notif_company
            co2 = Company(name='Other Notif AB', org_number='556900-0076', company_type='AB')
            db.session.add(co2)
            db.session.commit()
            count = get_unread_count(d['user'].id, co2.id)
            assert count == 0

    def test_bell_icon_in_navbar(self, logged_in_client, notif_company):
        d = notif_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/')
        html = resp.data.decode()
        assert 'notification-bell' in html
        assert 'notification-count' in html
