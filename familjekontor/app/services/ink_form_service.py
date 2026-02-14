"""INK form service — computes Skatteverket INK2/INK4 form fields from accounting data.

Maps BAS kontoplan accounts to INK2R räkenskapsschema, INK2S skattemässiga
justeringar, and INK2/INK4 huvudblankett fields.  Generates PDF and SRU exports.
"""

from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from flask import render_template, current_app

from app.extensions import db
from app.models.tax import TaxReturn
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.deklaration_service import _sum_accounts


# ---------------------------------------------------------------------------
# INK2R Balansräkning (Balance Sheet) field definitions
# Each entry: (label, [account_prefixes], sign, sru_code)
# sign='debit' for assets, sign='credit' for equity/liabilities
# None prefixes = computed subtotal
# ---------------------------------------------------------------------------

INK2R_BS_FIELDS = OrderedDict([
    # --- TILLGÅNGAR (Assets) ---
    # Immateriella anläggningstillgångar
    ('2.1', ('Immateriella anläggningstillgångar', ['101', '102', '103', '104', '105'], 'debit', '7201')),
    ('2.2', ('Förskott immateriella anläggningstillgångar', ['107', '108'], 'debit', '7202')),

    # Materiella anläggningstillgångar
    ('2.3', ('Byggnader och mark', ['111', '112', '113', '114', '115', '116', '117', '118'], 'debit', '7214')),
    ('2.4', ('Maskiner och inventarier', ['121', '122', '123', '124', '125', '126'], 'debit', '7215')),
    ('2.5', ('Förbättringsutgifter på annans fastighet', ['127'], 'debit', '7216')),
    ('2.6', ('Pågående nyanläggningar och förskott', ['128', '129'], 'debit', '7217')),

    # Finansiella anläggningstillgångar
    ('2.7', ('Andelar i koncernföretag', ['131'], 'debit', '7230')),
    ('2.8', ('Andelar i intresseföretag', ['133'], 'debit', '7231')),
    ('2.9', ('Ägarintressen i övriga företag', ['135'], 'debit', '7232')),
    ('2.10', ('Fordringar hos koncern- och intresseföretag', ['132', '134'], 'debit', '7233')),
    ('2.11', ('Lån till delägare eller närstående', ['138'], 'debit', '7234')),
    ('2.12', ('Övriga långfristiga fordringar', ['136', '137', '139'], 'debit', '7235')),

    # Varulager m.m.
    ('2.13', ('Råvaror och förnödenheter', ['141'], 'debit', '7241')),
    ('2.14', ('Varor under tillverkning', ['142'], 'debit', '7242')),
    ('2.15', ('Färdiga varor och handelsvaror', ['143', '144'], 'debit', '7243')),
    ('2.16', ('Övriga lagertillgångar', ['145'], 'debit', '7244')),
    ('2.17', ('Pågående arbeten för annans räkning', ['146'], 'debit', '7245')),
    ('2.18', ('Förskott till leverantörer', ['147'], 'debit', '7246')),

    # Kortfristiga fordringar
    ('2.19', ('Kundfordringar', ['151'], 'debit', '7251')),
    ('2.20', ('Fordringar hos koncernföretag', ['166'], 'debit', '7252')),
    ('2.21', ('Övriga fordringar', ['161', '163', '164', '165', '167', '168', '169'], 'debit', '7261')),
    ('2.22', ('Upparbetad men ej fakturerad intäkt', ['162'], 'debit', '7262')),
    ('2.23', ('Förutbetalda kostnader och upplupna intäkter', ['171', '172', '173', '174', '175', '176', '179'], 'debit', '7263')),

    # Kortfristiga placeringar
    ('2.24', ('Kortfristiga placeringar koncernföretag', ['181'], 'debit', '7270')),
    ('2.25', ('Övriga kortfristiga placeringar', ['182', '183', '188', '189'], 'debit', '7271')),

    # Kassa och bank
    ('2.26', ('Kassa och bank', ['191', '192', '193', '194', '195', '196', '197', '198', '199'], 'debit', '7281')),

    # --- EGET KAPITAL OCH SKULDER ---
    # Eget kapital
    ('2.27', ('Bundet eget kapital', ['201'], 'credit', '7301')),
    ('2.28', ('Fritt eget kapital', ['207', '208', '209'], 'credit', '7302')),

    # Obeskattade reserver
    ('2.29', ('Periodiseringsfonder', ['211', '212'], 'credit', '7311')),
    ('2.30', ('Ackumulerade överavskrivningar', ['215'], 'credit', '7312')),
    ('2.31', ('Övriga obeskattade reserver', ['216', '217', '218', '219'], 'credit', '7313')),

    # Avsättningar
    ('2.32', ('Avsättningar för pensioner (tryggandelagen)', ['221'], 'credit', '7321')),
    ('2.33', ('Övriga avsättningar för pensioner', ['222'], 'credit', '7322')),
    ('2.34', ('Övriga avsättningar', ['225', '226', '227', '228', '229'], 'credit', '7323')),

    # Långfristiga skulder
    ('2.35', ('Obligationslån', ['231'], 'credit', '7331')),
    ('2.36', ('Checkräkningskredit (långfristig)', ['233'], 'credit', '7332')),
    ('2.37', ('Övriga skulder till kreditinstitut', ['234', '235'], 'credit', '7333')),
    ('2.38', ('Skulder till koncern-/intresseföretag', ['236', '237'], 'credit', '7334')),
    ('2.39', ('Övriga långfristiga skulder', ['238', '239'], 'credit', '7335')),

    # Kortfristiga skulder
    ('2.40', ('Checkräkningskredit (kortfristig)', ['2411', '2412', '2413', '2414', '2415'], 'credit', '7351')),
    ('2.41', ('Övriga skulder till kreditinstitut (kortfr.)', ['2416', '2417', '2418', '2419'], 'credit', '7352')),
    ('2.42', ('Förskott från kunder', ['242'], 'credit', '7353')),
    ('2.43', ('Pågående arbeten för annans räkning (skuld)', ['243'], 'credit', '7354')),
    ('2.44', ('Fakturerad men ej upparbetad intäkt', ['245'], 'credit', '7355')),
    ('2.45', ('Leverantörsskulder', ['244'], 'credit', '7361')),
    ('2.46', ('Växelskulder', ['246'], 'credit', '7362')),
    ('2.47', ('Skulder till koncern-/intresseföretag (kortfr.)', ['247', '248', '249'], 'credit', '7365')),
    ('2.48', ('Övriga skulder', [
        '250', '252', '253', '254', '255', '256', '257', '258', '259',
        '261', '262', '263', '264', '265', '266', '267', '268', '269',
        '271', '272', '273', '274', '275', '276', '277', '278', '279',
        '281', '282', '283', '284', '285', '286', '287', '288', '289',
    ], 'credit', '7369')),
    ('2.49', ('Skatteskulder', ['251'], 'credit', '7368')),
    ('2.50', ('Upplupna kostnader och förutbetalda intäkter', ['291', '292', '293', '294', '295', '296', '297', '298', '299'], 'credit', '7370')),
])


