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
    create_transaction, get_portfolio_summary,
    get_dividend_income_summary,
    parse_nordnet_csv, import_nordnet_transactions,
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
