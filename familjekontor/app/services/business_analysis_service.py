"""Business analysis report service.

Combines ratios, cash flow, AR/AP, and comparison data into a narrative report.
Uses Ollama for AI-generated Swedish text when available, template-based fallback otherwise.
"""

from io import BytesIO

from app.extensions import db
from app.models.accounting import FiscalYear
from app.models.company import Company


def generate_business_analysis(company_id, fiscal_year_id):
    """Generate a comprehensive business analysis report.

    Returns dict with sections, each containing data + narrative text.
    has_ai flag indicates whether AI-generated or template-based.
    """
    company = db.session.get(Company, company_id)
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not company or not fy:
        return None

    from app.utils.ai_client import is_ollama_available

    has_ai = is_ollama_available()

    sections = []

    # 1. Profitability analysis
    profitability = _get_profitability_section(company_id, fiscal_year_id, has_ai)
    if profitability:
        sections.append(profitability)

    # 2. Liquidity and cash flow
    liquidity = _get_liquidity_section(company_id, fiscal_year_id, has_ai)
    if liquidity:
        sections.append(liquidity)

    # 3. Customer and supplier analysis
    arap = _get_arap_section(company_id, fiscal_year_id, has_ai)
    if arap:
        sections.append(arap)

    # 4. Comparison and trends
    comparison = _get_comparison_section(company_id, fiscal_year_id, has_ai)
    if comparison:
        sections.append(comparison)

    return {
        'company': company,
        'fiscal_year': fy,
        'sections': sections,
        'has_ai': has_ai,
    }


def _ratio_val(ratio_dict):
    """Extract numeric value from ratio dict or return 0."""
    if isinstance(ratio_dict, dict):
        v = ratio_dict.get('value')
        return float(v) if v is not None else 0.0
    if ratio_dict is not None:
        return float(ratio_dict)
    return 0.0


def _get_profitability_section(company_id, fiscal_year_id, has_ai):
    """Profitability ratios + narrative."""
    try:
        from app.services.ratio_service import get_financial_ratios
        ratios = get_financial_ratios(company_id, fiscal_year_id)
    except Exception:
        ratios = None

    if not ratios:
        return None

    profitability = ratios.get('profitability', {})
    gross_margin = _ratio_val(profitability.get('gross_margin'))
    net_margin = _ratio_val(profitability.get('net_margin'))
    roe = _ratio_val(profitability.get('roe'))

    data_points = {
        'gross_margin': gross_margin,
        'net_margin': net_margin,
        'roe': roe,
    }

    if has_ai:
        narrative = _ai_narrative(
            f"Analysera lönsamheten för ett svenskt företag. "
            f"Bruttomarginal: {gross_margin:.1f}%, nettomarginal: {net_margin:.1f}%, "
            f"räntabilitet på eget kapital: {roe:.1f}%. "
            f"Skriv 2-3 meningar på svenska med bedömning och rekommendationer."
        )
    else:
        narrative = _template_profitability(gross_margin, net_margin, roe)

    return {
        'key': 'profitability',
        'title': 'Lönsamhetsanalys',
        'icon': 'bi-graph-up',
        'data_points': data_points,
        'narrative': narrative,
    }


def _get_liquidity_section(company_id, fiscal_year_id, has_ai):
    """Liquidity ratios + cash flow summary."""
    try:
        from app.services.ratio_service import get_financial_ratios
        ratios = get_financial_ratios(company_id, fiscal_year_id)
    except Exception:
        ratios = None

    cf_total = None
    try:
        from app.services.cashflow_service import get_cash_flow_statement
        cf = get_cash_flow_statement(company_id, fiscal_year_id)
        cf_total = cf.get('total_cash_flow', 0) if cf else 0
    except Exception:
        pass

    liquidity = ratios.get('liquidity', {}) if ratios else {}
    current_ratio = _ratio_val(liquidity.get('current_ratio'))
    quick_ratio = _ratio_val(liquidity.get('quick_ratio'))

    data_points = {
        'current_ratio': current_ratio,
        'quick_ratio': quick_ratio,
        'total_cash_flow': cf_total,
    }

    if has_ai:
        narrative = _ai_narrative(
            f"Analysera likviditeten för ett svenskt företag. "
            f"Balanslikviditet: {current_ratio:.2f}, kassalikviditet: {quick_ratio:.2f}, "
            f"totalt kassaflöde: {cf_total:,.0f} kr. "
            f"Skriv 2-3 meningar på svenska."
        )
    else:
        narrative = _template_liquidity(current_ratio, quick_ratio, cf_total)

    return {
        'key': 'liquidity',
        'title': 'Likviditet och kassaflöde',
        'icon': 'bi-droplet',
        'data_points': data_points,
        'narrative': narrative,
    }


def _get_arap_section(company_id, fiscal_year_id, has_ai):
    """AR/AP aging + DSO/DPO analysis."""
    dso = None
    dpo = None

    try:
        from app.services.arap_service import get_dso, get_dpo
        dso = get_dso(company_id, fiscal_year_id)
        dpo = get_dpo(company_id, fiscal_year_id)
    except Exception:
        pass

    data_points = {
        'dso': dso,
        'dpo': dpo,
    }

    if has_ai:
        dso_str = f"{dso:.0f} dagar" if dso else "ej tillgängligt"
        dpo_str = f"{dpo:.0f} dagar" if dpo else "ej tillgängligt"
        narrative = _ai_narrative(
            f"Analysera kund- och leverantörsrelationer. "
            f"DSO (genomsnittlig kundkredittid): {dso_str}, "
            f"DPO (genomsnittlig leverantörskredittid): {dpo_str}. "
            f"Skriv 2-3 meningar på svenska."
        )
    else:
        narrative = _template_arap(dso, dpo)

    return {
        'key': 'arap',
        'title': 'Kund- och leverantörsanalys',
        'icon': 'bi-people',
        'data_points': data_points,
        'narrative': narrative,
    }


