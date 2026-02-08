"""Multi-company consolidation service: consolidated P&L, balance sheet, eliminations."""

from decimal import Decimal
from collections import OrderedDict
from io import BytesIO

from app.extensions import db
from app.models.consolidation import (
    ConsolidationGroup, ConsolidationGroupMember, IntercompanyElimination
)
from app.models.accounting import FiscalYear
from app.models.company import Company
from app.services.report_service import get_profit_and_loss, get_balance_sheet


def create_consolidation_group(name, parent_company_id, description=None):
    group = ConsolidationGroup(
        name=name,
        parent_company_id=parent_company_id,
        description=description,
    )
    db.session.add(group)
    db.session.commit()
    return group


def add_member(group_id, company_id, ownership_pct=100):
    existing = ConsolidationGroupMember.query.filter_by(
        group_id=group_id, company_id=company_id
    ).first()
    if existing:
        existing.ownership_pct = ownership_pct
        db.session.commit()
        return existing

    member = ConsolidationGroupMember(
        group_id=group_id,
        company_id=company_id,
        ownership_pct=ownership_pct,
    )
    db.session.add(member)
    db.session.commit()
    return member


def remove_member(group_id, company_id):
    member = ConsolidationGroupMember.query.filter_by(
        group_id=group_id, company_id=company_id
    ).first()
    if member:
        db.session.delete(member)
        db.session.commit()
        return True
    return False


def _get_fy_for_company(company_id, year):
    """Get fiscal year for a company matching a specific year."""
    return FiscalYear.query.filter_by(
        company_id=company_id, year=year
    ).first()


def get_consolidated_pnl(group_id, fy_year):
    """Generate consolidated P&L across all group members."""
    group = db.session.get(ConsolidationGroup, group_id)
    if not group:
        return None

    # Collect P&L data per member
    member_data = []
    consolidated_sections = OrderedDict()

    for member in group.members:
        fy = _get_fy_for_company(member.company_id, fy_year)
        if not fy:
            continue

        pnl = get_profit_and_loss(member.company_id, fy.id)
        weight = float(member.ownership_pct or 100) / 100.0

        member_data.append({
            'company': member.company,
            'ownership_pct': float(member.ownership_pct or 100),
            'pnl': pnl,
            'weight': weight,
        })

        # Consolidate sections
        for section_name, section in pnl['sections'].items():
            if section_name not in consolidated_sections:
                consolidated_sections[section_name] = {'total': 0, 'accounts': []}

            weighted_total = float(section['total']) * weight
            consolidated_sections[section_name]['total'] += weighted_total

    # Calculate consolidated totals
    gross_profit = consolidated_sections.get('Nettoomsättning', {}).get('total', 0) - \
                   consolidated_sections.get('Kostnad sålda varor', {}).get('total', 0)

    operating_result = gross_profit - (
        consolidated_sections.get('Övriga externa kostnader', {}).get('total', 0) +
        consolidated_sections.get('Personalkostnader', {}).get('total', 0)
    )

    result_before_tax = operating_result + (
        consolidated_sections.get('Finansiella intäkter', {}).get('total', 0) -
        consolidated_sections.get('Finansiella kostnader', {}).get('total', 0)
    )

    # Apply eliminations
    eliminations = IntercompanyElimination.query.filter_by(group_id=group_id).all()
    elimination_total = sum(float(e.amount) for e in eliminations)

    return {
        'group': group,
        'members': member_data,
        'sections': consolidated_sections,
        'gross_profit': gross_profit,
        'operating_result': operating_result,
        'result_before_tax': result_before_tax,
        'elimination_total': elimination_total,
        'adjusted_result': result_before_tax - elimination_total,
        'report_type': 'pnl',
    }


def get_consolidated_balance_sheet(group_id, fy_year):
    """Generate consolidated balance sheet across all group members."""
    group = db.session.get(ConsolidationGroup, group_id)
    if not group:
        return None

    member_data = []
    consolidated_sections = OrderedDict()

    for member in group.members:
        fy = _get_fy_for_company(member.company_id, fy_year)
        if not fy:
            continue

        bs = get_balance_sheet(member.company_id, fy.id)
        weight = float(member.ownership_pct or 100) / 100.0

        member_data.append({
            'company': member.company,
            'ownership_pct': float(member.ownership_pct or 100),
            'balance_sheet': bs,
            'weight': weight,
        })

        for section_name, section in bs['sections'].items():
            if section_name not in consolidated_sections:
                consolidated_sections[section_name] = {'total': 0}

            weighted_total = float(section['total']) * weight
            consolidated_sections[section_name]['total'] += weighted_total

    total_assets = (
        consolidated_sections.get('Anläggningstillgångar', {}).get('total', 0) +
        consolidated_sections.get('Omsättningstillgångar', {}).get('total', 0)
    )

    total_equity_liabilities = (
        consolidated_sections.get('Eget kapital', {}).get('total', 0) +
        consolidated_sections.get('Långfristiga skulder', {}).get('total', 0) +
        consolidated_sections.get('Kortfristiga skulder', {}).get('total', 0)
    )

    return {
        'group': group,
        'members': member_data,
        'sections': consolidated_sections,
        'total_assets': total_assets,
        'total_equity_liabilities': total_equity_liabilities,
        'report_type': 'balance',
    }


def create_elimination(group_id, fiscal_year_id, from_company_id, to_company_id,
                       account_number, amount, description=None):
    elimination = IntercompanyElimination(
        group_id=group_id,
        fiscal_year_id=fiscal_year_id,
        from_company_id=from_company_id,
        to_company_id=to_company_id,
        account_number=account_number,
        amount=amount,
        description=description,
    )
    db.session.add(elimination)
    db.session.commit()
    return elimination


def export_consolidated_report(group_id, fy_year, report_type):
    """Export consolidated report to Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    if report_type == 'pnl':
        data = get_consolidated_pnl(group_id, fy_year)
    else:
        data = get_consolidated_balance_sheet(group_id, fy_year)

    if not data:
        return None

    wb = Workbook()
    ws = wb.active
    bold = Font(bold=True)

    ws.append([f'Koncernrapport: {data["group"].name}'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([f'Räkenskapsår {fy_year}'])
    ws.append([])

    if report_type == 'pnl':
        ws.title = 'Koncern-RR'
        ws.append(['Avsnitt', 'Koncerntotal'])
        for cell in ws[ws.max_row]:
            cell.font = bold

        for section_name, section in data['sections'].items():
            ws.append([section_name, round(section['total'], 2)])

        ws.append([])
        ws.append(['Rörelseresultat', round(data['operating_result'], 2)])
        ws.append(['Resultat före skatt', round(data['result_before_tax'], 2)])
        ws.append(['Elimineringar', round(data['elimination_total'], 2)])
        ws.append(['Justerat resultat', round(data['adjusted_result'], 2)])
        ws[ws.max_row][0].font = bold

        ws.append([])
        ws.append(['Medlemsföretag'])
        ws[ws.max_row][0].font = bold
        for m in data['members']:
            ws.append([m['company'].name, f'{m["ownership_pct"]}%'])
    else:
        ws.title = 'Koncern-BR'
        ws.append(['Avsnitt', 'Koncerntotal'])
        for cell in ws[ws.max_row]:
            cell.font = bold

        for section_name, section in data['sections'].items():
            ws.append([section_name, round(section['total'], 2)])

        ws.append([])
        ws.append(['Summa tillgångar', round(data['total_assets'], 2)])
        ws.append(['Summa EK + skulder', round(data['total_equity_liabilities'], 2)])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
