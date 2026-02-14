"""Financial ratio analysis: profitability, liquidity, solvency, efficiency.

Computes KPIs from P&L and Balance Sheet data, with traffic-light benchmarks
and multi-year trend support.
"""

from app.extensions import db
from app.models.accounting import FiscalYear
from app.services.report_service import (
    get_profit_and_loss, get_balance_sheet, _get_account_balances,
)


# Swedish SME benchmarks (low = warning threshold, high = good threshold)
BENCHMARKS = {
    # Profitability (%) — higher is better
    'gross_margin': {'low': 20.0, 'high': 40.0},
    'operating_margin': {'low': 5.0, 'high': 15.0},
    'net_margin': {'low': 3.0, 'high': 10.0},
    'roe': {'low': 10.0, 'high': 20.0},
    'roa': {'low': 5.0, 'high': 10.0},
    # Liquidity (ratio) — higher is better
    'current_ratio': {'low': 1.0, 'high': 2.0},
    'quick_ratio': {'low': 0.8, 'high': 1.5},
    'cash_ratio': {'low': 0.2, 'high': 0.5},
    # Solvency — equity_ratio higher is better, debt_to_equity lower is better
    'equity_ratio': {'low': 20.0, 'high': 40.0},
    'debt_to_equity': {'low': 1.0, 'high': 3.0, 'inverted': True},
    'interest_coverage': {'low': 2.0, 'high': 5.0},
    # Efficiency — higher is better
    'asset_turnover': {'low': 0.5, 'high': 1.5},
}


def get_financial_ratios(company_id, fiscal_year_id):
    """Compute all financial ratios from P&L and Balance Sheet.

    Returns dict with sections: profitability, liquidity, solvency, efficiency.
    Each ratio: {value, label, format, description}.
    """
    pnl = get_profit_and_loss(company_id, fiscal_year_id)
    bs = get_balance_sheet(company_id, fiscal_year_id)

    revenue = pnl['sections']['Nettoomsättning']['total']
    cogs = pnl['sections']['Kostnad sålda varor']['total']
    gross_profit = pnl['gross_profit']
    operating_result = pnl['operating_result']
    result_before_tax = pnl['result_before_tax']
    fin_costs = pnl['sections']['Finansiella kostnader']['total']

    total_assets = bs['total_assets']
    equity = bs['sections']['Eget kapital']['total']
    current_assets = bs['sections']['Omsättningstillgångar']['total']
    st_liabilities = bs['sections']['Kortfristiga skulder']['total']
    lt_liabilities = bs['sections']['Långfristiga skulder']['total']
    total_debt = lt_liabilities + st_liabilities

    # Inventory (14xx) and Cash (19xx) from raw balances
    raw_balances = _get_account_balances(company_id, fiscal_year_id)
    inventory = sum(b for a, b in raw_balances if a.account_number[:2] == '14')
    cash = sum(b for a, b in raw_balances if a.account_number[:2] == '19')

    def _safe_div(a, b):
        return a / b if b else None

    def _safe_pct(a, b):
        v = _safe_div(a, b)
        return round(v * 100, 1) if v is not None else None

    profitability = {
        'gross_margin': {
            'value': _safe_pct(gross_profit, revenue),
            'label': 'Bruttomarginal',
            'format': 'pct',
            'description': 'Bruttovinst / Nettoomsättning',
        },
        'operating_margin': {
            'value': _safe_pct(operating_result, revenue),
            'label': 'Rörelsemarginal',
            'format': 'pct',
            'description': 'Rörelseresultat / Nettoomsättning',
        },
        'net_margin': {
            'value': _safe_pct(result_before_tax, revenue),
            'label': 'Nettomarginal',
            'format': 'pct',
            'description': 'Resultat före skatt / Nettoomsättning',
        },
        'roe': {
            'value': _safe_pct(result_before_tax, equity),
            'label': 'Avkastning eget kapital (ROE)',
            'format': 'pct',
            'description': 'Resultat före skatt / Eget kapital',
        },
        'roa': {
            'value': _safe_pct(result_before_tax, total_assets),
            'label': 'Avkastning totalt kapital (ROA)',
            'format': 'pct',
            'description': 'Resultat före skatt / Totala tillgångar',
        },
    }

    liquidity = {
        'current_ratio': {
            'value': round(_safe_div(current_assets, st_liabilities), 2) if _safe_div(current_assets, st_liabilities) is not None else None,
            'label': 'Balanslikviditet',
            'format': 'ratio',
            'description': 'Omsättningstillgångar / Kortfristiga skulder',
        },
        'quick_ratio': {
            'value': round(_safe_div(current_assets - inventory, st_liabilities), 2) if _safe_div(current_assets - inventory, st_liabilities) is not None else None,
            'label': 'Kassalikviditet',
            'format': 'ratio',
            'description': '(Omsättningstillgångar - Varulager) / Kortfristiga skulder',
        },
        'cash_ratio': {
            'value': round(_safe_div(cash, st_liabilities), 2) if _safe_div(cash, st_liabilities) is not None else None,
            'label': 'Kassagrad',
            'format': 'ratio',
            'description': 'Likvida medel / Kortfristiga skulder',
        },
        'working_capital': {
            'value': round(current_assets - st_liabilities, 2),
            'label': 'Rörelsekapital',
            'format': 'sek',
            'description': 'Omsättningstillgångar - Kortfristiga skulder',
        },
    }

    solvency = {
        'debt_to_equity': {
            'value': round(_safe_div(total_debt, equity), 2) if _safe_div(total_debt, equity) is not None else None,
            'label': 'Skuldsättningsgrad',
            'format': 'ratio',
            'description': 'Totala skulder / Eget kapital',
        },
        'equity_ratio': {
            'value': _safe_pct(equity, total_assets),
            'label': 'Soliditet',
            'format': 'pct',
            'description': 'Eget kapital / Totala tillgångar',
        },
        'interest_coverage': {
            'value': round(_safe_div(operating_result, fin_costs), 1) if _safe_div(operating_result, fin_costs) is not None else None,
            'label': 'Räntetäckningsgrad',
            'format': 'ratio',
            'description': 'Rörelseresultat / Finansiella kostnader',
        },
    }

    efficiency = {
        'asset_turnover': {
            'value': round(_safe_div(float(revenue), total_assets), 2) if _safe_div(float(revenue), total_assets) is not None else None,
            'label': 'Kapitalets omsättningshastighet',
            'format': 'ratio',
            'description': 'Nettoomsättning / Totala tillgångar',
        },
    }

    return {
        'profitability': profitability,
        'liquidity': liquidity,
        'solvency': solvency,
        'efficiency': efficiency,
    }