def _get_comparison_section(company_id, fiscal_year_id, has_ai):
    """Year-over-year comparison (if prior year exists)."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    prior_fy = (FiscalYear.query
                .filter_by(company_id=company_id)
                .filter(FiscalYear.year < fy.year)
                .order_by(FiscalYear.year.desc())
                .first())

    if not prior_fy:
        return {
            'key': 'comparison',
            'title': 'Jämförelse och trender',
            'icon': 'bi-arrow-left-right',
            'data_points': {},
            'narrative': 'Ingen föregående period att jämföra med.',
        }

    try:
        from app.services.comparison_service import compare_periods
        comparison = compare_periods(company_id, fiscal_year_id, prior_fy.id, 'pnl')
    except Exception:
        comparison = None

    if not comparison:
        return None

    data_points = {
        'current_year': fy.year,
        'prior_year': prior_fy.year,
    }

    if has_ai:
        narrative = _ai_narrative(
            f"Jämför räkenskapsår {fy.year} med {prior_fy.year}. "
            f"Skriv 2-3 meningar på svenska om utvecklingen."
        )
    else:
        narrative = (f'Jämförelse mellan räkenskapsår {fy.year} och {prior_fy.year}. '
                     f'Se detaljer i periodjämförelserapporten.')

    return {
        'key': 'comparison',
        'title': 'Jämförelse och trender',
        'icon': 'bi-arrow-left-right',
        'data_points': data_points,
        'narrative': narrative,
    }


# ---- AI narrative ----

def _ai_narrative(prompt):
    """Generate narrative text using Ollama. Returns template fallback on failure."""
    try:
        from app.utils.ai_client import generate_text
        result = generate_text(prompt)
        if result:
            return result
    except Exception:
        pass
    return None


# ---- Template fallbacks ----

def _template_profitability(gross_margin, net_margin, roe):
    parts = []
    if gross_margin > 30:
        parts.append(f'Bruttomarginalen på {gross_margin:.1f}% visar god lönsamhet i kärnverksamheten.')
    elif gross_margin > 10:
        parts.append(f'Bruttomarginalen på {gross_margin:.1f}% är acceptabel men kan förbättras.')
    else:
        parts.append(f'Bruttomarginalen på {gross_margin:.1f}% är låg och bör ses över.')

    if net_margin > 10:
        parts.append(f'Nettomarginalen ({net_margin:.1f}%) indikerar effektiv kostnadskontroll.')
    elif net_margin > 0:
        parts.append(f'Nettomarginalen ({net_margin:.1f}%) är positiv men har förbättringspotential.')
    else:
        parts.append(f'Negativ nettomarginal ({net_margin:.1f}%) kräver åtgärder.')

    if roe > 15:
        parts.append(f'Räntabiliteten på eget kapital ({roe:.1f}%) är stark.')
    return ' '.join(parts)


def _template_liquidity(current_ratio, quick_ratio, cf_total):
    parts = []
    if current_ratio >= 2:
        parts.append(f'Balanslikviditeten ({current_ratio:.2f}) är god och överstiger normgränsen 2.0.')
    elif current_ratio >= 1:
        parts.append(f'Balanslikviditeten ({current_ratio:.2f}) är acceptabel.')
    else:
        parts.append(f'Balanslikviditeten ({current_ratio:.2f}) är under 1.0 och signalerar likviditetsrisk.')

    if quick_ratio >= 1:
        parts.append(f'Kassalikviditeten ({quick_ratio:.2f}) är tillfredsställande.')
    else:
        parts.append(f'Kassalikviditeten ({quick_ratio:.2f}) understiger normvärdet 1.0.')

    if cf_total is not None:
        if cf_total > 0:
            parts.append(f'Positivt kassaflöde ({cf_total:,.0f} kr) stärker likviditeten.')
        else:
            parts.append(f'Negativt kassaflöde ({cf_total:,.0f} kr) bör bevakas.')

    return ' '.join(parts)


def _template_arap(dso, dpo):
    parts = []
    if dso is not None:
        if dso <= 30:
            parts.append(f'Genomsnittlig kundkredittid (DSO) är {dso:.0f} dagar, vilket är effektivt.')
        elif dso <= 60:
            parts.append(f'Genomsnittlig kundkredittid (DSO) är {dso:.0f} dagar.')
        else:
            parts.append(f'DSO på {dso:.0f} dagar är högt — överväg kreditpolicyn.')
    else:
        parts.append('DSO-data ej tillgängligt.')

    if dpo is not None:
        parts.append(f'Leverantörskredittid (DPO) är {dpo:.0f} dagar.')
    else:
        parts.append('DPO-data ej tillgängligt.')

    return ' '.join(parts)


def get_business_analysis_pdf(company_id, fiscal_year_id):
    """Generate PDF of business analysis. Returns BytesIO or None."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        return None

    from flask import render_template

    analysis = generate_business_analysis(company_id, fiscal_year_id)
    if not analysis:
        return None

    html_str = render_template('report_center/business_analysis_pdf.html',
                               analysis=analysis)
    output = BytesIO()
    HTML(string=html_str).write_pdf(output)
    output.seek(0)
    return output
