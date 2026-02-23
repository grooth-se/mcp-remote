"""Tests for Phase 5D: Investment/Portfolio Management."""
import io
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification
from app.models.investment import (
    InvestmentPortfolio, InvestmentHolding, InvestmentTransaction,
)
from app.services.investment_service import (
    create_portfolio, get_portfolios, get_portfolio,
    get_holding, get_holding_transactions, update_holding_price,
    update_holding_metadata,
    create_transaction, get_portfolio_summary,
    get_dividend_income_summary, get_interest_income_summary,
    parse_nordnet_csv, parse_csv, import_nordnet_transactions,
)


def _setup_company(logged_in_client):
    co = Company(name='Investment Test AB', org_number='556000-8800', company_type='AB')
    db.session.add(co)
    db.session.commit()
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co.id
    return co


def _setup_fy(company, year=2024):
    fy = FiscalYear(company_id=company.id, year=year,
                    start_date=date(year, 1, 1), end_date=date(year, 12, 31))
    db.session.add(fy)
    db.session.commit()
    return fy


def _add_accounts(company):
    accts = [
        Account(company_id=company.id, account_number='1350', name='Andelar och värdepapper',
                account_type='asset', active=True),
        Account(company_id=company.id, account_number='1930', name='Företagskonto',
                account_type='asset', active=True),
        Account(company_id=company.id, account_number='6570', name='Bankkostnader',
                account_type='expense', active=True),
        Account(company_id=company.id, account_number='8210', name='Utdelning på aktier',
                account_type='revenue', active=True),
        Account(company_id=company.id, account_number='8220', name='Resultat försäljning VP',
                account_type='revenue', active=True),
        Account(company_id=company.id, account_number='8230', name='Förlust försäljning VP',
                account_type='expense', active=True),
    ]
    db.session.add_all(accts)
    db.session.commit()
    return accts


def _create_test_portfolio(company):
    return create_portfolio(company.id, {
        'name': 'Nordnet ISK',
        'portfolio_type': 'isk',
        'broker': 'Nordnet',
        'ledger_account': '1350',
    })


# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------

class TestPortfolio:
    def test_create_portfolio(self, logged_in_client):
        co = _setup_company(logged_in_client)
        p = _create_test_portfolio(co)
        assert p.id is not None
        assert p.name == 'Nordnet ISK'
        assert p.portfolio_type_label == 'ISK'
        assert p.broker == 'Nordnet'

    def test_get_portfolios(self, logged_in_client):
        co = _setup_company(logged_in_client)
        create_portfolio(co.id, {'name': 'Avanza', 'broker': 'Avanza'})
        create_portfolio(co.id, {'name': 'Nordnet', 'broker': 'Nordnet'})
        portfolios = get_portfolios(co.id)
        assert len(portfolios) == 2

    def test_get_portfolio(self, logged_in_client):
        co = _setup_company(logged_in_client)
        p = _create_test_portfolio(co)
        fetched = get_portfolio(p.id)
        assert fetched.name == p.name


# ---------------------------------------------------------------------------
# Transactions — Buy
# ---------------------------------------------------------------------------

class TestBuyTransaction:
    def test_buy_creates_holding(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 3, 15),
            'name': 'Investor B',
            'isin': 'SE0000107419',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 200,
            'amount': 20000,
            'commission': 39,
            'fiscal_year_id': fy.id,
        })
        assert tx.id is not None
        assert tx.holding_id is not None
        assert tx.verification_id is not None

        holding = get_holding(tx.holding_id)
        assert holding.name == 'Investor B'
        assert float(holding.quantity) == 100
        # Total cost = 20000 + 39 = 20039
        assert float(holding.total_cost) == 20039
        # Avg cost = 20039 / 100 = 200.39
        assert abs(float(holding.average_cost) - 200.39) < 0.01

    def test_buy_additional_updates_average(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # First buy: 100 @ 200 + 0 commission
        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 3, 1),
            'name': 'SEB A',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 200,
            'amount': 20000,
            'fiscal_year_id': fy.id,
        })

        # Second buy: 50 @ 250
        tx2 = create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 6, 1),
            'name': 'SEB A',
            'instrument_type': 'aktie',
            'quantity': 50,
            'price_per_unit': 250,
            'amount': 12500,
            'fiscal_year_id': fy.id,
        })

        holding = get_holding(tx2.holding_id)
        assert float(holding.quantity) == 150
        assert float(holding.total_cost) == 32500  # 20000 + 12500
        # Avg = 32500/150 = 216.6667
        assert abs(float(holding.average_cost) - 216.67) < 0.01