# ---------------------------------------------------------------------------
# INK2R Resultaträkning (Income Statement) field definitions
# ---------------------------------------------------------------------------

INK2R_IS_FIELDS = OrderedDict([
    # Rörelseintäkter
    ('3.1', ('Nettoomsättning', ['30', '31', '32', '33', '34', '35', '36', '37'], 'credit', '7410')),
    ('3.2', ('Förändring av lager av produkter i arbete, färdiga varor', ['49'], 'net', '7411')),
    ('3.3', ('Aktiverat arbete för egen räkning', ['38'], 'credit', '7412')),
    ('3.4', ('Övriga rörelseintäkter', ['39'], 'credit', '7413')),

    # Rörelsekostnader
    ('3.5', ('Råvaror och förnödenheter', ['40'], 'debit', '7511')),
    ('3.6', ('Handelsvaror', ['41', '42', '43', '44', '45', '46', '47', '48'], 'debit', '7512')),
    ('3.7', ('Övriga externa kostnader', [
        '50', '51', '52', '53', '54', '55', '56', '57', '58', '59',
        '60', '61', '62', '63', '64', '65', '66', '67', '68', '69',
    ], 'debit', '7513')),
    ('3.8', ('Personalkostnader', ['70', '71', '72', '73', '74', '75', '76'], 'debit', '7514')),
    ('3.9', ('Av- och nedskrivningar av anläggningstillgångar', ['77', '78'], 'debit', '7515')),

    # Finansiella poster
    ('3.12', ('Resultat från andelar i koncernföretag', ['801', '802'], 'credit', '7414')),
    ('3.13', ('Resultat från andelar i intresseföretag', ['810', '811', '812', '813'], 'credit', '7415')),
    ('3.14', ('Resultat från övriga finansiella anläggningstillgångar', ['820', '821', '822', '823'], 'credit', '7416')),
    ('3.16', ('Övriga ränteintäkter och liknande resultatposter', ['824', '825', '826', '827', '828', '829', '830', '831', '832', '833', '834', '835', '836', '837', '838', '839'], 'credit', '7518')),
    ('3.18', ('Räntekostnader och liknande resultatposter', ['840', '841', '842', '843', '844', '845', '846', '847', '848', '849', '850', '851', '852', '853', '854', '855', '856', '857', '858', '859', '860', '861', '862', '863', '864', '865', '866', '867', '868', '869', '870', '871', '872', '873', '874', '875', '876', '877', '878', '879', '880'], 'debit', '7521')),

    # Bokslutsdispositioner
    ('3.19', ('Lämnade koncernbidrag', ['884'], 'debit', '7524')),
    ('3.20', ('Erhållna koncernbidrag', ['883'], 'credit', '7419')),
    ('3.21', ('Återföring av periodiseringsfonder', ['8811', '8819'], 'credit', '7418')),
    ('3.22', ('Avsättning till periodiseringsfonder', ['8810'], 'debit', '7523')),
    ('3.23', ('Förändring av överavskrivningar', ['882'], 'net', '7525')),

    # Skatt
    ('3.25', ('Skatt på årets resultat', ['891', '892'], 'debit', '7526')),
])


