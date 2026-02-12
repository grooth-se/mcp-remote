"""Tests for UX polish (Phase 6H): Swedish number formatting, required field indicators, help tooltips."""
import os
from datetime import date

from app import create_app
from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6H Test AB', org_number='556000-6688', company_type='AB')
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
# Swedish number formatting (|sek filter)
# ---------------------------------------------------------------------------

class TestSekFilter:
    def test_sek_filter_registered(self, app):
        """The |sek filter should be registered."""
        assert 'sek' in app.jinja_env.filters

    def test_sek_filter_basic(self, app):
        """Test basic formatting: 1234.56 → '1 234,56'."""
        sek = app.jinja_env.filters['sek']
        result = sek(1234.56)
        assert '1' in result
        assert '234' in result
        assert ',56' in result
        # Should NOT contain a dot as decimal separator
        assert '.56' not in result

    def test_sek_filter_zero_decimals(self, app):
        """Test zero-decimal formatting: 1234567 → '1 234 567'."""
        sek = app.jinja_env.filters['sek']
        result = sek(1234567, 0)
        assert '234' in result
        assert '567' in result

    def test_sek_filter_none(self, app):
        """Test None returns dash."""
        sek = app.jinja_env.filters['sek']
        assert sek(None) == '-'

    def test_sek_filter_negative(self, app):
        """Test negative number formatting."""
        sek = app.jinja_env.filters['sek']
        result = sek(-1234.56)
        assert '-' in result
        assert ',56' in result

    def test_pnl_uses_sek_filter(self):
        """P&L template should use |sek filter, not old %.2f format."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'reports', 'pnl.html')
        with open(path) as f:
            content = f.read()
        assert '|sek' in content
        assert '"%.2f"|format' not in content

    def test_balance_uses_sek_filter(self):
        """Balance sheet template should use |sek filter."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'reports', 'balance.html')
        with open(path) as f:
            content = f.read()
        assert '|sek' in content
        assert '"%.2f"|format' not in content

    def test_dashboard_uses_sek_filter(self):
        """Dashboard template should use |sek(0) filter."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'dashboard', 'index.html')
        with open(path) as f:
            content = f.read()
        assert '|sek(0)' in content
        assert '"{:,.0f}".format' not in content

    def test_salary_uses_sek_filter(self):
        """Salary run view should use |sek(0) filter."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'salary', 'run_view.html')
        with open(path) as f:
            content = f.read()
        assert '|sek(0)' in content
        assert '"{:,.0f}".format' not in content


# ---------------------------------------------------------------------------
# Required field asterisks
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_css_has_required_style(self):
        """CSS should have .form-label.required::after rule."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'css', 'style.css')
        with open(path) as f:
            content = f.read()
        assert '.form-label.required::after' in content
        assert 'content: " *"' in content

    def test_company_form_has_required(self):
        """Company form should mark required fields."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'companies', 'new.html')
        with open(path) as f:
            content = f.read()
        assert 'form-label required' in content

    def test_verification_form_has_required(self):
        """Verification form should mark date as required."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'accounting', 'new_verification.html')
        with open(path) as f:
            content = f.read()
        assert 'form-label required' in content

    def test_employee_form_has_required(self):
        """Employee form should mark key fields as required."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'salary', 'employee_form.html')
        with open(path) as f:
            content = f.read()
        assert 'form-label required' in content


# ---------------------------------------------------------------------------
# Help tooltips
# ---------------------------------------------------------------------------

class TestHelpTooltips:
    def test_base_initializes_tooltips(self, logged_in_client):
        """Base template should initialize Bootstrap tooltips."""
        _setup_company(logged_in_client)
        response = logged_in_client.get('/')
        html = response.data.decode()
        assert 'bootstrap.Tooltip' in html

    def test_employee_form_has_pension_tooltip(self):
        """Employee form should have tooltip explaining pension plans."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'salary', 'employee_form.html')
        with open(path) as f:
            content = f.read()
        assert 'bi-info-circle' in content
        assert 'ITP1' in content

    def test_customer_invoice_has_vat_tooltip(self):
        """Customer invoice form should have tooltip explaining VAT types."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_customer_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'bi-info-circle' in content
        assert 'skattskyldighet' in content

    def test_exchange_rate_tooltip(self):
        """Supplier invoice should have tooltip on exchange rate."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_supplier_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'bi-info-circle' in content
        assert 'utländsk enhet' in content.lower() or 'utl' in content.lower()