# ---------------------------------------------------------------------------
# Transactions — Sell
# ---------------------------------------------------------------------------

class TestSellTransaction:
    def test_sell_calculates_gain(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # Buy 100 @ 200
        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 15),
            'name': 'ABB',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 200,
            'amount': 20000,
            'fiscal_year_id': fy.id,
        })

        # Sell 50 @ 300
        tx = create_transaction(p.id, {
            'transaction_type': 'salj',
            'transaction_date': date(2024, 6, 15),
            'name': 'ABB',
            'instrument_type': 'aktie',
            'quantity': 50,
            'price_per_unit': 300,
            'amount': 15000,
            'fiscal_year_id': fy.id,
        })

        assert tx.realized_gain is not None
        # Cost basis = 200 * 50 = 10000, proceeds = 15000
        assert float(tx.realized_gain) == 5000.0

        holding = get_holding(tx.holding_id)
        assert float(holding.quantity) == 50
        assert holding.active is True

    def test_sell_all_deactivates_holding(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'Volvo B',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 150,
            'amount': 15000,
            'fiscal_year_id': fy.id,
        })

        tx = create_transaction(p.id, {
            'transaction_type': 'salj',
            'transaction_date': date(2024, 6, 1),
            'name': 'Volvo B',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 120,
            'amount': 12000,
            'fiscal_year_id': fy.id,
        })

        holding = get_holding(tx.holding_id)
        assert float(holding.quantity) == 0
        assert holding.active is False
        # Loss: 12000 - 15000 = -3000
        assert float(tx.realized_gain) == -3000.0

    def test_sell_more_than_held_raises(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'Test',
            'instrument_type': 'aktie',
            'quantity': 10,
            'price_per_unit': 100,
            'amount': 1000,
            'fiscal_year_id': fy.id,
        })

        try:
            create_transaction(p.id, {
                'transaction_type': 'salj',
                'transaction_date': date(2024, 6, 1),
                'name': 'Test',
                'instrument_type': 'aktie',
                'quantity': 20,
                'price_per_unit': 100,
                'amount': 2000,
                'fiscal_year_id': fy.id,
            })
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Transactions — Dividend, Fee, etc.
# ---------------------------------------------------------------------------

class TestOtherTransactions:
    def test_dividend_transaction(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # First buy something
        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'H&M B',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 150,
            'amount': 15000,
            'fiscal_year_id': fy.id,
        })

        # Dividend
        tx = create_transaction(p.id, {
            'transaction_type': 'utdelning',
            'transaction_date': date(2024, 4, 15),
            'name': 'H&M B',
            'instrument_type': 'aktie',
            'amount': 650,
            'fiscal_year_id': fy.id,
        })
        assert tx.verification_id is not None

    def test_fee_transaction(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'avgift',
            'transaction_date': date(2024, 3, 31),
            'amount': 29,
            'fiscal_year_id': fy.id,
        })
        assert tx.verification_id is not None

    def test_deposit_transaction(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'insattning',
            'transaction_date': date(2024, 1, 5),
            'amount': 50000,
            'fiscal_year_id': fy.id,
        })
        assert tx.verification_id is not None


# ---------------------------------------------------------------------------
# Price Update
# ---------------------------------------------------------------------------

class TestPriceUpdate:
    def test_update_price(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'Ericsson B',
            'instrument_type': 'aktie',
            'quantity': 200,
            'price_per_unit': 80,
            'amount': 16000,
            'fiscal_year_id': fy.id,
        })

        holding = update_holding_price(tx.holding_id, 95, date(2024, 12, 1))
        assert float(holding.current_price) == 95
        assert float(holding.current_value) == 19000  # 200 * 95
        assert float(holding.unrealized_gain) == 3000  # 19000 - 16000


# ---------------------------------------------------------------------------
# Portfolio Summary
# ---------------------------------------------------------------------------

class TestPortfolioSummary:
    def test_summary(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'Stock A',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 100,
            'amount': 10000,
            'fiscal_year_id': fy.id,
        })

        summary = get_portfolio_summary(co.id)
        assert len(summary['portfolios']) == 1
        assert float(summary['total_cost']) == 10000

    def test_empty_summary(self, logged_in_client):
        co = _setup_company(logged_in_client)
        summary = get_portfolio_summary(co.id)
        assert summary['portfolios'] == []
        assert float(summary['total_cost']) == 0