# ---------------------------------------------------------------------------
# Subtotal definitions for balance sheet
# Each entry: (label, [field_numbers_to_sum], sru_code_or_None)
# ---------------------------------------------------------------------------

BS_SUBTOTALS = OrderedDict([
    ('sum_intangible', ('Summa immateriella anläggningstillgångar', ['2.1', '2.2'], None)),
    ('sum_tangible', ('Summa materiella anläggningstillgångar', ['2.3', '2.4', '2.5', '2.6'], None)),
    ('sum_financial_fixed', ('Summa finansiella anläggningstillgångar', ['2.7', '2.8', '2.9', '2.10', '2.11', '2.12'], None)),
    ('sum_fixed_assets', ('Summa anläggningstillgångar', ['sum_intangible', 'sum_tangible', 'sum_financial_fixed'], None)),
    ('sum_inventory', ('Summa varulager m.m.', ['2.13', '2.14', '2.15', '2.16', '2.17', '2.18'], None)),
    ('sum_receivables', ('Summa kortfristiga fordringar', ['2.19', '2.20', '2.21', '2.22', '2.23'], None)),
    ('sum_investments', ('Summa kortfristiga placeringar', ['2.24', '2.25'], None)),
    ('sum_current_assets', ('Summa omsättningstillgångar', ['sum_inventory', 'sum_receivables', 'sum_investments', '2.26'], None)),
    ('sum_assets', ('SUMMA TILLGÅNGAR', ['sum_fixed_assets', 'sum_current_assets'], None)),

    ('sum_equity', ('Summa eget kapital', ['2.27', '2.28'], None)),
    ('sum_untaxed_reserves', ('Summa obeskattade reserver', ['2.29', '2.30', '2.31'], None)),
    ('sum_provisions', ('Summa avsättningar', ['2.32', '2.33', '2.34'], None)),
    ('sum_longterm_debt', ('Summa långfristiga skulder', ['2.35', '2.36', '2.37', '2.38', '2.39'], None)),
    ('sum_shortterm_debt', ('Summa kortfristiga skulder', ['2.40', '2.41', '2.42', '2.43', '2.44', '2.45', '2.46', '2.47', '2.48', '2.49', '2.50'], None)),
    ('sum_equity_liabilities', ('SUMMA EGET KAPITAL OCH SKULDER', ['sum_equity', 'sum_untaxed_reserves', 'sum_provisions', 'sum_longterm_debt', 'sum_shortterm_debt'], None)),
])

