"""AI-enhanced services for invoice analysis, account suggestion,
natural language queries, and annual report text generation.

All functions degrade gracefully when Ollama is unavailable.
"""

import re
import logging
from decimal import Decimal

from flask import current_app
from app.extensions import db
from app.utils.ai_client import generate_text, generate_structured, is_ollama_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Invoice OCR & Analysis
# ---------------------------------------------------------------------------

INVOICE_SYSTEM_PROMPT = """Du är en expert på svenska fakturor. Analysera texten och extrahera:
- supplier_name: Leverantörens namn
- supplier_org_number: Organisationsnummer (format: 556XXX-XXXX)
- invoice_number: Fakturanummer
- invoice_date: Fakturadatum (YYYY-MM-DD)
- due_date: Förfallodatum (YYYY-MM-DD)
- total_amount: Totalbelopp inkl moms (nummer)
- vat_amount: Momsbelopp (nummer)
- currency: Valuta (SEK om ej angivet)
- description: Kort beskrivning av vad fakturan avser

Svara med JSON. Använd null för saknade fält."""


def analyze_invoice_text(text_content):
    """Analyze invoice text using AI to extract structured data.

    Args:
        text_content: Raw text from invoice (OCR or PDF extraction).

    Returns:
        Dict with extracted fields, or None if AI unavailable.
    """
    if not text_content or not is_ollama_available():
        return _regex_invoice_fallback(text_content)

    prompt = f'Analysera denna faktura:\n\n{text_content[:3000]}'
    result = generate_structured(prompt, system_prompt=INVOICE_SYSTEM_PROMPT)

    if result:
        return result

    # Fall back to regex
    return _regex_invoice_fallback(text_content)


def _regex_invoice_fallback(text):
    """Simple regex-based invoice data extraction as fallback."""
    if not text:
        return None

    data = {}

    # Invoice number
    m = re.search(r'[Ff]aktura\s*nr?\.?\s*[:.]?\s*(\S+)', text)
    if m:
        data['invoice_number'] = m.group(1)

    # Org number
    m = re.search(r'(\d{6}-\d{4})', text)
    if m:
        data['supplier_org_number'] = m.group(1)

    # Total amount
    m = re.search(r'(?:totalt?|att betala|summa)\s*[:.]?\s*([\d\s,.]+)\s*(?:kr|SEK)?', text, re.I)
    if m:
        amt = m.group(1).replace(' ', '').replace(',', '.')
        try:
            data['total_amount'] = float(amt)
        except ValueError:
            pass

    # VAT amount
    m = re.search(r'moms\s*[:.]?\s*([\d\s,.]+)\s*(?:kr|SEK)?', text, re.I)
    if m:
        amt = m.group(1).replace(' ', '').replace(',', '.')
        try:
            data['vat_amount'] = float(amt)
        except ValueError:
            pass

    # Dates (YYYY-MM-DD)
    dates = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
    if len(dates) >= 1:
        data['invoice_date'] = dates[0]
    if len(dates) >= 2:
        data['due_date'] = dates[1]

    return data if data else None


# ---------------------------------------------------------------------------
# Account Suggestion
# ---------------------------------------------------------------------------

ACCOUNT_SYSTEM_PROMPT = """Du är en svensk redovisningsexpert som följer BAS-kontoplanen.
Givet en transaktionsbeskrivning, föreslå det mest troliga BAS-kontot.
Svara med JSON: {"account_number": "XXXX", "account_name": "namn", "confidence": 0.0-1.0, "reasoning": "kort motivering"}"""