# ---------------------------------------------------------------------------
# Dividend Income Summary
# ---------------------------------------------------------------------------

class TestDividendSummary:
    def test_dividend_summary(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # Buy + dividend
        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'SHB A',
            'instrument_type': 'aktie',
            'quantity': 100,
            'price_per_unit': 100,
            'amount': 10000,
            'fiscal_year_id': fy.id,
        })
        create_transaction(p.id, {
            'transaction_type': 'utdelning',
            'transaction_date': date(2024, 4, 15),
            'name': 'SHB A',
            'amount': 500,
            'fiscal_year_id': fy.id,
        })

        result = get_dividend_income_summary(co.id, fy.id)
        assert len(result) == 1
        assert float(result[0]['total']) == 500


# ---------------------------------------------------------------------------
# Nordnet CSV Parsing
# ---------------------------------------------------------------------------

class TestNordnetParsing:
    def test_parse_basic_csv(self, logged_in_client):
        _setup_company(logged_in_client)
        csv_content = (
            'Bokföringsdag;Transaktionstyp;Värdepapper;ISIN;Antal;Kurs;Belopp;Courtage;Valuta\n'
            '2024-03-15;KÖPT;Investor B;SE0000107419;100;200,50;20050,00;39,00;SEK\n'
            '2024-06-01;SÅLT;Investor B;SE0000107419;50;250,00;12500,00;39,00;SEK\n'
            '2024-04-15;UTDELNING;Investor B;SE0000107419;;;650,00;;SEK\n'
        )
        file = io.BytesIO(csv_content.encode('latin-1'))
        file.name = 'nordnet.csv'
        transactions = parse_nordnet_csv(file)

        assert len(transactions) == 3
        assert transactions[0]['transaction_type'] == 'kop'
        assert transactions[0]['name'] == 'Investor B'
        assert float(transactions[0]['quantity']) == 100
        assert float(transactions[0]['amount']) == 20050

        assert transactions[1]['transaction_type'] == 'salj'
        assert transactions[2]['transaction_type'] == 'utdelning'

    def test_parse_with_spaces_in_numbers(self, logged_in_client):
        _setup_company(logged_in_client)
        csv_content = (
            'Bokföringsdag;Transaktionstyp;Värdepapper;ISIN;Antal;Kurs;Belopp;Courtage;Valuta\n'
            '2024-01-15;KÖPT;Volvo B;SE0000115446;1 000;220,50;220 500,00;99,00;SEK\n'
        )
        file = io.BytesIO(csv_content.encode('latin-1'))
        transactions = parse_nordnet_csv(file)

        assert len(transactions) == 1
        assert float(transactions[0]['quantity']) == 1000
        assert float(transactions[0]['amount']) == 220500


class TestSEBParsing:
    def test_parse_seb_bank_statement(self, logged_in_client):
        _setup_company(logged_in_client)
        csv_content = (
            'Bokförd;Valutadatum;Text;Typ;Insättningar;Uttag;Bokfört saldo\n'
            '2025-06-11;2025-06-11;SKATTEVERKET;Betalning (bg/pg);;-20915,00;50608,35\n'
            '2025-02-28;2025-02-28;BG 172-7676;Bankgirobetalning;31632,00;;87748,60\n'
            '2025-02-24;2025-02-24;LÅN;Överföring;;-25000,00;56116,60\n'
        )
        file = io.BytesIO(csv_content.encode('utf-8'))
        transactions = parse_csv(file)

        assert len(transactions) == 3
        assert transactions[0]['transaction_type'] == 'uttag'
        assert float(transactions[0]['amount']) == 20915
        assert transactions[0]['name'] == 'SKATTEVERKET'

        assert transactions[1]['transaction_type'] == 'insattning'
        assert float(transactions[1]['amount']) == 31632

        assert transactions[2]['transaction_type'] == 'uttag'
        assert float(transactions[2]['amount']) == 25000

    def test_parse_seb_with_utf8_bom(self, logged_in_client):
        _setup_company(logged_in_client)
        csv_content = (
            '\ufeffBokförd;Valutadatum;Text;Typ;Insättningar;Uttag;Bokfört saldo\n'
            '2025-01-10;2025-01-10;LÅN;Annan;100000,00;;233727,96\n'
        )
        file = io.BytesIO(csv_content.encode('utf-8-sig'))
        transactions = parse_csv(file)

        assert len(transactions) == 1
        assert transactions[0]['transaction_type'] == 'insattning'
        assert float(transactions[0]['amount']) == 100000

    def test_unsupported_format_raises(self, logged_in_client):
        _setup_company(logged_in_client)
        csv_content = 'Datum;Beskrivning;Summa\n2025-01-01;Test;100\n'
        file = io.BytesIO(csv_content.encode('utf-8'))
        import pytest
        with pytest.raises(ValueError, match='Okänt CSV-format'):
            parse_csv(file)

    def test_auto_detect_nordnet(self, logged_in_client):
        _setup_company(logged_in_client)
        csv_content = (
            'Bokföringsdag;Transaktionstyp;Värdepapper;ISIN;Antal;Kurs;Belopp;Courtage;Valuta\n'
            '2024-03-15;KÖPT;Investor B;SE0000107419;100;200,50;20050,00;39,00;SEK\n'
        )
        file = io.BytesIO(csv_content.encode('latin-1'))
        transactions = parse_csv(file)

        assert len(transactions) == 1
        assert transactions[0]['transaction_type'] == 'kop'


