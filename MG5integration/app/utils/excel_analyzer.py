"""Analyze Monitor G5 Excel exports to discover schema and column mappings."""

import pandas as pd
from pathlib import Path
from collections import Counter


# Mapping of Swedish Excel column headers to English model field names.
# Organized by source file / model domain.
COLUMN_MAPPINGS = {
    # kontoplan.xlsx -> Account
    'kontoplan': {
        'Konto': 'account_number',
        'Benämning': 'description',
        'Kontotyp': 'account_type',
        'SRU-kod': 'sru_code',
        'D/K': 'debit_credit',
    },
    # verlista.xlsx -> Verification
    'verlista': {
        'Ver.nr': 'verification_number',
        'Ver.datum': 'date',
        'Verifikationstext': 'text',
        'Rättning till/Kopia av': 'correction_ref',
        'Rättad av/Kopia av': 'corrected_by',
        'Preliminär': 'preliminary',
        'Konto': 'account',
        'Benämning': 'account_description',
        'Kst': 'cost_center',
        'Kb': 'profit_center',
        'Proj.': 'project',
        'Specifikation': 'specification',
        'Debet': 'debit',
        'Kredit': 'credit',
    },
    # projektuppf.xlsx -> Project
    'projektuppf': {
        'Projektnummer': 'project_number',
        'Benämning': 'description',
        'Kundnamn': 'customer',
        'Startdatum': 'start_date',
        'Slutdatum': 'end_date',
        'Utf., kostnad': 'executed_cost',
        'Utf., intäkt': 'executed_income',
        'Förvän. kostnad': 'expected_cost',
        'Förvän. intäkt': 'expected_income',
        'Rest. kostnad': 'remaining_cost',
        'Rest. intäkt': 'remaining_income',
    },
    # projectadjustments.xlsx -> ProjectAdjustment
    'projectadjustments': {
        'Projektnummer': 'project_number',
        'Benämning': 'description',
        'Kundnamn': 'customer',
        'Accured': 'include_in_accrued',
        'Contingency': 'contingency',
        'Incomeadj': 'income_adjustment',
        'Costcalcadj': 'cost_calc_adjustment',
        'puradj': 'purchase_adjustment',
        'Closing': 'closing_date',
    },
    # tiduppfoljning.xlsx -> TimeTracking
    'tiduppfoljning': {
        'Projektnummer': 'project_number',
        'Benämning': 'description',
        'Budget': 'budget',
        'Planerad tid': 'planned_time',
        'Utfall': 'actual_hours',
        'Förväntat': 'expected_hours',
        'Prognos': 'forecast',
        'Rest.': 'remaining',
    },
    # CO_proj_crossref.xlsx -> CustomerOrderProjectMap
    'CO_proj_crossref': {
        'Ordernummer': 'order_number',
        'Projekt': 'project_number',
    },
    # kundorderforteckning.xlsx -> CustomerOrder
    'kundorderforteckning': {
        'Ordernummer': 'order_number',
        'Projekt': 'project',
        'Projektbenämning': 'project_description',
        'Kundnummer': 'customer_number',
        'Kundnamn': 'customer_name',
        'Kundens ordernummer': 'customer_order_number',
        'Orderdatum': 'order_date',
        'Artikelnummer': 'article_number',
        'Benämning': 'article_description',
        'Restbelopp': 'remaining_amount',
        'Restbelopp val.': 'remaining_amount_currency',
        'Betalningsvillkor': 'payment_terms',
        'Valuta': 'currency',
        'Valutakurs': 'exchange_rate',
        'À-pris': 'unit_price',
        'À-pris val.': 'unit_price_currency',
    },
    # inkoporderforteckning.xlsx -> PurchaseOrder
    'inkoporderforteckning': {
        'Tillv order': 'manufacturing_order_ref',
        'Projekt': 'project',
        'Tillverkningsorder': 'manufacturing_order',
        'Ordernummer': 'order_number',
        'Pos.': 'position',
        'Artikelnummer': 'article_number',
        'Benämning': 'article_description',
        'Leveransdatum': 'delivery_date',
        'À-pris': 'unit_price',
        'À-pris val.': 'unit_price_currency',
        'Beställt antal': 'quantity_ordered',
        'Inlevererat antal': 'quantity_received',
        'Resterande antal': 'quantity_remaining',
        'Bekräftad – Rad': 'confirmed',
        'Restbelopp': 'remaining_amount',
        'Belopp val.': 'amount_currency',
        'Konto': 'account',
        'Inköpsorder': 'is_purchase_order',
        'Projektbenämning': 'project_description',
        'Leverantörsnamn': 'supplier_name',
        'Lev. ordernr': 'supplier_order_number',
        'Orderdatum': 'order_date',
        'Kundorder': 'customer_order',
        'Postadress – Land': 'country',
        'Valuta': 'currency',
        'Önskat leveransdatum': 'requested_delivery_date',
        'Godsmärke': 'goods_marking',
    },
    # Offertförteckning-*.xlsx -> Quote
    'offertforteckning': {
        'Offertnummer': 'quote_number',
        'Lagerställe': 'warehouse',
        'Ordertyp': 'order_type',
        'Kund': 'customer_number',
        'Namn': 'customer_name',
        'Status': 'status',
        'Förfrågannr': 'inquiry_number',
        'Giltighet': 'validity_date',
        'Kundens referens': 'customer_reference',
        'Telefonnummer': 'phone',
        'Pos.': 'position',
        'Artikelnummer': 'article_number',
        'Benämning': 'article_description',
        'Leveransdatum': 'delivery_date',
        'Antal': 'quantity',
        'À-pris': 'unit_price',
        'Rabatt': 'discount',
        'Ställpris': 'setup_price',
        'Belopp': 'amount',
    },
    # Orderingång-*.xlsx -> OrderIntake
    'orderingang': {
        'Loggdatum': 'log_date',
        'Ordernummer': 'order_number',
        'Kund': 'customer_number',
        'Kundnamn': 'customer_name',
        'Ordertyp': 'order_type',
        'Säljare': 'salesperson',
        'Pos.': 'position',
        'Artikelnummer': 'article_number',
        'Benämning': 'article_description',
        'Antal': 'quantity',
        'Pris': 'price',
        'Värde': 'value',
    },
    # faktureringslogg.xlsx -> InvoiceLog
    'faktureringslogg': {
        'Fakturanummer': 'invoice_number',
        'Fakt.datum': 'date',
        'Projekt': 'project',
        'Ordernummer': 'order_number',
        'Kundnamn faktura': 'customer_name',
        'Artikel – Artikelnummer': 'article_category',
        'Artikelnummer': 'article_number',
        'À-pris': 'unit_price',
        'À-pris val.': 'unit_price_currency',
        'Belopp': 'amount',
        'Belopp val.': 'amount_currency',
        'Valutakurs': 'exchange_rate',
        'Terminskurs': 'forward_rate',
    },
    # valutakurser.xlsx -> ExchangeRate
    'valutakurser': {
        'DATE': 'date',
        'DKK': 'dkk',
        'EUR': 'eur',
        'GBP': 'gbp',
        'NOK': 'nok',
        'SEK': 'sek',
        'USD': 'usd',
    },
    # Artikellista-*.xlsx -> Article
    'artikellista': {
        'Artikelnummer': 'article_number',
        'Artikelbenämning': 'description',
        'Artikelns PIA-saldo': 'wip_balance',
        'Lagerplats': 'location',
        'Serienummer': 'serial_number',
        'Batchnummer': 'batch_number',
        'Klarerat saldo (inkl. utgånget)': 'cleared_balance',
        'Tillgängligt saldo': 'available_balance',
        'Totalt saldo': 'total_balance',
    },
    # Min stock per artikel.xlsx -> MinimumStock
    'min_stock': {
        'Lagertyp': 'stock_type',
        'Artikelnummer': 'article_number',
        'OD': 'outer_diameter',
        'GRADE': 'grade',
        'Beställt antal': 'ordered_quantity',
    },
}

