"""Tests for SQLAlchemy models."""

from datetime import date
from app.models.accounting import Account, Verification
from app.models.projects import (
    Project, ProjectAdjustment, TimeTracking, CustomerOrderProjectMap
)
from app.models.orders import CustomerOrder, PurchaseOrder, Quote, OrderIntake
from app.models.invoicing import InvoiceLog, ExchangeRate
from app.models.inventory import Article, MinimumStock
from app.models.extraction import ExtractionLog


def test_create_account(db):
    acc = Account(account_number=1010, description='Test', account_type='Tillgångar')
    db.session.add(acc)
    db.session.commit()
    assert acc.id is not None
    assert acc.account_number == 1010
    d = acc.to_dict()
    assert d['account_number'] == 1010
    assert d['description'] == 'Test'


def test_account_unique_constraint(db):
    db.session.add(Account(account_number=1010, description='A'))
    db.session.commit()
    db.session.add(Account(account_number=1010, description='B'))
    import sqlalchemy
    try:
        db.session.commit()
        assert False, 'Should have raised IntegrityError'
    except sqlalchemy.exc.IntegrityError:
        db.session.rollback()


def test_create_verification(db):
    v = Verification(
        verification_number='1-1', date=date(2024, 1, 15),
        text='Test', account=1010, debit=1000, credit=0,
        project='0089 145'
    )
    db.session.add(v)
    db.session.commit()
    assert v.id is not None
    d = v.to_dict()
    assert d['date'] == '2024-01-15'
    assert d['project'] == '0089 145'
    assert d['debit'] == 1000


def test_create_project(db):
    p = Project(
        project_number='0089 145', description='MEGI',
        customer='FMC KONGSBERG',
        expected_income=700000, executed_cost=500000
    )
    db.session.add(p)
    db.session.commit()
    assert p.id is not None
    d = p.to_dict()
    assert d['project_number'] == '0089 145'
    assert d['expected_income'] == 700000


def test_project_adjustment_fk(db):
    p = Project(project_number='0089 145', description='MEGI')
    db.session.add(p)
    db.session.commit()

    adj = ProjectAdjustment(
        project_number='0089 145', contingency=0.04,
        include_in_accrued=True
    )
    db.session.add(adj)
    db.session.commit()
    assert adj.project.project_number == '0089 145'


def test_time_tracking_fk(db):
    p = Project(project_number='0089 145', description='MEGI')
    db.session.add(p)
    db.session.commit()

    t = TimeTracking(
        project_number='0089 145', actual_hours=159.01, expected_hours=159.01
    )
    db.session.add(t)
    db.session.commit()
    assert t.project.project_number == '0089 145'
    assert t.to_dict()['actual_hours'] == 159.01


def test_create_co_project_map(db):
    m = CustomerOrderProjectMap(order_number=502100, project_number='0089 145')
    db.session.add(m)
    db.session.commit()
    assert m.to_dict()['order_number'] == 502100


def test_create_customer_order(db):
    o = CustomerOrder(
        order_number=502100, project='0089 145',
        customer_name='FMC KONGSBERG', currency='SEK',
        unit_price=60000
    )
    db.session.add(o)
    db.session.commit()
    d = o.to_dict()
    assert d['order_number'] == 502100
    assert d['currency'] == 'SEK'


def test_create_purchase_order(db):
    po = PurchaseOrder(
        order_number=8002018, project='0089 145',
        supplier_name='ITAG', currency='EUR',
        quantity_ordered=1, quantity_received=1
    )
    db.session.add(po)
    db.session.commit()
    d = po.to_dict()
    assert d['supplier_name'] == 'ITAG'


def test_create_quote(db):
    q = Quote(
        quote_number='Q2326', customer_name='FMC KONGSBERG',
        status='6 Avslutad', amount=49000
    )
    db.session.add(q)
    db.session.commit()
    d = q.to_dict()
    assert d['amount'] == 49000


def test_create_order_intake(db):
    oi = OrderIntake(
        order_number=501939, customer_name='Helix',
        value=9.23, salesperson='Peter Jansson'
    )
    db.session.add(oi)
    db.session.commit()
    d = oi.to_dict()
    assert d['salesperson'] == 'Peter Jansson'


def test_create_invoice_log(db):
    inv = InvoiceLog(
        invoice_number=1, date=date(2024, 1, 1),
        project='0089 145', amount=753860.25, exchange_rate=9.23
    )
    db.session.add(inv)
    db.session.commit()
    d = inv.to_dict()
    assert d['amount'] == 753860.25


def test_create_exchange_rate(db):
    r = ExchangeRate(
        date=date(2024, 1, 1), eur=10.14, usd=8.36,
        gbp=11.65, nok=0.97, dkk=1.44, sek=1.0
    )
    db.session.add(r)
    db.session.commit()
    d = r.to_dict()
    assert d['eur'] == 10.14


def test_create_article(db):
    a = Article(
        article_number='0018 049 04 007',
        description='LOWER STRESS JOINT',
        total_balance=5
    )
    db.session.add(a)
    db.session.commit()
    d = a.to_dict()
    assert d['total_balance'] == 5


def test_create_minimum_stock(db):
    ms = MinimumStock(
        article_number='PN P6000145792',
        outer_diameter=200, grade='F22', ordered_quantity=12
    )
    db.session.add(ms)
    db.session.commit()
    d = ms.to_dict()
    assert d['grade'] == 'F22'


def test_create_extraction_log(db):
    log = ExtractionLog(
        batch_id='test-batch-123', source='excel', status='success',
        records_imported=100
    )
    db.session.add(log)
    db.session.commit()
    d = log.to_dict()
    assert d['records_imported'] == 100
