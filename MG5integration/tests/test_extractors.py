"""Tests for Excel extractors."""

import os
from app.extractors import (
    AccountExtractor, VerificationExtractor,
    ProjectExtractor, ProjectAdjustmentExtractor,
    TimeTrackingExtractor, CrossRefExtractor,
    CustomerOrderExtractor, PurchaseOrderExtractor,
    QuoteExtractor, OrderIntakeExtractor,
    InvoiceLogExtractor, ExchangeRateExtractor,
    ArticleExtractor, MinimumStockExtractor,
)
from app.models.accounting import Account, Verification
from app.models.projects import (
    Project, ProjectAdjustment, TimeTracking, CustomerOrderProjectMap
)
from app.models.orders import CustomerOrder, PurchaseOrder, Quote, OrderIntake
from app.models.invoicing import InvoiceLog, ExchangeRate
from app.models.inventory import Article, MinimumStock


def test_account_extractor(db, fixtures_dir):
    ext = AccountExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'kontoplan.xlsx'), 'test-batch'
    )
    assert count == 3
    acc = Account.query.filter_by(account_number=1010).first()
    assert acc is not None
    assert acc.description == 'Investering FoU'
    assert acc.account_type == 'Tillgångar'
    assert acc.import_batch_id == 'test-batch'


def test_verification_extractor(db, fixtures_dir):
    ext = VerificationExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'verlista.xlsx'), 'test-batch'
    )
    assert count == 3
    rows = Verification.query.filter_by(verification_number='1-1').all()
    assert len(rows) == 2
    assert rows[0].project == '0089 145'
    # Check debit/credit
    debits = sum(r.debit for r in rows)
    credits = sum(r.credit for r in rows)
    assert debits == 1000
    assert credits == 1000


def test_project_extractor(db, fixtures_dir):
    ext = ProjectExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'projektuppf.xlsx'), 'test-batch'
    )
    assert count == 2
    p = Project.query.filter_by(project_number='0089 145').first()
    assert p is not None
    assert p.description == 'MEGI'
    assert p.expected_income == 700000


def test_project_adjustment_extractor(db, fixtures_dir):
    # Need project first for FK
    from app.models.projects import Project
    db.session.add(Project(project_number='0089 145', description='MEGI'))
    db.session.commit()

    ext = ProjectAdjustmentExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'projectadjustments.xlsx'), 'test-batch'
    )
    assert count == 1
    adj = ProjectAdjustment.query.first()
    assert adj.contingency == 0.04
    assert adj.include_in_accrued is True


def test_time_tracking_extractor(db, fixtures_dir):
    db.session.add(Project(project_number='0089 145', description='MEGI'))
    db.session.commit()

    ext = TimeTrackingExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'tiduppfoljning.xlsx'), 'test-batch'
    )
    assert count == 1
    t = TimeTracking.query.first()
    assert t.actual_hours == 159.01


def test_crossref_extractor(db, fixtures_dir):
    ext = CrossRefExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'CO_proj_crossref.xlsx'), 'test-batch'
    )
    assert count == 2
    items = CustomerOrderProjectMap.query.all()
    assert items[0].order_number == 502100
    assert items[0].project_number == '0089 145'


def test_customer_order_extractor(db, fixtures_dir):
    ext = CustomerOrderExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'kundorderforteckning.xlsx'), 'test-batch'
    )
    assert count == 1
    o = CustomerOrder.query.first()
    assert o.order_number == 502100
    assert o.currency == 'SEK'
    assert o.unit_price == 60000


def test_purchase_order_extractor(db, fixtures_dir):
    ext = PurchaseOrderExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'inkoporderforteckning.xlsx'), 'test-batch'
    )
    assert count == 1
    po = PurchaseOrder.query.first()
    assert po.order_number == 8002018
    assert po.currency == 'EUR'
    assert po.supplier_name == 'ITAG'


def test_quote_extractor(db, fixtures_dir):
    ext = QuoteExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'Offertförteckning.xlsx'), 'test-batch'
    )
    assert count == 1
    q = Quote.query.first()
    assert q.quote_number == 'Q2326'
    assert q.amount == 49000


def test_order_intake_extractor(db, fixtures_dir):
    ext = OrderIntakeExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'Orderingång.xlsx'), 'test-batch'
    )
    assert count == 1
    oi = OrderIntake.query.first()
    assert oi.order_number == 501939
    assert oi.salesperson == 'Peter Jansson'


def test_invoice_log_extractor(db, fixtures_dir):
    ext = InvoiceLogExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'faktureringslogg.xlsx'), 'test-batch'
    )
    assert count == 2
    inv = InvoiceLog.query.filter_by(invoice_number=1).first()
    assert inv.amount == 753860.25
    assert inv.exchange_rate == 9.23


def test_exchange_rate_extractor(db, fixtures_dir):
    ext = ExchangeRateExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'valutakurser.xlsx'), 'test-batch'
    )
    assert count == 2
    r = ExchangeRate.query.order_by(ExchangeRate.date).first()
    assert r.eur == 10.14
    assert r.usd == 8.36


def test_article_extractor(db, fixtures_dir):
    ext = ArticleExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'Artikellista.xlsx'), 'test-batch'
    )
    assert count == 2
    a = Article.query.filter_by(article_number='PN P6000145792').first()
    assert a.total_balance == 10


def test_minimum_stock_extractor(db, fixtures_dir):
    ext = MinimumStockExtractor()
    count = ext.extract_from_excel(
        os.path.join(fixtures_dir, 'Min stock per artikel.xlsx'), 'test-batch'
    )
    assert count == 1
    ms = MinimumStock.query.first()
    assert ms.grade == 'F22'
    assert ms.ordered_quantity == 12


def test_full_refresh_clears_old_data(db, fixtures_dir):
    """Running extractor twice should replace, not duplicate."""
    ext = AccountExtractor()
    ext.extract_from_excel(os.path.join(fixtures_dir, 'kontoplan.xlsx'))
    assert Account.query.count() == 3
    ext.extract_from_excel(os.path.join(fixtures_dir, 'kontoplan.xlsx'))
    assert Account.query.count() == 3  # not 6