# Human-readable labels and canonical filenames for upload UI
UPLOAD_TABLE_INFO = {
    'kontoplan': {'label': 'Kontoplan (Chart of Accounts)', 'canonical_filename': 'kontoplan.xlsx'},
    'verlista': {'label': 'Verlista (Journal Entries)', 'canonical_filename': 'verlista.xlsx'},
    'projektuppf': {'label': 'Projektuppföljning (Project Follow-up)', 'canonical_filename': 'projektuppf.xlsx'},
    'projectadjustments': {'label': 'Project Adjustments', 'canonical_filename': 'projectadjustments.xlsx'},
    'tiduppfoljning': {'label': 'Tiduppföljning (Time Tracking)', 'canonical_filename': 'tiduppfoljning.xlsx'},
    'CO_proj_crossref': {'label': 'CO-Project Cross Reference', 'canonical_filename': 'CO_proj_crossref.xlsx'},
    'kundorderforteckning': {'label': 'Kundorderförteckning (Customer Orders)', 'canonical_filename': 'kundorderforteckning.xlsx'},
    'inkoporderforteckning': {'label': 'Inköpsorderförteckning (Purchase Orders)', 'canonical_filename': 'inkoporderforteckning.xlsx'},
    'offertforteckning': {'label': 'Offertförteckning (Quotes)', 'canonical_filename': 'Offertförteckning.xlsx'},
    'orderingang': {'label': 'Orderingång (Order Intake)', 'canonical_filename': 'Orderingång.xlsx'},
    'faktureringslogg': {'label': 'Faktureringslogg (Invoice Log)', 'canonical_filename': 'faktureringslogg.xlsx'},
    'valutakurser': {'label': 'Valutakurser (Exchange Rates)', 'canonical_filename': 'valutakurser.xlsx'},
    'artikellista': {'label': 'Artikellista (Articles)', 'canonical_filename': 'Artikellista.xlsx'},
    'min_stock': {'label': 'Min Stock per Artikel', 'canonical_filename': 'Min stock.xlsx'},
}