class TestNordnetImport:
    def test_import_with_dedup(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        transactions = [
            {
                'transaction_type': 'kop',
                'transaction_date': date(2024, 3, 15),
                'name': 'ABB',
                'instrument_type': 'aktie',
                'quantity': 100,
                'price_per_unit': 200,
                'amount': Decimal('20000'),
                'commission': Decimal('39'),
                'currency': 'SEK',
            },
        ]

        result1 = import_nordnet_transactions(p.id, transactions, fy.id)
        assert result1['imported'] == 1

        # Import again — should skip
        result2 = import_nordnet_transactions(p.id, transactions, fy.id)
        assert result2['imported'] == 0
        assert result2['skipped'] == 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestInvestmentRoutes:
    def test_index(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/investments/')
        assert resp.status_code == 200
        assert 'Investeringar' in resp.data.decode()

    def test_portfolio_new_get(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.get('/investments/portfolios/new')
        assert resp.status_code == 200
        assert 'Ny portfölj' in resp.data.decode()

    def test_portfolio_new_post(self, logged_in_client):
        _setup_company(logged_in_client)
        resp = logged_in_client.post('/investments/portfolios/new', data={
            'name': 'Test Portfolio',
            'portfolio_type': 'isk',
            'broker': 'Nordnet',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Test Portfolio' in resp.data.decode()

    def test_portfolio_view(self, logged_in_client):
        co = _setup_company(logged_in_client)
        p = _create_test_portfolio(co)
        resp = logged_in_client.get(f'/investments/portfolios/{p.id}')
        assert resp.status_code == 200
        assert 'Nordnet ISK' in resp.data.decode()

    def test_transaction_new_get(self, logged_in_client):
        co = _setup_company(logged_in_client)
        p = _create_test_portfolio(co)
        resp = logged_in_client.get(f'/investments/portfolios/{p.id}/transactions/new')
        assert resp.status_code == 200
        assert 'Ny transaktion' in resp.data.decode()

    def test_import_get(self, logged_in_client):
        co = _setup_company(logged_in_client)
        p = _create_test_portfolio(co)
        resp = logged_in_client.get(f'/investments/portfolios/{p.id}/import')
        assert resp.status_code == 200
        assert 'Importera' in resp.data.decode()

    def test_reports(self, logged_in_client):
        co = _setup_company(logged_in_client)
        _setup_fy(co)
        resp = logged_in_client.get('/investments/reports')
        assert resp.status_code == 200
        assert 'Investeringsrapporter' in resp.data.decode()

    def test_holding_view(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'Test Stock',
            'instrument_type': 'aktie',
            'quantity': 50,
            'price_per_unit': 100,
            'amount': 5000,
            'fiscal_year_id': fy.id,
        })
        resp = logged_in_client.get(f'/investments/holdings/{tx.holding_id}')
        assert resp.status_code == 200
        assert 'Test Stock' in resp.data.decode()

    def test_price_update_get(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 1),
            'name': 'Price Test',
            'instrument_type': 'aktie',
            'quantity': 10,
            'price_per_unit': 100,
            'amount': 1000,
            'fiscal_year_id': fy.id,
        })
        resp = logged_in_client.get(f'/investments/holdings/{tx.holding_id}/price')
        assert resp.status_code == 200
        assert 'Uppdatera pris' in resp.data.decode()

    def test_holding_edit_get(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 3, 1),
            'name': 'Lån till Startup AB',
            'instrument_type': 'lan',
            'amount': 500000,
            'fiscal_year_id': fy.id,
        })
        resp = logged_in_client.get(f'/investments/holdings/{tx.holding_id}/edit')
        assert resp.status_code == 200
        assert 'Redigera detaljer' in resp.data.decode()

    def test_holding_edit_post(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 3, 1),
            'name': 'Edit Test AB',
            'instrument_type': 'lan',
            'amount': 100000,
            'fiscal_year_id': fy.id,
        })
        resp = logged_in_client.post(f'/investments/holdings/{tx.holding_id}/edit', data={
            'org_number': '556123-4567',
            'interest_rate': '5.5',
            'maturity_date': '2026-12-31',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Detaljer uppdaterade' in resp.data.decode()


# ---------------------------------------------------------------------------
# Loans (utlan / amortering)
# ---------------------------------------------------------------------------

class TestLoanTransactions:
    def test_utlan_creates_loan_holding(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 3, 1),
            'name': 'Startup AB',
            'instrument_type': 'lan',
            'amount': 500000,
            'org_number': '556123-4567',
            'interest_rate': 8.0,
            'maturity_date': date(2026, 3, 1),
            'fiscal_year_id': fy.id,
        })
        assert tx.id is not None
        assert tx.holding_id is not None
        assert tx.verification_id is not None

        holding = get_holding(tx.holding_id)
        assert holding.name == 'Startup AB'
        assert holding.instrument_type == 'lan'
        assert float(holding.face_value) == 500000
        assert float(holding.remaining_principal) == 500000
        assert float(holding.quantity) == 1
        assert holding.org_number == '556123-4567'
        assert holding.active is True

    def test_amortering_reduces_principal(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # Issue loan
        create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 1, 15),
            'name': 'Borrower AB',
            'instrument_type': 'lan',
            'amount': 200000,
            'fiscal_year_id': fy.id,
        })

        # Partial amortization
        tx = create_transaction(p.id, {
            'transaction_type': 'amortering',
            'transaction_date': date(2024, 6, 15),
            'name': 'Borrower AB',
            'amount': 50000,
            'fiscal_year_id': fy.id,
        })
        assert tx.verification_id is not None

        holding = get_holding(tx.holding_id)
        assert float(holding.remaining_principal) == 150000
        assert holding.active is True

    def test_full_repayment_deactivates(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 1, 1),
            'name': 'Full Repay AB',
            'instrument_type': 'lan',
            'amount': 100000,
            'fiscal_year_id': fy.id,
        })

        tx = create_transaction(p.id, {
            'transaction_type': 'amortering',
            'transaction_date': date(2024, 12, 1),
            'name': 'Full Repay AB',
            'amount': 100000,
            'fiscal_year_id': fy.id,
        })

        holding = get_holding(tx.holding_id)
        assert float(holding.remaining_principal) == 0
        assert holding.active is False

    def test_over_amortization_raises(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 1, 1),
            'name': 'Over Amort AB',
            'instrument_type': 'lan',
            'amount': 50000,
            'fiscal_year_id': fy.id,
        })

        try:
            create_transaction(p.id, {
                'transaction_type': 'amortering',
                'transaction_date': date(2024, 6, 1),
                'name': 'Over Amort AB',
                'amount': 60000,
                'fiscal_year_id': fy.id,
            })
            assert False, 'Should have raised ValueError'
        except ValueError as e:
            assert 'överskrider' in str(e)

    def test_utlan_verification_accounts(self, logged_in_client):
        """utlan: Debit loan account (1385), Credit bank (1930)."""
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 3, 1),
            'name': 'Verify Loan AB',
            'instrument_type': 'lan',
            'amount': 300000,
            'fiscal_year_id': fy.id,
        })

        v = db.session.get(Verification, tx.verification_id)
        assert v is not None
        assert len(v.rows) == 2
        debits = [r for r in v.rows if float(r.debit) > 0]
        credits = [r for r in v.rows if float(r.credit) > 0]
        assert len(debits) == 1
        assert len(credits) == 1
        # Debit is loan account (1385), credit is bank (1930)
        debit_acct = db.session.get(Account, debits[0].account_id)
        credit_acct = db.session.get(Account, credits[0].account_id)
        assert debit_acct.account_number == '1385'
        assert credit_acct.account_number == '1930'


