"""Tests for REST API endpoints."""

import os
from datetime import date
from app.models.accounting import Account, Verification
from app.models.projects import (
    Project, ProjectAdjustment, TimeTracking, CustomerOrderProjectMap
)
from app.models.orders import CustomerOrder, PurchaseOrder
from app.models.invoicing import InvoiceLog, ExchangeRate
from app.models.inventory import Article, MinimumStock
from app.models.extraction import ExtractionLog


def _seed_basic_data(db):
    """Seed minimal data for API tests."""
    db.session.add(Account(account_number=1010, description='Test Account', account_type='Tillgångar'))
    db.session.add(Account(account_number=3010, description='Revenue', account_type='Intäkter'))

    p = Project(project_number='0089 145', description='MEGI', customer='FMC KONGSBERG',
                expected_income=700000, executed_cost=500000)
    db.session.add(p)
    db.session.commit()

    db.session.add(ProjectAdjustment(project_number='0089 145', contingency=0.04))
    db.session.add(TimeTracking(project_number='0089 145', actual_hours=159))

    db.session.add(Verification(verification_number='1-1', date=date(2024, 1, 15),
                                 text='Test', account=1010, debit=1000, credit=0, project='0089 145'))
    db.session.add(Verification(verification_number='1-1', date=date(2024, 1, 15),
                                 text='Test', account=3010, debit=0, credit=1000, project='0089 145'))
    db.session.add(Verification(verification_number='1-2', date=date(2024, 6, 1),
                                 text='Other', account=1010, debit=500, credit=0))

    db.session.add(CustomerOrderProjectMap(order_number=502100, project_number='0089 145'))
    db.session.add(CustomerOrder(order_number=502100, project='0089 145',
                                  customer_name='FMC KONGSBERG', currency='SEK'))
    db.session.add(PurchaseOrder(order_number=8002018, project='0089 145',
                                  supplier_name='ITAG', currency='EUR'))
    db.session.add(InvoiceLog(invoice_number=1, date=date(2024, 1, 1),
                               project='0089 145', amount=753860.25))
    db.session.add(ExchangeRate(date=date(2024, 1, 1), eur=10.14, usd=8.36, sek=1.0))
    db.session.add(Article(article_number='0018 049 04 007', description='STRESS JOINT',
                            total_balance=5))
    db.session.add(MinimumStock(article_number='PN P6000145792', grade='F22',
                                 ordered_quantity=12))
    db.session.commit()


def test_health_endpoint(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['total_records'] > 0
    assert 'accounts' in data['record_counts']


def test_get_accounts(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/accounts')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total'] == 2
    assert len(data['items']) == 2


def test_get_accounts_filter_type(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/accounts?type=Tillgångar')
    data = resp.get_json()
    assert data['total'] == 1
    assert data['items'][0]['account_type'] == 'Tillgångar'


def test_get_single_account(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/accounts/1010')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['account_number'] == 1010


def test_get_account_not_found(client, db):
    resp = client.get('/api/accounts/9999')
    assert resp.status_code == 404


def test_get_verifications(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/verifications')
    data = resp.get_json()
    assert data['total'] == 3


def test_get_verifications_filter_project(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/verifications?project=0089 145')
    data = resp.get_json()
    assert data['total'] == 2


def test_get_verifications_filter_date_range(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/verifications?from_date=2024-03-01&to_date=2024-12-31')
    data = resp.get_json()
    assert data['total'] == 1  # Only the June verification


def test_get_verifications_filter_account(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/verifications?account=1010')
    data = resp.get_json()
    assert data['total'] == 2


def test_get_verification_by_number(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/verifications/1-1')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


def test_get_projects(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/projects')
    data = resp.get_json()
    assert data['total'] == 1


def test_get_project_detail(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/projects/0089 145')
    data = resp.get_json()
    assert data['project_number'] == '0089 145'
    assert len(data['adjustments']) == 1
    assert len(data['time_tracking']) == 1


def test_get_project_verifications(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/projects/0089 145/verifications')
    data = resp.get_json()
    assert data['total'] == 2


def test_get_project_orders(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/projects/0089 145/orders')
    data = resp.get_json()
    assert len(data['customer_orders']) == 1
    assert len(data['purchase_orders']) == 1


def test_get_customer_orders(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/customer-orders')
    data = resp.get_json()
    assert data['total'] == 1


def test_get_purchase_orders(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/purchase-orders?supplier=ITAG')
    data = resp.get_json()
    assert data['total'] == 1


def test_get_invoices(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/invoices')
    data = resp.get_json()
    assert data['total'] == 1


def test_get_exchange_rates(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/exchange-rates')
    data = resp.get_json()
    assert data['total'] == 1


def test_get_latest_exchange_rate(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/exchange-rates/latest')
    data = resp.get_json()
    assert data['eur'] == 10.14


def test_get_articles(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/articles')
    data = resp.get_json()
    assert data['total'] == 1


def test_get_article_with_min_stock(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/articles/0018 049 04 007')
    data = resp.get_json()
    assert data['article_number'] == '0018 049 04 007'


def test_get_order_project_map(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/order-project-map')
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['order_number'] == 502100


def test_accrued_income_data(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/accrued-income-data')
    data = resp.get_json()
    assert len(data['projects']) == 1
    assert len(data['adjustments']) == 1
    assert 'gl_summary' in data
    assert data['exchange_rates']['eur'] == 10.14


def test_pagination(client, db):
    _seed_basic_data(db)
    resp = client.get('/api/verifications?page=1&per_page=1')
    data = resp.get_json()
    assert data['total'] == 3
    assert len(data['items']) == 1
    assert data['pages'] == 3


def test_extraction_status_empty(client, db):
    resp = client.get('/api/extract/status')
    data = resp.get_json()
    assert data['status'] == 'no_extractions'


def test_extraction_status_after_import(client, db):
    log = ExtractionLog(batch_id='test-1', source='excel',
                         status='success', records_imported=100)
    db.session.add(log)
    db.session.commit()
    resp = client.get('/api/extract/status')
    data = resp.get_json()
    assert data['status'] == 'success'
    assert data['records_imported'] == 100


def test_trigger_extraction(client, db, fixtures_dir, app):
    app.config['EXCEL_EXPORTS_FOLDER'] = fixtures_dir
    resp = client.post('/api/extract/trigger')
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['status'] in ('success', 'partial')
    assert data['records_imported'] > 0