# Map file name patterns to mapping keys
FILE_PATTERN_MAP = {
    'kontoplan': 'kontoplan',
    'verlista': 'verlista',
    'projektuppf': 'projektuppf',
    'projectadjustments': 'projectadjustments',
    'tiduppfoljning': 'tiduppfoljning',
    'CO_proj_crossref': 'CO_proj_crossref',
    'kundorderforteckning': 'kundorderforteckning',
    'inkoporderforteckning': 'inkoporderforteckning',
    'Offertförteckning': 'offertforteckning',
    'Orderingång': 'orderingang',
    'faktureringslogg': 'faktureringslogg',
    'valutakurser': 'valutakurser',
    'Artikellista': 'artikellista',
    'Min stock': 'min_stock',
}


def analyze_all_exports(folder_path):
    """Analyze all Excel files in folder. Returns dict of file info."""
    results = {}
    folder = Path(folder_path)

    for excel_file in sorted(folder.glob('*.xlsx')):
        try:
            df = pd.read_excel(excel_file, nrows=0)
            row_count = len(pd.read_excel(excel_file))
            results[excel_file.name] = {
                'columns': list(df.columns),
                'column_count': len(df.columns),
                'row_count': row_count,
            }
        except Exception as e:
            results[excel_file.name] = {'error': str(e)}

    return results


def find_common_columns(analysis):
    """Find columns that appear in multiple exports."""
    all_columns = []
    for file_data in analysis.values():
        if 'columns' in file_data:
            all_columns.extend(file_data['columns'])
    return Counter(all_columns).most_common()


def get_mapping_for_file(filename):
    """Get the column mapping dict for a given filename."""
    for pattern, key in FILE_PATTERN_MAP.items():
        if pattern.lower() in filename.lower():
            return COLUMN_MAPPINGS.get(key)
    return None


def find_file_for_key(folder_path, key):
    """Find the Excel file matching a mapping key in the folder.

    Prefers the canonical upload filename (exact match) over pattern match
    so that newly uploaded files are found before older originals.
    """
    folder = Path(folder_path)

    # 1. Try canonical filename first (from upload)
    info = UPLOAD_TABLE_INFO.get(key)
    if info:
        canonical = folder / info['canonical_filename']
        if canonical.exists():
            return canonical

    # 2. Fall back to pattern match
    for pattern, mapping_key in FILE_PATTERN_MAP.items():
        if mapping_key == key:
            for f in folder.glob('*.xlsx'):
                if pattern.lower() in f.name.lower():
                    return f
    return None