# ---------------------------------------------------------------------------
# Direct investments (onoterad)
# ---------------------------------------------------------------------------

class TestDirectInvestment:
    def test_buy_onoterad_with_metadata(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 2, 1),
            'name': 'TechStartup AB',
            'instrument_type': 'onoterad',
            'quantity': 1000,
            'price_per_unit': 100,
            'amount': 100000,
            'org_number': '559000-1234',
            'ownership_pct': 25.0,
            'fiscal_year_id': fy.id,
        })

        holding = get_holding(tx.holding_id)
        assert holding.instrument_type == 'onoterad'
        assert holding.org_number == '559000-1234'
        assert float(holding.ownership_pct) == 25.0
        assert float(holding.quantity) == 1000


# ---------------------------------------------------------------------------
# Bonds (kupong)
# ---------------------------------------------------------------------------

class TestBondTransactions:
    def test_kupong_verification(self, logged_in_client):
        """kupong: Debit bank (1930), Credit ränteintäkter (8310)."""
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        # Ensure 8310 exists
        Account.query.filter_by(company_id=co.id, account_number='8310').first() or \
            db.session.add(Account(company_id=co.id, account_number='8310',
                                   name='Ränteintäkter', account_type='revenue', active=True))
        db.session.commit()

        p = _create_test_portfolio(co)

        # First create the bond holding via buy
        create_transaction(p.id, {
            'transaction_type': 'kop',
            'transaction_date': date(2024, 1, 15),
            'name': 'Corp Bond 2027',
            'instrument_type': 'foretagsobligation',
            'quantity': 10,
            'price_per_unit': 10000,
            'amount': 100000,
            'interest_rate': 5.5,
            'maturity_date': date(2027, 6, 15),
            'face_value': 100000,
            'fiscal_year_id': fy.id,
        })

        # Coupon payment
        tx = create_transaction(p.id, {
            'transaction_type': 'kupong',
            'transaction_date': date(2024, 6, 15),
            'name': 'Corp Bond 2027',
            'amount': 2750,
            'fiscal_year_id': fy.id,
        })
        assert tx.verification_id is not None

        v = db.session.get(Verification, tx.verification_id)
        assert len(v.rows) == 2
        debits = [r for r in v.rows if float(r.debit) > 0]
        credits = [r for r in v.rows if float(r.credit) > 0]
        debit_acct = db.session.get(Account, debits[0].account_id)
        credit_acct = db.session.get(Account, credits[0].account_id)
        assert debit_acct.account_number == '1930'
        assert credit_acct.account_number == '8310'


