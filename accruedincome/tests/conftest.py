"""Shared test fixtures for accrued income tests."""

import os
import json
import pytest
import pandas as pd

from app import create_app
from app.extensions import db as _db
from config import Config


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # in-memory
    WTF_CSRF_ENABLED = False
    MG5_INTEGRATION_URL = 'http://test-mg5:5001'
    PORTAL_AUTH_ENABLED = False


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app('default')
    app.config.from_object(TestingConfig)

    # Re-create tables with test config
    with app.app_context():
        _db.drop_all()
        _db.create_all()

    yield app


@pytest.fixture()
def db(app):
    """Provide clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture()
def client(app, db):
    """Flask test client."""
    return app.test_client()


# --- Sample API response data ---

SAMPLE_EXCHANGE_RATES = {
    'id': 1,
    'date': '2026-01-31',
    'sek': 1.0,
    'dkk': 1.52,
    'eur': 11.35,
    'gbp': 13.20,
    'nok': 0.98,
    'usd': 10.50,
}

SAMPLE_PROJECTS = [
    {
        'id': 1,
        'project_number': 'PROJ001',
        'description': 'Test Project Alpha',
        'customer': 'Customer A',
        'start_date': '2025-01-01',
        'end_date': '2026-12-31',
        'executed_cost': 500000.0,
        'executed_income': 300000.0,
        'expected_cost': 1000000.0,
        'expected_income': 1500000.0,
        'remaining_cost': 500000.0,
        'remaining_income': 1200000.0,
    },
    {
        'id': 2,
        'project_number': 'PROJ002',
        'description': 'Test Project Beta',
        'customer': 'Customer B',
        'start_date': '2025-06-01',
        'end_date': '2026-06-30',
        'executed_cost': 200000.0,
        'executed_income': 100000.0,
        'expected_cost': 400000.0,
        'expected_income': 600000.0,
        'remaining_cost': 200000.0,
        'remaining_income': 500000.0,
    },
]

SAMPLE_ADJUSTMENTS = [
    {
        'id': 1,
        'project_number': 'PROJ001',
        'description': 'Test Project Alpha',
        'customer': 'Customer A',
        'include_in_accrued': True,
        'contingency': 0.05,
        'income_adjustment': 0,
        'cost_calc_adjustment': 0,
        'purchase_adjustment': 0,
        'closing_date': '2026-01-31',
    },
    {
        'id': 2,
        'project_number': 'PROJ002',
        'description': 'Test Project Beta',
        'customer': 'Customer B',
        'include_in_accrued': True,
        'contingency': 0.10,
        'income_adjustment': 5000,
        'cost_calc_adjustment': 0,
        'purchase_adjustment': 0,
        'closing_date': '2026-01-31',
    },
]

SAMPLE_CO_MAP = [
    {'id': 1, 'order_number': 1001, 'project_number': 'PROJ001'},
    {'id': 2, 'order_number': 1002, 'project_number': 'PROJ002'},
]

SAMPLE_CUSTOMER_ORDERS = [
    {
        'id': 1,
        'order_number': 1001,
        'project': 'PROJ001',
        'project_description': 'Test Project Alpha',
        'customer_number': 100,
        'customer_name': 'Customer A',
        'customer_order_number': 'CA-001',
        'order_date': '2025-01-15',
        'article_number': 'ART100',
        'article_description': 'Service A',
        'remaining_amount': 500000.0,
        'remaining_amount_currency': 50000.0,
        'payment_terms': 30,
        'currency': 'EUR',
        'exchange_rate': 11.35,
        'unit_price': 113500.0,
        'unit_price_currency': 10000.0,
    },
]

SAMPLE_PURCHASE_ORDERS = [
    {
        'id': 1,
        'manufacturing_order_ref': None,
        'project': 'PROJ001',
        'manufacturing_order': None,
        'order_number': 2001,
        'position': 1,
        'article_number': 'MAT001',
        'article_description': 'Steel plates',
        'delivery_date': '2025-03-15',
        'unit_price': 50000.0,
        'unit_price_currency': 5000.0,
        'quantity_ordered': 10.0,
        'quantity_received': 5.0,
        'quantity_remaining': 5.0,
        'confirmed': True,
        'remaining_amount': 250000.0,
        'amount_currency': 25000.0,
        'account': 4010,
        'is_purchase_order': True,
        'project_description': 'Test Project Alpha',
        'supplier_name': 'Supplier X',
        'supplier_order_number': 'SX-001',
        'order_date': '2025-02-01',
        'customer_order': None,
        'country': 'DE',
        'currency': 'EUR',
        'requested_delivery_date': '2025-03-15',
        'goods_marking': None,
    },
]

SAMPLE_TIME_TRACKING = [
    {
        'id': 1,
        'project_number': 'PROJ001',
        'description': 'Engineering',
        'budget': 1000.0,
        'planned_time': 800.0,
        'actual_hours': 500.0,
        'expected_hours': 900.0,
        'forecast': 950.0,
        'remaining': 300.0,
    },
    {
        'id': 2,
        'project_number': 'PROJ002',
        'description': 'Design',
        'budget': 500.0,
        'planned_time': 400.0,
        'actual_hours': 200.0,
        'expected_hours': 450.0,
        'forecast': 460.0,
        'remaining': 200.0,
    },
]

SAMPLE_INVOICES = [
    {
        'id': 1,
        'invoice_number': 5001,
        'date': '2025-06-15',
        'project': 'PROJ001',
        'order_number': 1001,
        'customer_name': 'Customer A',
        'article_category': 'F100',
        'article_number': 'F100',
        'unit_price': 100000.0,
        'unit_price_currency': 10000.0,
        'amount': 100000.0,
        'amount_currency': 10000.0,
        'exchange_rate': 11.35,
        'forward_rate': False,
    },
]

SAMPLE_GL_SUMMARY = {
    'income_by_project': {
        'PROJ001': 350000.0,
        'PROJ002': 120000.0,
    },
    'cost_by_project': {
        'PROJ001': 480000.0,
        'PROJ002': 190000.0,
    },
}


def build_sample_api_response():
    """Build a complete sample API response."""
    return {
        'projects': SAMPLE_PROJECTS,
        'adjustments': SAMPLE_ADJUSTMENTS,
        'time_tracking': SAMPLE_TIME_TRACKING,
        'co_project_map': SAMPLE_CO_MAP,
        'customer_orders': SAMPLE_CUSTOMER_ORDERS,
        'purchase_orders': SAMPLE_PURCHASE_ORDERS,
        'invoice_log': SAMPLE_INVOICES,
        'gl_summary': SAMPLE_GL_SUMMARY,
        'exchange_rates': SAMPLE_EXCHANGE_RATES,
    }