# Common Swedish transaction patterns → BAS accounts
ACCOUNT_PATTERNS = {
    r'hyra|lokalkostnad|lokal': ('5010', 'Lokalhyra'),
    r'telefon|mobil|tele': ('5060', 'Telefon och kommunikation'),
    r'\bel\b|energi|fjärrvärme': ('5020', 'El och uppvärmning'),
    r'internet|bredband': ('5060', 'Telefon och kommunikation'),
    r'porto|frakt': ('5710', 'Frakt och transport'),
    r'försäkring': ('6310', 'Företagsförsäkring'),
    r'revision|revisor': ('6420', 'Revision'),
    r'bokför|redovisning': ('6530', 'Redovisning'),
    r'juridisk|advokat': ('6530', 'Övriga externa tjänster'),
    r'kontorsmaterial|papper': ('6110', 'Kontorsmaterial'),
    r'representation': ('6071', 'Representation avdragsgill'),
    r'resor|tåg|flyg': ('5800', 'Resekostnader'),
    r'bränsle|bensin|diesel': ('5611', 'Drivmedel'),
    r'parkering': ('5612', 'Parkering'),
    r'mat|lunch|fika': ('6072', 'Personalrepresentation'),
    r'lön|salary': ('7010', 'Löner tjänstemän'),
    r'arbetsgivaravgift': ('7510', 'Arbetsgivaravgifter'),
    r'ränteintäkt': ('8310', 'Ränteintäkter'),
    r'räntekostnad': ('8410', 'Räntekostnader'),
    r'utdelning': ('8210', 'Utdelning'),
    r'programvara|licens|saas|software': ('5420', 'Programvaror'),
    r'annons|reklam|marknadsföring': ('5910', 'Annons och reklam'),
}


def suggest_account(description, amount=None, transaction_type=None, supplier_id=None):
    """Suggest a BAS account for a bank transaction.

    Args:
        description: Transaction description text.
        amount: Transaction amount (positive/negative).
        transaction_type: Optional hint ('expense', 'income').
        supplier_id: Optional supplier ID to check learned mappings first.

    Returns:
        Dict with account_number, account_name, confidence, reasoning.
    """
    if not description:
        return None

    # Check supplier learned mappings first (highest confidence)
    if supplier_id:
        mapping = _check_supplier_mappings(supplier_id, description)
        if mapping:
            return mapping

    # Try regex patterns
    desc_lower = description.lower()
    for pattern, (acct_num, acct_name) in ACCOUNT_PATTERNS.items():
        if re.search(pattern, desc_lower):
            return {
                'account_number': acct_num,
                'account_name': acct_name,
                'confidence': 0.8,
                'reasoning': f'Matchat mönster: {pattern}',
            }

    # Fall back to AI if available
    if is_ollama_available():
        prompt = f'Transaktion: "{description}"'
        if amount:
            prompt += f'\nBelopp: {amount} SEK'
        if transaction_type:
            prompt += f'\nTyp: {transaction_type}'

        result = generate_structured(prompt, system_prompt=ACCOUNT_SYSTEM_PROMPT)
        if result and 'account_number' in result:
            return result

    return None


def _check_supplier_mappings(supplier_id, description):
    """Check supplier's learned mappings for a matching description."""
    from app.models.invoice import Supplier

    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or not supplier.learned_mappings:
        return None

    desc_lower = description.strip().lower()
    mappings = supplier.learned_mappings

    # Exact match
    if desc_lower in mappings:
        acct_num = mappings[desc_lower]
        return {
            'account_number': acct_num,
            'account_name': f'Konto {acct_num}',
            'confidence': 0.95,
            'reasoning': f'Inlärd mappning från leverantör {supplier.name}',
        }

    # Substring match — check if any learned key is contained in description
    for key, acct_num in mappings.items():
        if key in desc_lower or desc_lower in key:
            return {
                'account_number': acct_num,
                'account_name': f'Konto {acct_num}',
                'confidence': 0.90,
                'reasoning': f'Delvis matchning från leverantör {supplier.name}',
            }

    return None


def record_supplier_mapping(supplier_id, description, account_number):
    """Record a description→account mapping for a supplier.

    Returns True on success, False if supplier not found.
    """
    from app.models.invoice import Supplier

    supplier = db.session.get(Supplier, supplier_id)
    if not supplier:
        return False

    supplier.learn_mapping(description, account_number)
    db.session.commit()
    return True


