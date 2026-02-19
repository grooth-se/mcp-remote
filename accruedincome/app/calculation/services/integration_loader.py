"""Load accrued income data from MG5integration REST API.

Converts JSON responses to pandas DataFrames with exact column names
the AccruedIncomeCalculator expects, replacing the need for 11 Excel files.
"""

import json
import urllib.request
import urllib.error
import pandas as pd
from flask import current_app

from app.extensions import db
from app.models import FactProjectMonthly


class IntegrationDataLoader:
    """Fetches data from MG5integration API and builds calculator DataFrames."""

    def __init__(self, base_url=None):
        self.base_url = base_url or current_app.config.get(
            'MG5_INTEGRATION_URL', 'http://mg5integration:5001'
        )

    def check_health(self):
        """Check if MG5integration API is reachable.

        Returns:
            dict with 'ok' bool and 'detail' string.
        """
        try:
            url = f'{self.base_url}/api/health'
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return {'ok': True, 'detail': data}
        except Exception as e:
            return {'ok': False, 'detail': str(e)}

    def fetch_api_data(self):
        """Fetch all accrued income data from MG5integration in one call.

        Returns:
            dict: parsed JSON from /api/accrued-income-data
        Raises:
            ConnectionError: if API is unreachable
            ValueError: if response is not valid JSON
        """
        url = f'{self.base_url}/api/accrued-income-data'
        req = urllib.request.Request(url, method='GET')
        req.add_header('Accept', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            raise ConnectionError(
                f'Could not connect to MG5integration at {self.base_url}: {e}'
            )

    def load(self):
        """Fetch API data and convert to calculator-compatible DataFrames.

        Returns:
            dict: mapping of DataFrame keys to pandas DataFrames,
                  plus 'gl_summary' key with pre-aggregated GL data.
        """
        data = self.fetch_api_data()
        dfs = {}

        dfs['valutakurser'] = self._build_exchange_rates(data.get('exchange_rates'))
        dfs['projectadjustments'] = self._build_adjustments(data.get('adjustments', []))
        dfs['CO_proj_crossref'] = self._build_co_project_map(data.get('co_project_map', []))
        dfs['projektuppf'] = self._build_projects(data.get('projects', []))
        dfs['inkoporderforteckning'] = self._build_purchase_orders(data.get('purchase_orders', []))
        dfs['kundorderforteckning'] = self._build_customer_orders(data.get('customer_orders', []))
        dfs['kontoplan'] = pd.DataFrame()  # Not used in core calculation
        dfs['verlista'] = pd.DataFrame()   # Replaced by gl_summary
        dfs['tiduppfoljning'] = self._build_time_tracking(data.get('time_tracking', []))
        dfs['faktureringslogg'] = self._build_invoice_log(data.get('invoice_log', []))
        dfs['Accuredhistory'] = self._build_accrued_history()

        # Pass pre-aggregated GL data for direct injection
        dfs['gl_summary'] = data.get('gl_summary', {})

        return dfs

    # --- DataFrame builders ---

    def _build_exchange_rates(self, rates):
        """Build single-row exchange rate DataFrame.

        API: {sek, dkk, eur, gbp, nok, usd}
        Calculator expects: {SEK, DKK, EUR, GBP, NOK, USD} (single row)
        """
        if not rates:
            return pd.DataFrame([{'SEK': 1.0, 'DKK': 1.0, 'EUR': 1.0,
                                  'GBP': 1.0, 'NOK': 1.0, 'USD': 1.0}])
        return pd.DataFrame([{
            'SEK': rates.get('sek', 1.0),
            'DKK': rates.get('dkk', 1.0),
            'EUR': rates.get('eur', 1.0),
            'GBP': rates.get('gbp', 1.0),
            'NOK': rates.get('nok', 1.0),
            'USD': rates.get('usd', 1.0),
        }])

    def _build_adjustments(self, items):
        """Build project adjustments DataFrame.

        API: project_number, include_in_accrued, contingency, income_adjustment,
             cost_calc_adjustment, purchase_adjustment, closing_date
        Calculator expects: Projektnummer, Accured, Contingency, Incomeadj,
                           Costcalcadj, puradj, Closing
        """
        if not items:
            return pd.DataFrame(columns=[
                'Projektnummer', 'Accured', 'Contingency',
                'Incomeadj', 'Costcalcadj', 'puradj', 'Closing'
            ])
        rows = []
        for item in items:
            rows.append({
                'Projektnummer': item['project_number'],
                'Accured': item.get('include_in_accrued', True),
                'Contingency': item.get('contingency', 0) or 0,
                'Incomeadj': item.get('income_adjustment', 0) or 0,
                'Costcalcadj': item.get('cost_calc_adjustment', 0) or 0,
                'puradj': item.get('purchase_adjustment', 0) or 0,
                'Closing': item.get('closing_date', ''),
            })
        return pd.DataFrame(rows)

    def _build_co_project_map(self, items):
        """Build customer order → project cross-reference DataFrame.

        API: order_number, project_number
        Calculator expects: Ordernummer, Projekt
        """
        if not items:
            return pd.DataFrame(columns=['Ordernummer', 'Projekt'])
        rows = [{'Ordernummer': item['order_number'],
                 'Projekt': item['project_number']} for item in items]
        return pd.DataFrame(rows)

    def _build_projects(self, items):
        """Build project follow-up DataFrame.

        API: project_number, description, customer, expected_income,
             expected_cost, executed_income, executed_cost
        Calculator expects: Projektnummer, Benamning, Kundnamn,
                           Forvan. intakt, Forvan. kostnad,
                           Utf., intakt, Utf., kostnad
        """
        if not items:
            return pd.DataFrame(columns=[
                'Projektnummer', 'Benamning', 'Kundnamn',
                'Forvan. intakt', 'Forvan. kostnad',
                'Utf., intakt', 'Utf., kostnad'
            ])
        rows = []
        for item in items:
            rows.append({
                'Projektnummer': item['project_number'],
                'Benamning': item.get('description', ''),
                'Kundnamn': item.get('customer', ''),
                'Forvan. intakt': item.get('expected_income', 0) or 0,
                'Forvan. kostnad': item.get('expected_cost', 0) or 0,
                'Utf., intakt': item.get('executed_income', 0) or 0,
                'Utf., kostnad': item.get('executed_cost', 0) or 0,
            })
        return pd.DataFrame(rows)

    def _build_purchase_orders(self, items):
        """Build purchase order DataFrame.

        API: project, article_description, article_number, amount_currency, currency
        Calculator expects: Projekt, Benamning, Artikelnummer, Belopp val., Valuta
        """
        if not items:
            return pd.DataFrame(columns=[
                'Projekt', 'Benamning', 'Artikelnummer', 'Belopp val.', 'Valuta'
            ])
        rows = []
        for item in items:
            rows.append({
                'Projekt': item.get('project', ''),
                'Benamning': item.get('article_description', ''),
                'Artikelnummer': item.get('article_number', ''),
                'Belopp val.': item.get('amount_currency', 0) or 0,
                'Valuta': item.get('currency', 'SEK'),
            })
        return pd.DataFrame(rows)

    def _build_customer_orders(self, items):
        """Build customer order DataFrame.

        API: order_number, remaining_amount_currency, currency, project
        Calculator expects: Ordernummer, Restbelopp val., Valuta, Projekt
        """
        if not items:
            return pd.DataFrame(columns=[
                'Ordernummer', 'Restbelopp val.', 'Valuta', 'Projekt'
            ])
        rows = []
        for item in items:
            rows.append({
                'Ordernummer': item.get('order_number', ''),
                'Restbelopp val.': item.get('remaining_amount_currency', 0) or 0,
                'Valuta': item.get('currency', 'SEK'),
                'Projekt': item.get('project', ''),
            })
        return pd.DataFrame(rows)

    def _build_time_tracking(self, items):
        """Build time tracking DataFrame.

        API: project_number, actual_hours
        Calculator expects: Projektnummer, Utfall
        """
        if not items:
            return pd.DataFrame(columns=['Projektnummer', 'Utfall'])
        rows = [{'Projektnummer': item['project_number'],
                 'Utfall': item.get('actual_hours', 0) or 0} for item in items]
        return pd.DataFrame(rows)

    def _build_invoice_log(self, items):
        """Build invoice/milestone log DataFrame.

        API: order_number, article_category, amount, amount_currency
        Calculator expects: Ordernummer, Artikel - Artikelnummer, Belopp, Belopp val.
        """
        if not items:
            return pd.DataFrame(columns=[
                'Ordernummer', 'Artikel - Artikelnummer', 'Belopp', 'Belopp val.'
            ])
        rows = []
        for item in items:
            rows.append({
                'Ordernummer': item.get('order_number', ''),
                'Artikel - Artikelnummer': item.get('article_category', ''),
                'Belopp': item.get('amount', 0) or 0,
                'Belopp val.': item.get('amount_currency', 0) or 0,
            })
        return pd.DataFrame(rows)

    def _build_accrued_history(self):
        """Build accrued history DataFrame from FactProjectMonthly DB records.

        Replaces the Accuredhistory.xlsx file by querying the app's own
        stored historical calculation results.
        """
        records = FactProjectMonthly.query.order_by(
            FactProjectMonthly.closing_date,
            FactProjectMonthly.project_number
        ).all()

        if not records:
            return pd.DataFrame(columns=[
                'Projektnummer', 'closing', 'actcost CUR', 'actincome CUR',
                'accured income CUR', 'totalcost CUR', 'totalincome CUR'
            ])

        rows = []
        for r in records:
            rows.append({
                'Projektnummer': r.project_number,
                'Benamning': r.project_name or '',
                'Kundnamn': r.customer_name or '',
                'closing': r.closing_date,
                'Forvan. intakt': r.expected_income or 0,
                'Forvan. kostnad': r.expected_cost or 0,
                'Utf., intakt': r.executed_income or 0,
                'Utf., kostnad': r.executed_cost or 0,
                'act income': r.actual_income or 0,
                'act cost': r.actual_cost or 0,
                'CM cost': r.cm_cost or 0,
                'Remaining cost': r.remaining_cost or 0,
                'Remaining income': r.remaining_income or 0,
                'Remaining income val.': r.remaining_income_val or 0,
                'Remaining income CUR': r.remaining_income_cur or 0,
                'Milestone': r.milestone_amount or 0,
                'Milestone CUR': r.milestone_cur or 0,
                'vinstmarg': r.profit_margin or 0,
                'kostfakt': r.cost_factor or 0,
                'fardiggrad': r.completion_rate or 0,
                'accured income': r.accrued_income or 0,
                'risk': r.risk_amount or 0,
                'actincome CUR': r.actual_income_cur or 0,
                'actcost CUR': r.actual_cost_cur or 0,
                'totalincome CUR': r.total_income_cur or 0,
                'totalcost CUR': r.total_cost_cur or 0,
                'profit margin CUR': r.profit_margin_cur or 0,
                'actcost invo CUR': r.actual_cost_invoiced_cur or 0,
                'completion CUR': r.completion_cur or 0,
                'completion CUR1': r.completion_cur1 or 0,
                'accured income CUR': r.accrued_income_cur or 0,
                'contingency CUR': r.contingency_cur or 0,
                'incl': r.include_in_accrued,
                'complex': r.contingency_factor or 0,
                'incomeadj': r.income_adjustment or 0,
                'costcalcadj': r.cost_calc_adjustment or 0,
                'puradj': r.purchase_adjustment or 0,
                'projloss': r.project_profit or 0,
                'diffincome': r.diff_income or 0,
                'diffcost': r.diff_cost or 0,
            })
        return pd.DataFrame(rows)