# ---------------------------------------------------------------------------
# Interest Income Summary
# ---------------------------------------------------------------------------

class TestInterestSummary:
    def test_interest_summary(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # Create loan + coupon income
        create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 1, 1),
            'name': 'Interest Test AB',
            'instrument_type': 'lan',
            'amount': 100000,
            'fiscal_year_id': fy.id,
        })
        create_transaction(p.id, {
            'transaction_type': 'kupong',
            'transaction_date': date(2024, 6, 15),
            'name': 'Interest Test AB',
            'amount': 5000,
            'fiscal_year_id': fy.id,
        })

        result = get_interest_income_summary(co.id, fy.id)
        assert len(result) == 1
        assert float(result[0]['total']) == 5000

    def test_interest_summary_includes_ranta(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co, 2024)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        # Plain ranta transaction (no holding)
        create_transaction(p.id, {
            'transaction_type': 'ranta',
            'transaction_date': date(2024, 3, 31),
            'amount': 1500,
            'fiscal_year_id': fy.id,
        })

        result = get_interest_income_summary(co.id, fy.id)
        assert len(result) == 1
        assert float(result[0]['total']) == 1500


# ---------------------------------------------------------------------------
# Holding metadata update
# ---------------------------------------------------------------------------

class TestHoldingMetadata:
    def test_update_holding_metadata(self, logged_in_client):
        co = _setup_company(logged_in_client)
        fy = _setup_fy(co)
        _add_accounts(co)
        p = _create_test_portfolio(co)

        tx = create_transaction(p.id, {
            'transaction_type': 'utlan',
            'transaction_date': date(2024, 1, 1),
            'name': 'Meta Test AB',
            'instrument_type': 'lan',
            'amount': 200000,
            'fiscal_year_id': fy.id,
        })

        holding = update_holding_metadata(tx.holding_id, {
            'org_number': '556999-0001',
            'interest_rate': 6.5,
            'maturity_date': date(2026, 6, 30),
            'face_value': 200000,
        })
        assert holding.org_number == '556999-0001'
        assert float(holding.interest_rate) == 6.5
        assert holding.maturity_date == date(2026, 6, 30)