# Subtotal definitions for income statement
IS_SUBTOTALS = OrderedDict([
    ('sum_revenue', ('Summa rörelseintäkter', ['3.1', '3.2', '3.3', '3.4'], None)),
    ('sum_costs', ('Summa rörelsekostnader', ['3.5', '3.6', '3.7', '3.8', '3.9'], None)),
    ('operating_result', ('Rörelseresultat', None, None)),  # Computed specially
    ('sum_financial', ('Summa finansiella poster', ['3.12', '3.13', '3.14', '3.16', '3.18'], None)),
    ('result_after_financial', ('Resultat efter finansiella poster', None, None)),
    ('sum_closing', ('Summa bokslutsdispositioner', ['3.19', '3.20', '3.21', '3.22', '3.23'], None)),
    ('result_before_tax', ('Resultat före skatt', None, None)),
])


# ---------------------------------------------------------------------------
# Compute functions
# ---------------------------------------------------------------------------

def _compute_fields(company_id, fiscal_year_id, field_defs):
    """Compute INK form field values from accounting data.

    Returns OrderedDict of field_number → {label, value, sru_code}.
    """
    result = OrderedDict()
    for field_nr, (label, prefixes, sign, sru_code) in field_defs.items():
        if prefixes is None:
            # Computed subtotal — handled separately
            value = Decimal('0')
        elif sign == 'net':
            # Net = credit - debit (can be positive or negative)
            value = _sum_accounts(company_id, fiscal_year_id, prefixes, sign='credit')
        else:
            value = _sum_accounts(company_id, fiscal_year_id, prefixes, sign=sign)
        result[field_nr] = {
            'label': label,
            'value': value,
            'sru_code': sru_code,
            'is_total': False,
        }
    return result


def _compute_subtotals(fields, subtotal_defs):
    """Compute subtotals by summing referenced field values.

    Adds subtotal entries into a new result dict that interleaves
    subtotals with the base fields in the correct order.
    """
    computed = {}
    for key, (label, refs, sru_code) in subtotal_defs.items():
        if refs is None:
            # Computed specially (operating_result etc.)
            computed[key] = {'label': label, 'value': Decimal('0'), 'sru_code': sru_code, 'is_total': True}
            continue
        total = Decimal('0')
        for ref in refs:
            if ref in fields:
                total += fields[ref]['value']
            elif ref in computed:
                total += computed[ref]['value']
        computed[key] = {'label': label, 'value': total, 'sru_code': sru_code, 'is_total': True}
    return computed