def get_supplier_mappings(supplier_id):
    """Get all learned mappings for a supplier.

    Returns dict of {description: account_number} or empty dict.
    """
    from app.models.invoice import Supplier

    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or not supplier.learned_mappings:
        return {}
    return dict(supplier.learned_mappings)


def delete_supplier_mapping(supplier_id, description_key):
    """Delete a single mapping from a supplier's learned mappings.

    Returns True on success, False if not found.
    """
    from app.models.invoice import Supplier

    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or not supplier.learned_mappings:
        return False

    mappings = dict(supplier.learned_mappings)
    if description_key in mappings:
        del mappings[description_key]
        supplier.learned_mappings = mappings if mappings else None
        db.session.commit()
        return True
    return False


def batch_categorize(transactions):
    """Categorize a batch of transactions.

    Args:
        transactions: List of dicts with 'description' and optionally 'amount'.

    Returns:
        List of suggestion dicts (same order as input).
    """
    results = []
    for txn in transactions:
        suggestion = suggest_account(
            txn.get('description', ''),
            amount=txn.get('amount'),
        )
        results.append(suggestion)
    return results


# ---------------------------------------------------------------------------
# Natural Language Financial Queries
# ---------------------------------------------------------------------------

QUERY_SYSTEM_PROMPT = """Du är en AI-assistent för ett svenskt bokföringssystem (PsalmGears).
Du hjälper användare att förstå sin ekonomi genom att svara på frågor.
Svara alltid på svenska. Var koncis men informativ.
Om du inte kan svara, förklara vad som behövs."""


def interpret_financial_query(query, company_data=None):
    """Interpret a natural language financial query.

    Args:
        query: User's question in Swedish.
        company_data: Optional dict with company financial context.

    Returns:
        Dict with 'answer', 'query_type', and optionally 'data'.
    """
    if not query:
        return {'answer': 'Ställ en fråga om din ekonomi.', 'query_type': 'empty'}

    # Simple keyword-based routing (works without AI)
    query_lower = query.lower()

    if any(w in query_lower for w in ['vinst', 'resultat', 'intäkt', 'omsättning']):
        query_type = 'pnl'
    elif any(w in query_lower for w in ['balans', 'tillgång', 'skuld', 'eget kapital']):
        query_type = 'balance'
    elif any(w in query_lower for w in ['moms', 'vat']):
        query_type = 'vat'
    elif any(w in query_lower for w in ['skatt', 'deklaration', 'bolagsskatt']):
        query_type = 'tax'
    elif any(w in query_lower for w in ['lön', 'salary', 'personal']):
        query_type = 'salary'
    elif any(w in query_lower for w in ['likviditet', 'kassaflöde', 'cash']):
        query_type = 'cashflow'
    elif any(w in query_lower for w in ['faktur', 'invoice', 'kund', 'leverantör']):
        query_type = 'invoices'
    else:
        query_type = 'general'

    # Build context from company data
    context = ''
    if company_data:
        context = _build_context_string(company_data)

    # Try AI for natural language response
    if is_ollama_available():
        prompt = f'Fråga: {query}'
        if context:
            prompt += f'\n\nKontext:\n{context}'

        answer = generate_text(prompt, system_prompt=QUERY_SYSTEM_PROMPT)
        if answer:
            return {'answer': answer, 'query_type': query_type}

    # Fallback: route to appropriate report
    route_hints = {
        'pnl': 'Se Resultaträkning under Rapporter för detaljerad information.',
        'balance': 'Se Balansräkning under Rapporter.',
        'vat': 'Se Momsrapporter under Skatt.',
        'tax': 'Se Inkomstdeklaration under Skatt.',
        'salary': 'Se Löneöversikt under Rapporter.',
        'cashflow': 'Se Kassaflödesanalys under Koncernrapporter.',
        'invoices': 'Se Fakturor i huvudmenyn.',
        'general': 'Jag kan hjälpa med frågor om resultat, balans, moms, skatt, löner och fakturor.',
    }

    answer = route_hints.get(query_type, route_hints['general'])
    if company_data:
        answer = _add_data_summary(query_type, company_data) + ' ' + answer

    return {'answer': answer, 'query_type': query_type}


