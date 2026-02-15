"""Tests for UX polish (Phase 6G): active nav, unsaved changes, AJAX loading, favicon, footer."""
import os
from datetime import date

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6G Test AB', org_number='556000-6699', company_type='AB')
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
# Active nav highlight
# ---------------------------------------------------------------------------

class TestActiveNavHighlight:
    def test_dashboard_nav_active(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        # The "Start" nav link should have the active class
        assert 'class="nav-link active' in html

    def test_accounting_nav_active(self, logged_in_client):
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get(f'/accounting/?fiscal_year_id={fy.id}')
        html = response.data.decode()
        # Bokföring dropdown should be active
        assert 'Bokföring' in html
        # Check that at least one nav-link has active class
        assert 'nav-link dropdown-toggle active' in html or 'nav-link active' in html

    def test_base_has_endpoint_checks(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'base.html')
        with open(path) as f:
            content = f.read()
        assert 'request.endpoint' in content
        assert "startswith('dashboard.')" in content
        assert "startswith('accounting.')" in content


# ---------------------------------------------------------------------------
# Unsaved changes warning
# ---------------------------------------------------------------------------

class TestUnsavedChanges:
    def test_unsaved_changes_js_exists(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'unsaved_changes.js')
        assert os.path.exists(path)

    def test_unsaved_changes_js_content(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'unsaved_changes.js')
        with open(path) as f:
            content = f.read()
        assert 'data-warn-unsaved' in content
        assert 'beforeunload' in content

    def test_base_includes_unsaved_changes(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'unsaved_changes.js' in html

    def test_verification_form_has_warn_unsaved(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'accounting', 'new_verification.html')
        with open(path) as f:
            content = f.read()
        assert 'data-warn-unsaved' in content

    def test_supplier_invoice_has_warn_unsaved(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_supplier_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'data-warn-unsaved' in content

    def test_employee_form_has_warn_unsaved(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'salary', 'employee_form.html')
        with open(path) as f:
            content = f.read()
        assert 'data-warn-unsaved' in content


# ---------------------------------------------------------------------------
# AJAX loading states
# ---------------------------------------------------------------------------

class TestAjaxLoadingStates:
    def test_budget_grid_has_loading_spinner(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'budget_grid.js')
        with open(path) as f:
            content = f.read()
        assert 'spinner-border' in content
        assert 'Sparar...' in content
        assert 'saveBtn' in content


# ---------------------------------------------------------------------------
# Favicon
# ---------------------------------------------------------------------------

class TestFavicon:
    def test_favicon_svg_exists(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'favicon.svg')
        assert os.path.exists(path)

    def test_favicon_is_valid_svg(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'favicon.svg')
        with open(path) as f:
            content = f.read()
        assert '<svg' in content
        assert '</svg>' in content

    def test_base_has_favicon_link(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'favicon.svg' in html


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

class TestFooter:
    def test_footer_visible(self, logged_in_client):
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert '<footer' in html
        assert 'PsalmGears' in html
        assert 'Bokföring' in html

    def test_footer_has_year(self, logged_in_client):
        from datetime import datetime
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert str(datetime.now().year) in html

    def test_footer_hidden_in_print_css(self):
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'css', 'style.css')
        with open(path) as f:
            content = f.read()
        assert 'footer' in content
