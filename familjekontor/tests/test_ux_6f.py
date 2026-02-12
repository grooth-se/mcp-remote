"""Tests for UX polish (Phase 6F): back-to-top, pagination info, confirm standardization, variance chart, aria-labels."""
import os
from datetime import date

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6F Test AB', org_number='556000-9999', company_type='AB')
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
# Back to top
# ---------------------------------------------------------------------------

class TestBackToTop:
    def test_back_to_top_js_exists(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'back_to_top.js')
        assert os.path.exists(path)

    def test_back_to_top_js_content(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'back_to_top.js')
        with open(path) as f:
            content = f.read()
        assert 'back-to-top' in content
        assert 'scrollTo' in content

    def test_base_includes_back_to_top(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'back_to_top.js' in html

    def test_css_has_back_to_top_styles(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'css', 'style.css')
        with open(path) as f:
            content = f.read()
        assert '.back-to-top' in content
        assert 'position: fixed' in content


# ---------------------------------------------------------------------------
# Pagination info
# ---------------------------------------------------------------------------

class TestPaginationInfo:
    def test_pagination_macro_has_count(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'macros', 'pagination.html')
        with open(path) as f:
            content = f.read()
        assert 'Visar' in content
        assert 'pagination.total' in content


# ---------------------------------------------------------------------------
# Confirm dialog standardization
# ---------------------------------------------------------------------------

class TestConfirmStandardization:
    def test_closing_uses_data_confirm(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'closing', 'preview.html')
        with open(path) as f:
            content = f.read()
        assert 'data-confirm=' in content
        assert 'onclick="return confirm' not in content

    def test_salary_run_uses_data_confirm(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'salary', 'run_view.html')
        with open(path) as f:
            content = f.read()
        assert 'data-confirm=' in content
        assert 'onclick="return confirm' not in content

    def test_companies_view_uses_data_confirm(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'companies', 'view.html')
        with open(path) as f:
            content = f.read()
        assert 'data-confirm=' in content
        assert 'onsubmit="return confirm' not in content

    def test_consolidation_uses_data_confirm(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'consolidation', 'group_view.html')
        with open(path) as f:
            content = f.read()
        assert 'data-confirm=' in content
        assert 'onsubmit="return confirm' not in content


# ---------------------------------------------------------------------------
# Budget variance chart
# ---------------------------------------------------------------------------

class TestVarianceChart:
    def test_variance_template_has_chart_canvas(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'budget', 'variance.html')
        with open(path) as f:
            content = f.read()
        assert 'varianceChart' in content
        assert 'indexAxis' in content

    def test_variance_page_loads_chartjs(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'budget', 'variance.html')
        with open(path) as f:
            content = f.read()
        assert 'chart.js' in content or 'chart.umd.min.js' in content

    def test_variance_chart_has_aria(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'budget', 'variance.html')
        with open(path) as f:
            content = f.read()
        assert 'role="img"' in content
        assert 'aria-label=' in content


# ---------------------------------------------------------------------------
# Dynamic row aria-label
# ---------------------------------------------------------------------------

class TestDynamicAriaLabels:
    def test_verification_form_js_has_aria(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'verification_form.js')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Ta bort rad"' in content

    def test_fetch_rate_supplier_aria(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_supplier_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Hämta växelkurs"' in content

    def test_fetch_rate_customer_aria(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_customer_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'aria-label="Hämta växelkurs"' in content
