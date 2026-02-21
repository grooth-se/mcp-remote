"""Tests for Phase 10D: Reverse Charge VAT for International Customers."""

import pytest
from decimal import Decimal
from app.models.invoice import Customer, CustomerInvoice
from app.models.company import Company
from app.services.vat_service import (
    get_vat_type_for_customer, validate_eu_vat_number,
    get_vat_display_text, compute_invoice_vat, EU_COUNTRIES,
)


# ---- Service tests ----

class TestGetVatTypeForCustomer:
    def test_swedish_customer(self):
        assert get_vat_type_for_customer('SE') == 'standard'

    def test_swedish_with_vat(self):
        assert get_vat_type_for_customer('SE', 'SE123456789012') == 'standard'

    def test_eu_with_vat(self):
        assert get_vat_type_for_customer('DE', 'DE123456789') == 'reverse_charge'

    def test_eu_without_vat(self):
        assert get_vat_type_for_customer('DE', None) == 'standard'

    def test_eu_empty_vat(self):
        assert get_vat_type_for_customer('FR', '') == 'standard'

    def test_non_eu(self):
        assert get_vat_type_for_customer('US') == 'export'

    def test_non_eu_with_vat(self):
        assert get_vat_type_for_customer('US', 'US12345') == 'export'

    def test_empty_country(self):
        assert get_vat_type_for_customer('') == 'standard'

    def test_none_country(self):
        assert get_vat_type_for_customer(None) == 'standard'

    def test_lowercase_country(self):
        assert get_vat_type_for_customer('de', 'DE123456789') == 'reverse_charge'


class TestValidateEuVatNumber:
    def test_valid_german(self):
        result = validate_eu_vat_number('DE123456789')
        assert result['valid'] is True

    def test_valid_finnish(self):
        result = validate_eu_vat_number('FI12345678')
        assert result['valid'] is True

    def test_valid_swedish(self):
        result = validate_eu_vat_number('SE123456789012')
        assert result['valid'] is True

    def test_invalid_german_too_short(self):
        result = validate_eu_vat_number('DE1234')
        assert result['valid'] is False

    def test_empty_vat(self):
        result = validate_eu_vat_number('')
        assert result['valid'] is False

    def test_none_vat(self):
        result = validate_eu_vat_number(None)
        assert result['valid'] is False

    def test_unknown_country(self):
        result = validate_eu_vat_number('XX12345')
        assert result['valid'] is False

    def test_with_country_hint(self):
        result = validate_eu_vat_number('DE123456789', country='DE')
        assert result['valid'] is True

    def test_strips_whitespace(self):
        result = validate_eu_vat_number(' DE 123456789 ')
        assert result['valid'] is True


class TestGetVatDisplayText:
    def test_reverse_charge(self):
        text = get_vat_display_text('reverse_charge')
        assert 'Omvänd skattskyldighet' in text

    def test_export(self):
        text = get_vat_display_text('export')
        assert 'Momsfri export' in text

    def test_standard(self):
        text = get_vat_display_text('standard')
        assert text is None


class TestComputeInvoiceVat:
    def test_standard_25(self):
        vat = compute_invoice_vat(10000, 25, 'standard')
        assert vat == Decimal('2500.00')

    def test_reverse_charge_zero(self):
        vat = compute_invoice_vat(10000, 25, 'reverse_charge')
        assert vat == Decimal('0')

    def test_export_zero(self):
        vat = compute_invoice_vat(10000, 25, 'export')
        assert vat == Decimal('0')

    def test_none_amount(self):
        vat = compute_invoice_vat(None, 25, 'standard')
        assert vat == Decimal('0')


class TestEuCountries:
    def test_sweden_in_eu(self):
        assert 'SE' in EU_COUNTRIES

    def test_norway_not_in_eu(self):
        assert 'NO' not in EU_COUNTRIES

    def test_count(self):
        assert len(EU_COUNTRIES) == 27


# ---- Route tests ----

class TestVatSuggestionRoute:
    def test_vat_suggestion_se(self, logged_in_client, db):
        company = Company(name='Vat AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        customer = Customer(company_id=company.id, name='Kund SE', country='SE')
        db.session.add(customer)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/invoices/customer/{customer.id}/vat-suggestion')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['vat_type'] == 'standard'

    def test_vat_suggestion_eu_reverse(self, logged_in_client, db):
        company = Company(name='Vat AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        customer = Customer(company_id=company.id, name='German Co', country='DE', vat_number='DE123456789')
        db.session.add(customer)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/invoices/customer/{customer.id}/vat-suggestion')
        data = resp.get_json()
        assert data['vat_type'] == 'reverse_charge'

    def test_vat_suggestion_export(self, logged_in_client, db):
        company = Company(name='Vat AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()
        customer = Customer(company_id=company.id, name='US Corp', country='US')
        db.session.add(customer)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get(f'/invoices/customer/{customer.id}/vat-suggestion')
        data = resp.get_json()
        assert data['vat_type'] == 'export'
        assert 'Momsfri export' in data['display_text']

    def test_vat_suggestion_not_found(self, logged_in_client, db):
        company = Company(name='Vat AB', org_number='556700-0001', company_type='AB')
        db.session.add(company)
        db.session.commit()

        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = company.id

        resp = logged_in_client.get('/invoices/customer/9999/vat-suggestion')
        assert resp.status_code == 404