def compute_ink2r(company_id, fiscal_year_id):
    """Compute all INK2R (Räkenskapsschema) fields from accounting data.

    Returns dict with:
        'balance_sheet': OrderedDict of field entries (including subtotals)
        'income_statement': OrderedDict of field entries (including subtotals)
        'totals': dict with sum_assets, sum_equity_liabilities, annual_result
    """
    # --- Balance Sheet ---
    bs_fields = _compute_fields(company_id, fiscal_year_id, INK2R_BS_FIELDS)
    bs_subtotals = _compute_subtotals(bs_fields, BS_SUBTOTALS)

    # Build ordered result interleaving subtotals at correct positions
    balance_sheet = OrderedDict()

    # Section: Immateriella anläggningstillgångar
    balance_sheet['section_intangible'] = {'label': 'Immateriella anläggningstillgångar', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.1', '2.2']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_intangible'] = bs_subtotals['sum_intangible']

    # Section: Materiella anläggningstillgångar
    balance_sheet['section_tangible'] = {'label': 'Materiella anläggningstillgångar', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.3', '2.4', '2.5', '2.6']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_tangible'] = bs_subtotals['sum_tangible']

    # Section: Finansiella anläggningstillgångar
    balance_sheet['section_financial'] = {'label': 'Finansiella anläggningstillgångar', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.7', '2.8', '2.9', '2.10', '2.11', '2.12']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_financial_fixed'] = bs_subtotals['sum_financial_fixed']

    balance_sheet['sum_fixed_assets'] = bs_subtotals['sum_fixed_assets']

    # Section: Varulager
    balance_sheet['section_inventory'] = {'label': 'Varulager m.m.', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.13', '2.14', '2.15', '2.16', '2.17', '2.18']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_inventory'] = bs_subtotals['sum_inventory']

    # Section: Kortfristiga fordringar
    balance_sheet['section_receivables'] = {'label': 'Kortfristiga fordringar', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.19', '2.20', '2.21', '2.22', '2.23']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_receivables'] = bs_subtotals['sum_receivables']

    # Section: Kortfristiga placeringar
    balance_sheet['section_investments'] = {'label': 'Kortfristiga placeringar', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.24', '2.25']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_investments'] = bs_subtotals['sum_investments']

    # Kassa och bank
    balance_sheet['2.26'] = bs_fields['2.26']

    balance_sheet['sum_current_assets'] = bs_subtotals['sum_current_assets']
    balance_sheet['sum_assets'] = bs_subtotals['sum_assets']

    # --- Equity & Liabilities side ---
    balance_sheet['section_equity'] = {'label': 'Eget kapital', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.27', '2.28']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_equity'] = bs_subtotals['sum_equity']

    balance_sheet['section_untaxed'] = {'label': 'Obeskattade reserver', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.29', '2.30', '2.31']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_untaxed_reserves'] = bs_subtotals['sum_untaxed_reserves']

    balance_sheet['section_provisions'] = {'label': 'Avsättningar', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.32', '2.33', '2.34']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_provisions'] = bs_subtotals['sum_provisions']

    balance_sheet['section_longterm'] = {'label': 'Långfristiga skulder', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.35', '2.36', '2.37', '2.38', '2.39']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_longterm_debt'] = bs_subtotals['sum_longterm_debt']

    balance_sheet['section_shortterm'] = {'label': 'Kortfristiga skulder', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['2.40', '2.41', '2.42', '2.43', '2.44', '2.45', '2.46', '2.47', '2.48', '2.49', '2.50']:
        balance_sheet[f] = bs_fields[f]
    balance_sheet['sum_shortterm_debt'] = bs_subtotals['sum_shortterm_debt']

    balance_sheet['sum_equity_liabilities'] = bs_subtotals['sum_equity_liabilities']

    # --- Income Statement ---
    is_fields = _compute_fields(company_id, fiscal_year_id, INK2R_IS_FIELDS)
    is_subtotals = _compute_subtotals(is_fields, IS_SUBTOTALS)

    # Compute special subtotals
    # Rörelseresultat = revenue - costs
    operating_result = is_subtotals['sum_revenue']['value'] - is_subtotals['sum_costs']['value']
    is_subtotals['operating_result']['value'] = operating_result

    # Resultat efter finansiella poster = operating + financial
    # Financial items: income items (3.12-3.14, 3.16) are positive, cost (3.18) is negative
    financial_net = (
        is_fields['3.12']['value'] + is_fields['3.13']['value'] +
        is_fields['3.14']['value'] + is_fields['3.16']['value'] -
        is_fields['3.18']['value']
    )
    is_subtotals['result_after_financial']['value'] = operating_result + financial_net

    # Bokslutsdispositioner net effect
    closing_net = (
        is_fields['3.20']['value'] + is_fields['3.21']['value'] -
        is_fields['3.19']['value'] - is_fields['3.22']['value'] +
        is_fields['3.23']['value']  # net sign: positive = income
    )
    is_subtotals['sum_closing']['value'] = closing_net

    result_before_tax = is_subtotals['result_after_financial']['value'] + closing_net
    is_subtotals['result_before_tax']['value'] = result_before_tax

    # Årets resultat
    tax_amount = is_fields['3.25']['value']
    annual_result = result_before_tax - tax_amount

    income_statement = OrderedDict()

    # Revenue section
    income_statement['section_revenue'] = {'label': 'Rörelseintäkter', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['3.1', '3.2', '3.3', '3.4']:
        income_statement[f] = is_fields[f]
    income_statement['sum_revenue'] = is_subtotals['sum_revenue']

    # Costs section
    income_statement['section_costs'] = {'label': 'Rörelsekostnader', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['3.5', '3.6', '3.7', '3.8', '3.9']:
        income_statement[f] = is_fields[f]
    income_statement['sum_costs'] = is_subtotals['sum_costs']

    income_statement['operating_result'] = is_subtotals['operating_result']

    # Financial section
    income_statement['section_financial'] = {'label': 'Finansiella poster', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['3.12', '3.13', '3.14', '3.16', '3.18']:
        income_statement[f] = is_fields[f]
    income_statement['result_after_financial'] = is_subtotals['result_after_financial']

    # Closing entries section
    income_statement['section_closing'] = {'label': 'Bokslutsdispositioner', 'value': None, 'sru_code': None, 'is_section': True}
    for f in ['3.19', '3.20', '3.21', '3.22', '3.23']:
        income_statement[f] = is_fields[f]
    income_statement['sum_closing'] = is_subtotals['sum_closing']

    income_statement['result_before_tax'] = is_subtotals['result_before_tax']

    # Tax
    income_statement['3.25'] = is_fields['3.25']

    # Årets resultat
    if annual_result >= 0:
        income_statement['3.26'] = {'label': 'Årets resultat (vinst)', 'value': annual_result, 'sru_code': '7326', 'is_total': True}
        income_statement['3.27'] = {'label': 'Årets resultat (förlust)', 'value': Decimal('0'), 'sru_code': '7327', 'is_total': True}
    else:
        income_statement['3.26'] = {'label': 'Årets resultat (vinst)', 'value': Decimal('0'), 'sru_code': '7326', 'is_total': True}
        income_statement['3.27'] = {'label': 'Årets resultat (förlust)', 'value': abs(annual_result), 'sru_code': '7327', 'is_total': True}

    return {
        'balance_sheet': balance_sheet,
        'income_statement': income_statement,
        'totals': {
            'sum_assets': bs_subtotals['sum_assets']['value'],
            'sum_equity_liabilities': bs_subtotals['sum_equity_liabilities']['value'],
            'annual_result': annual_result,
        },
    }


def compute_ink2s(tax_return):
    """Compute INK2S (Skattemässiga justeringar) fields from TaxReturn.

    Maps existing TaxReturn adjustment fields to INK2S form fields 4.1-4.16.
    """
    tr = tax_return
    net_income = tr.net_income or Decimal('0')

    # Tax on result (always added back in 4.3a)
    tax_booked = _sum_accounts(
        tr.company_id, tr.fiscal_year_id, ['891', '892'], sign='debit'
    ) if tr.fiscal_year_id else Decimal('0')

    fields = OrderedDict()

    # Årets resultat
    if net_income >= 0:
        fields['4.1'] = {'label': 'Årets resultat, vinst', 'value': net_income, 'sru_code': '7401'}
        fields['4.2'] = {'label': 'Årets resultat, förlust', 'value': Decimal('0'), 'sru_code': '7402'}
    else:
        fields['4.1'] = {'label': 'Årets resultat, vinst', 'value': Decimal('0'), 'sru_code': '7401'}
        fields['4.2'] = {'label': 'Årets resultat, förlust', 'value': abs(net_income), 'sru_code': '7402'}

    # Bokförda kostnader som inte ska dras av (section header)
    fields['section_4.3'] = {'label': 'Bokförda kostnader som inte ska dras av', 'value': None, 'sru_code': None, 'is_section': True}
    fields['4.3a'] = {'label': 'Skatt på årets resultat', 'value': tax_booked, 'sru_code': '7403'}
    fields['4.3c'] = {'label': 'Övriga ej avdragsgilla kostnader', 'value': tr.non_deductible_expenses or Decimal('0'), 'sru_code': '7405'}

    # Ej skattepliktiga intäkter
    fields['section_4.5'] = {'label': 'Bokförda intäkter som inte är skattepliktiga', 'value': None, 'sru_code': None, 'is_section': True}
    fields['4.5c'] = {'label': 'Övriga ej skattepliktiga intäkter', 'value': tr.non_taxable_income or Decimal('0'), 'sru_code': '7408'}

    # Skattemässiga avskrivningar
    fields['4.9'] = {'label': 'Skattemässig justering avskrivningar', 'value': tr.depreciation_tax_diff or Decimal('0'), 'sru_code': '7412'}

    # Övriga justeringar
    fields['4.13'] = {'label': 'Övriga skattemässiga justeringar (tillkommer)', 'value': tr.other_adjustments_add or Decimal('0'), 'sru_code': '7416'}
    fields['4.13b'] = {'label': 'Övriga skattemässiga justeringar (avgår)', 'value': tr.other_adjustments_deduct or Decimal('0'), 'sru_code': '7417'}

    # Outnyttjat underskott
    fields['4.14a'] = {'label': 'Outnyttjat underskott från tidigare år', 'value': tr.previous_deficit or Decimal('0'), 'sru_code': '7418'}

    # Compute taxable income
    additions = (
        fields['4.3a']['value'] + fields['4.3c']['value'] +
        fields['4.9']['value'] + fields['4.13']['value']
    )
    deductions = fields['4.5c']['value'] + fields['4.13b']['value']

    taxable_before = net_income + additions - deductions
    deficit = fields['4.14a']['value']

    if taxable_before > 0:
        taxable_income = max(Decimal('0'), taxable_before - deficit)
    else:
        taxable_income = taxable_before  # Negative = underskott

    if taxable_income >= 0:
        fields['4.15'] = {'label': 'Överskott av näringsverksamhet', 'value': taxable_income, 'sru_code': '7419', 'is_total': True}
        fields['4.16'] = {'label': 'Underskott av näringsverksamhet', 'value': Decimal('0'), 'sru_code': '7420', 'is_total': True}
    else:
        fields['4.15'] = {'label': 'Överskott av näringsverksamhet', 'value': Decimal('0'), 'sru_code': '7419', 'is_total': True}
        fields['4.16'] = {'label': 'Underskott av näringsverksamhet', 'value': abs(taxable_income), 'sru_code': '7420', 'is_total': True}

    return fields


def compute_ink2_main(ink2s_data):
    """Compute INK2 huvudblankett fields from INK2S results."""
    surplus = ink2s_data.get('4.15', {}).get('value', Decimal('0'))
    deficit = ink2s_data.get('4.16', {}).get('value', Decimal('0'))

    return OrderedDict([
        ('1.1', {'label': 'Överskott av näringsverksamhet', 'value': surplus, 'sru_code': '7011'}),
        ('1.2', {'label': 'Underskott av näringsverksamhet', 'value': deficit, 'sru_code': '7012'}),
    ])


def compute_ink4r(company_id, fiscal_year_id):
    """Compute INK4R fields — same structure as INK2R for HB/KB companies."""
    # INK4R uses the same account structure as INK2R
    return compute_ink2r(company_id, fiscal_year_id)


def compute_ink4s(tax_return):
    """Compute INK4S fields — same as INK2S but for HB/KB (no corporate tax)."""
    # Same adjustment logic, but no corporate tax calculation at entity level
    return compute_ink2s(tax_return)


def compute_all_ink_data(return_id):
    """Compute all INK form data for a given tax return.

    Returns dict with ink_type, ink_r, ink_s, ink_main, company, fy, tr.
    """
    tr = db.session.get(TaxReturn, return_id)
    if not tr:
        return None

    company = db.session.get(Company, tr.company_id)
    fy = db.session.get(FiscalYear, tr.fiscal_year_id)

    if tr.return_type == 'ink4':
        ink_r = compute_ink4r(tr.company_id, tr.fiscal_year_id)
        ink_s = compute_ink4s(tr)
        ink_type = 'INK4'
    else:
        ink_r = compute_ink2r(tr.company_id, tr.fiscal_year_id)
        ink_s = compute_ink2s(tr)
        ink_type = 'INK2'

    ink_main = compute_ink2_main(ink_s)

    return {
        'ink_type': ink_type,
        'ink_r': ink_r,
        'ink_s': ink_s,
        'ink_main': ink_main,
        'company': company,
        'fy': fy,
        'tr': tr,
    }


# ---------------------------------------------------------------------------
# SRU file generation
# ---------------------------------------------------------------------------

def generate_sru_file(return_id):
    """Generate SRU file content as BytesIO for Skatteverket digital submission."""
    data = compute_all_ink_data(return_id)
    if not data:
        return None

    tr = data['tr']
    company = data['company']
    ink_type = data['ink_type']
    tax_year = tr.tax_year

    # Org number without dash
    org_nr = (company.org_number or '').replace('-', '').replace(' ', '')

    # Blankett suffix
    blankett_r = f'{ink_type}R-{tax_year}P4'
    blankett_s = f'{ink_type}S-{tax_year}P4'
    blankett_main = f'{ink_type}-{tax_year}P4'

    lines = []

    # Header
    lines.append('#DATABESKRIVNING_START')
    lines.append('#PRODUKT SRU')
    lines.append(f'#SESSION {datetime.now().strftime("%Y%m%d%H%M%S")}')
    lines.append('#FLAGGA 0')
    lines.append('#PROGRAM Familjekontor')
    lines.append('#DATABESKRIVNING_SLUT')
    lines.append('#MEDESSION_START')
    lines.append(f'#UPPGIFTSLAMNARE {org_nr}')
    lines.append(f'#BLANKETT {blankett_r}')
    lines.append('#SYSTEMINFO Familjekontor')
    lines.append('#MEDESSION_SLUT')

    def _emit_fields(blankett, fields_dict):
        """Emit #FLT lines for all fields with SRU codes and values."""
        lines.append(f'#BLANKETT {blankett}')
        for key, field in fields_dict.items():
            sru = field.get('sru_code')
            val = field.get('value')
            if sru and val is not None:
                # Round to integer SEK
                int_val = int(round(float(val)))
                lines.append(f'#FLT {sru} {int_val}')

    # INK2R/INK4R - Balance sheet
    _emit_fields(blankett_r, data['ink_r']['balance_sheet'])
    # INK2R/INK4R - Income statement
    _emit_fields(blankett_r, data['ink_r']['income_statement'])

    # INK2S/INK4S - Tax adjustments
    _emit_fields(blankett_s, data['ink_s'])

    # INK2/INK4 - Main form
    _emit_fields(blankett_main, data['ink_main'])

    content = '\n'.join(lines) + '\n'
    output = BytesIO(content.encode('iso-8859-1'))
    output.seek(0)
    return output


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_ink_pdf(return_id):
    """Generate INK form PDF using WeasyPrint.

    Returns BytesIO with PDF content, or HTML string if WeasyPrint unavailable.
    """
    data = compute_all_ink_data(return_id)
    if not data:
        return None

    template = 'tax/ink2_pdf.html' if data['ink_type'] == 'INK2' else 'tax/ink4_pdf.html'

    html = render_template(
        template,
        company=data['company'],
        fy=data['fy'],
        tr=data['tr'],
        ink_type=data['ink_type'],
        ink_main=data['ink_main'],
        balance_sheet=data['ink_r']['balance_sheet'],
        income_statement=data['ink_r']['income_statement'],
        ink_s=data['ink_s'],
        totals=data['ink_r']['totals'],
    )

    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        return html

    output = BytesIO()
    HTML(string=html).write_pdf(output)
    output.seek(0)
    return output
