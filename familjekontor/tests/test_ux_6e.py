"""Tests for UX polish (Phase 6E): accessibility, print buttons, responsive reports."""
from datetime import date

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6E Test AB', org_number='556000-8888', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


def _setup_with_fy(logged_in_client):
    """Create company + fiscal year + account."""
    co = _setup_company(logged_in_client)
    fy = FiscalYear(company_id=co.id, year=2024,
                    start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    acct = Account(company_id=co.id, account_number=1910,
                   name='Kassa', account_type='asset', active=True)
    db.session.add_all([fy, acct])
    db.session.commit()
    return co, fy


# ---------------------------------------------------------------------------
# Skip-to-content link
# ---------------------------------------------------------------------------

class TestSkipNav:
    def test_skip_link_present(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'Hoppa till innehåll' in html
        assert 'visually-hidden-focusable' in html

    def test_main_content_id(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'id="main-content"' in html


# ---------------------------------------------------------------------------
# Print buttons on reports
# ---------------------------------------------------------------------------

class TestPrintButtons:
    def test_pnl_print_button(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/reports/pnl?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'window.print()' in html
        assert 'bi-printer' in html

    def test_balance_print_button(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/reports/balance?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'window.print()' in html
        assert 'bi-printer' in html

    def test_ledger_print_button(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/reports/ledger?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'window.print()' in html
        assert 'bi-printer' in html


# ---------------------------------------------------------------------------
# Responsive report tables
# ---------------------------------------------------------------------------

class TestResponsiveTables:
    def test_pnl_table_responsive(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/reports/pnl?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'table-responsive' in html

    def test_balance_table_responsive(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/reports/balance?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'table-responsive' in html


# ---------------------------------------------------------------------------
# aria-label on icon-only buttons
# ---------------------------------------------------------------------------

class TestAriaLabels:
    def test_verification_form_aria(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/accounting/verification/new?fiscal_year_id={fy.id}')
        html = response.data.decode()
        assert 'aria-label="Ta bort rad"' in html

    def test_recurring_list_aria(self, logged_in_client):
        _setup_company(logged_in_client)
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'recurring', 'list.html')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Generera faktura"' in content
        assert 'aria-label="Redigera"' in content

    def test_consolidation_group_aria(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'consolidation', 'group_view.html')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Ta bort medlem"' in content

    def test_bank_reconciliation_aria(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'bank', 'reconciliation.html')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Ignorera"' in content
        assert 'aria-label="Ta bort matchning"' in content
        assert 'aria-label="Matcha"' in content

    def test_customer_invoice_detail_aria(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'customer_invoice_detail.html')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Ta bort rad"' in content


# ---------------------------------------------------------------------------
# Dashboard chart canvas accessibility
# ---------------------------------------------------------------------------

class TestChartAccessibility:
    def test_revenue_chart_aria(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'role="img"' in html
        assert 'aria-label="Stapeldiagram' in html

    def test_cashflow_chart_aria(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'aria-label="Linjediagram' in html


# ---------------------------------------------------------------------------
# Print CSS enhancements
# ---------------------------------------------------------------------------

class TestPrintCSS:
    def test_breadcrumb_hidden_in_print(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'css', 'style.css')
        with open(path) as f:
            content = f.read()
        assert '.breadcrumb' in content
        assert 'a[href]:after' in content