def _build_context_string(data):
    """Build a context string from company financial data."""
    parts = []
    if 'revenue' in data:
        parts.append(f"Nettoomsättning: {data['revenue']:,.0f} SEK")
    if 'expenses' in data:
        parts.append(f"Kostnader: {data['expenses']:,.0f} SEK")
    if 'net_income' in data:
        parts.append(f"Årets resultat: {data['net_income']:,.0f} SEK")
    if 'total_assets' in data:
        parts.append(f"Tillgångar: {data['total_assets']:,.0f} SEK")
    if 'equity' in data:
        parts.append(f"Eget kapital: {data['equity']:,.0f} SEK")
    return '\n'.join(parts)


def _add_data_summary(query_type, data):
    """Add a brief data summary based on query type."""
    if query_type == 'pnl' and 'net_income' in data:
        return f"Årets resultat: {data['net_income']:,.0f} SEK."
    if query_type == 'balance' and 'total_assets' in data:
        return f"Totala tillgångar: {data['total_assets']:,.0f} SEK."
    return ''


# ---------------------------------------------------------------------------
# Annual Report Text Generation
# ---------------------------------------------------------------------------

VERKSAMHET_SYSTEM_PROMPT = """Du är en expert på svenska årsredovisningar (K2).
Skriv en kort förvaltningsberättelse (verksamhetsbeskrivning) baserat på de
ekonomiska nyckeltalen. Max 3-4 meningar. Formellt språk. Inga spekulationer."""

HANDELSER_SYSTEM_PROMPT = """Du är en expert på svenska årsredovisningar (K2).
Lista väsentliga händelser under räkenskapsåret baserat på bokföringsdata.
Kort och sakligt. Punktlista med max 3-5 punkter."""


def generate_verksamhetsbeskrivning(company_name, fiscal_year, financial_data):
    """Generate a draft förvaltningsberättelse (management report) text.

    Args:
        company_name: Company name.
        fiscal_year: Year (int).
        financial_data: Dict with revenue, expenses, net_income, etc.

    Returns:
        Generated text string, or a template placeholder.
    """
    context = _build_context_string(financial_data)
    prompt = f"""Skriv förvaltningsberättelse för {company_name}, räkenskapsår {fiscal_year}.

Nyckeltal:
{context}"""

    if is_ollama_available():
        result = generate_text(prompt, system_prompt=VERKSAMHET_SYSTEM_PROMPT)
        if result:
            return result

    # Fallback template
    revenue = financial_data.get('revenue', 0)
    net_income = financial_data.get('net_income', 0)
    trend = 'positivt' if net_income > 0 else 'negativt'
    return (
        f'{company_name} har under räkenskapsåret {fiscal_year} '
        f'bedrivit verksamhet i enlighet med bolagsordningen. '
        f'Nettoomsättningen uppgick till {revenue:,.0f} SEK med ett '
        f'{trend} resultat om {net_income:,.0f} SEK.'
    )


def generate_vasentliga_handelser(company_name, fiscal_year, financial_data):
    """Generate suggested väsentliga händelser (significant events).

    Args:
        company_name: Company name.
        fiscal_year: Year (int).
        financial_data: Dict with financial metrics.

    Returns:
        Generated text string, or placeholder.
    """
    context = _build_context_string(financial_data)
    prompt = f"""Lista väsentliga händelser för {company_name}, räkenskapsår {fiscal_year}.

Nyckeltal:
{context}"""

    if is_ollama_available():
        result = generate_text(prompt, system_prompt=HANDELSER_SYSTEM_PROMPT)
        if result:
            return result

    return f'Inga väsentliga händelser att rapportera för räkenskapsåret {fiscal_year}.'
