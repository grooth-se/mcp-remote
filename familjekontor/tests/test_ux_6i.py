"""Tests for UX Phase 6I: Searchable select dropdowns (Choices.js)."""
import os
from datetime import date

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account


def _setup_company(logged_in_client):
    """Create a company and set it as active in the session."""
    co = Company(name='UX6I Test AB', org_number='556000-6699', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


def _setup_with_fy(logged_in_client):
    """Create company + fiscal year + accounts."""
    co = _setup_company(logged_in_client)
    fy = FiscalYear(company_id=co.id, year=2024,
                    start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    acct = Account(company_id=co.id, account_number=1910,
                   name='Kassa', account_type='asset', active=True)
    db.session.add_all([fy, acct])
    db.session.commit()
    return co, fy


# ---------------------------------------------------------------------------
# CDN and JS module
# ---------------------------------------------------------------------------

class TestChoicesJsCDN:
    def test_base_includes_choices_css(self):
        """base.html should include Choices.js CSS CDN."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'base.html')
        with open(path) as f:
            content = f.read()
        assert 'choices.min.css' in content

    def test_base_includes_choices_js(self):
        """base.html should include Choices.js JS CDN."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'base.html')
        with open(path) as f:
            content = f.read()
        assert 'choices.min.js' in content

    def test_base_includes_searchable_select_js(self):
        """base.html should include searchable_select.js."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'base.html')
        with open(path) as f:
            content = f.read()
        assert 'searchable_select.js' in content


class TestSearchableSelectModule:
    def test_searchable_select_js_exists(self):
        """The searchable_select.js file should exist."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'searchable_select.js')
        assert os.path.exists(path)

    def test_searchable_select_js_has_init_function(self):
        """searchable_select.js should define initSearchableSelect."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'searchable_select.js')
        with open(path) as f:
            content = f.read()
        assert 'function initSearchableSelect' in content

    def test_searchable_select_js_swedish_labels(self):
        """searchable_select.js should use Swedish labels."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'searchable_select.js')
        with open(path) as f:
            content = f.read()
        assert 'Inga träffar' in content
        assert 'Skriv för att söka' in content


# ---------------------------------------------------------------------------
# Verification form integration
# ---------------------------------------------------------------------------

class TestVerificationFormSearchable:
    def test_verification_account_selects_have_searchable_class(self):
        """Verification form account selects should have searchable-select class."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'accounting', 'new_verification.html')
        with open(path) as f:
            content = f.read()
        assert 'searchable-select' in content

    def test_verification_form_js_calls_init(self):
        """verification_form.js addRow should call initSearchableSelect."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'verification_form.js')
        with open(path) as f:
            content = f.read()
        assert 'initSearchableSelect' in content

    def test_verification_form_stores_options_html(self):
        """verification_form.js should store accountOptionsHtml for new rows."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'js', 'verification_form.js')
        with open(path) as f:
            content = f.read()
        assert 'accountOptionsHtml' in content

    def test_verification_page_renders(self, logged_in_client):
        """Verification form page should render with searchable-select class."""
        co, fy = _setup_with_fy(logged_in_client)
        response = logged_in_client.get('/accounting/verification/new')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'searchable-select' in html


# ---------------------------------------------------------------------------
# Invoice forms
# ---------------------------------------------------------------------------

class TestInvoiceFormsSearchable:
    def test_customer_invoice_has_searchable_select(self):
        """Customer invoice form should have searchable-select on customer_id."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_customer_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'searchable-select' in content

    def test_supplier_invoice_has_searchable_select(self):
        """Supplier invoice form should have searchable-select on supplier_id."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'templates', 'invoices', 'new_supplier_invoice.html')
        with open(path) as f:
            content = f.read()
        assert 'searchable-select' in content


# ---------------------------------------------------------------------------
# CSS overrides
# ---------------------------------------------------------------------------

class TestChoicesCssOverrides:
    def test_css_has_choices_overrides(self):
        """style.css should have Choices.js Bootstrap overrides."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'css', 'style.css')
        with open(path) as f:
            content = f.read()
        assert '.choices__inner' in content
        assert '.choices' in content

    def test_css_hides_choices_in_print(self):
        """style.css should hide Choices.js wrapper in print."""
        path = os.path.join(os.path.dirname(__file__), '..',
                            'app', 'static', 'css', 'style.css')
        with open(path) as f:
            content = f.read()
        # Check print media query hides choices
        assert '.choices' in content
        assert '@media print' in content