def get_multi_year_ratios(company_id, num_years=5):
    """Compute ratios for multiple fiscal years for trend charts.

    Returns: {years: [int], ratios: {name: [value|None]}}
    """
    fiscal_years = (FiscalYear.query
                    .filter_by(company_id=company_id)
                    .order_by(FiscalYear.year.asc())
                    .limit(num_years)
                    .all())

    years = []
    all_ratios = {}

    # Keys to track across years
    ratio_keys = [
        ('profitability', 'gross_margin'),
        ('profitability', 'operating_margin'),
        ('profitability', 'net_margin'),
        ('profitability', 'roe'),
        ('liquidity', 'current_ratio'),
        ('liquidity', 'quick_ratio'),
        ('solvency', 'equity_ratio'),
        ('solvency', 'debt_to_equity'),
        ('efficiency', 'asset_turnover'),
    ]

    for section, key in ratio_keys:
        all_ratios[key] = []

    for fy in fiscal_years:
        years.append(fy.year)
        ratios = get_financial_ratios(company_id, fy.id)
        for section, key in ratio_keys:
            val = ratios[section][key]['value']
            all_ratios[key].append(val)

    return {'years': years, 'ratios': all_ratios}


def get_ratio_summary(company_id, fiscal_year_id):
    """Traffic-light summary of all ratios.

    Returns list of {name, label, value, format, status, section}.
    status: 'good' (green), 'warning' (yellow), 'danger' (red).
    """
    ratios = get_financial_ratios(company_id, fiscal_year_id)
    summary = []

    for section_name, section_data in ratios.items():
        for key, ratio in section_data.items():
            value = ratio['value']
            bench = BENCHMARKS.get(key)

            if value is None or bench is None:
                status = 'secondary'
            elif bench.get('inverted'):
                # Lower is better (e.g. debt-to-equity)
                if value <= bench['low']:
                    status = 'good'
                elif value <= bench['high']:
                    status = 'warning'
                else:
                    status = 'danger'
            else:
                # Higher is better
                if value >= bench['high']:
                    status = 'good'
                elif value >= bench['low']:
                    status = 'warning'
                else:
                    status = 'danger'

            summary.append({
                'name': key,
                'label': ratio['label'],
                'value': value,
                'format': ratio['format'],
                'description': ratio['description'],
                'status': status,
                'section': section_name,
            })

    return summary
