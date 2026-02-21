"""Tax planning recommendations service.

Provides Swedish owner-employee tax optimization guidance:
- Lön vs utdelning (3:12-reglerna)
- Loss carryforward tracking
- Asset purchase timing
- Group structure suggestions
"""

from decimal import Decimal
from datetime import date

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, VerificationRow, Verification
from app.models.tax import TaxReturn
from app.models.salary import SalaryRun
from app.models.governance import DividendDecision

# Inkomstbasbelopp 2026 (updated annually)
IBB = Decimal('77600')
SALARY_THRESHOLD = IBB * 6  # 465 600 — needed for lönebaserat utrymme
CORPORATE_TAX_RATE = Decimal('0.206')
DIVIDEND_TAX_RATE = Decimal('0.20')  # 20% on qualified dividends within gränsbelopp
MARGINAL_TAX_RATE = Decimal('0.52')  # approximate top marginal income tax


def get_tax_planning_suggestions(company_id, fiscal_year_id):
    """Get all tax planning suggestions for a company.

    Returns dict with recommendation areas, each containing:
    - status: 'green' / 'yellow' / 'red'
    - title, summary, details
    """
    company = db.session.get(Company, company_id)
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not company or not fy:
        return {'recommendations': [], 'company_type': None}

    recommendations = []

    # Only provide lön/utdelning for AB
    if company.company_type == 'AB':
        rec = _salary_vs_dividend(company_id, fy)
        if rec:
            recommendations.append(rec)

    rec = _loss_carryforward(company_id, fy)
    if rec:
        recommendations.append(rec)

    rec = _asset_purchase_timing(company_id, fy)
    if rec:
        recommendations.append(rec)

    if company.company_type == 'AB':
        rec = _group_structure_suggestion(company_id, fy)
        if rec:
            recommendations.append(rec)

    return {
        'recommendations': recommendations,
        'company_type': company.company_type,
        'fiscal_year': fy,
        'ibb': float(IBB),
    }


def _salary_vs_dividend(company_id, fy):
    """Lön vs utdelning analysis (3:12-reglerna)."""
    # Get total gross salary paid this FY
    salary_runs = SalaryRun.query.filter_by(company_id=company_id).filter(
        SalaryRun.period_year == fy.year,
        SalaryRun.status.in_(['approved', 'paid']),
    ).all()
    total_salary = sum(float(sr.total_gross or 0) for sr in salary_runs)

    # Get dividends declared
    dividends = DividendDecision.query.filter_by(company_id=company_id).filter(
        db.extract('year', DividendDecision.decision_date) == fy.year,
    ).all()
    total_dividends = sum(float(d.total_amount or 0) for d in dividends)

    # Gränsbelopp (simplified): 2.75 × IBB for förenklingsregeln
    forenklingsregel = float(IBB) * 2.75
    salary_threshold = float(SALARY_THRESHOLD)

    # Determine status
    if total_salary >= salary_threshold:
        status = 'green'
        summary = (f'Löneutbetalning {total_salary:,.0f} kr uppfyller lönekravet '
                   f'({salary_threshold:,.0f} kr). Lönebaserat utdelningsutrymme aktiverat.')
    elif total_salary > 0:
        status = 'yellow'
        remaining = salary_threshold - total_salary
        summary = (f'Löneutbetalning {total_salary:,.0f} kr. Ytterligare {remaining:,.0f} kr '
                   f'behövs för att nå lönekravet ({salary_threshold:,.0f} kr).')
    else:
        status = 'red'
        summary = (f'Ingen lön utbetald. Förenklingsregeln ger gränsbelopp på '
                   f'{forenklingsregel:,.0f} kr.')

    return {
        'area': 'salary_vs_dividend',
        'title': 'Lön vs Utdelning (3:12)',
        'status': status,
        'summary': summary,
        'details': {
            'total_salary': total_salary,
            'total_dividends': total_dividends,
            'salary_threshold': salary_threshold,
            'forenklingsregel': forenklingsregel,
            'ibb': float(IBB),
        },
    }


def _loss_carryforward(company_id, fy):
    """Track loss carryforward (underskottsavdrag)."""
    # Get all tax returns for this company, ordered by year
    returns = TaxReturn.query.filter_by(company_id=company_id).order_by(
        TaxReturn.tax_year
    ).all()

    if not returns:
        return {
            'area': 'loss_carryforward',
            'title': 'Underskottsavdrag',
            'status': 'green',
            'summary': 'Ingen deklarationshistorik. Skapa deklarationer för att spåra underskott.',
            'details': {'deficit_history': [], 'available_deficit': 0},
        }

    # Walk through returns to calculate cumulative deficit
    deficit_history = []
    cumulative_deficit = Decimal('0')

    for tr in returns:
        taxable = tr.taxable_income or Decimal('0')
        prev_deficit = tr.previous_deficit or Decimal('0')

        if taxable < 0:
            # Loss year — deficit increases
            cumulative_deficit = abs(taxable)
        else:
            # Profit year — deficit used
            cumulative_deficit = max(Decimal('0'), cumulative_deficit - taxable)

        deficit_history.append({
            'year': tr.tax_year,
            'taxable_income': float(taxable),
            'deficit_used': float(prev_deficit),
            'remaining_deficit': float(cumulative_deficit),
        })

    available = float(cumulative_deficit)

    if available > 0:
        status = 'yellow'
        summary = f'Outnyttjat underskottsavdrag: {available:,.0f} kr. Kan kvittas mot framtida vinster.'
    else:
        status = 'green'
        summary = 'Inga outnyttjade underskottsavdrag.'

    return {
        'area': 'loss_carryforward',
        'title': 'Underskottsavdrag',
        'status': status,
        'summary': summary,
        'details': {
            'deficit_history': deficit_history,
            'available_deficit': available,
        },
    }


def _asset_purchase_timing(company_id, fy):
    """Asset purchase timing — months remaining in FY vs depreciation benefit."""
    if not fy.end_date:
        return None

    today = date.today()
    if today > fy.end_date:
        months_remaining = 0
    else:
        months_remaining = max(0,
            (fy.end_date.year - today.year) * 12 + (fy.end_date.month - today.month)
        )

    total_months = max(1,
        (fy.end_date.year - fy.start_date.year) * 12 +
        (fy.end_date.month - fy.start_date.month) + 1
    )
    depreciation_pct = round((months_remaining / total_months) * 100, 1)

    if months_remaining >= 6:
        status = 'green'
        summary = (f'{months_remaining} månader kvar av räkenskapsåret. '
                   f'Investering nu ger ca {depreciation_pct}% avskrivning detta år.')
    elif months_remaining >= 1:
        status = 'yellow'
        summary = (f'Bara {months_remaining} månader kvar. '
                   f'Investering ger begränsad avskrivning ({depreciation_pct}%) i år — '
                   f'överväg att vänta till nästa räkenskapsår.')
    else:
        status = 'red'
        summary = 'Räkenskapsåret är avslutat. Investeringar bokförs på nästa period.'

    return {
        'area': 'asset_timing',
        'title': 'Investeringstidpunkt',
        'status': status,
        'summary': summary,
        'details': {
            'months_remaining': months_remaining,
            'total_months': total_months,
            'depreciation_pct': depreciation_pct,
            'fy_end': str(fy.end_date),
        },
    }


def _group_structure_suggestion(company_id, fy):
    """Suggest holding company if standalone AB with high income."""
    # Check if already in a consolidation group
    from app.models.consolidation import ConsolidationGroup, ConsolidationGroupMember
    is_in_group = ConsolidationGroupMember.query.filter_by(company_id=company_id).first()

    if is_in_group:
        return {
            'area': 'group_structure',
            'title': 'Koncernstruktur',
            'status': 'green',
            'summary': 'Bolaget ingår redan i en koncern. Koncernbidrag möjligt.',
            'details': {'in_group': True},
        }

    # Check if there are dividends and high income
    dividends = DividendDecision.query.filter_by(company_id=company_id).filter(
        db.extract('year', DividendDecision.decision_date) == fy.year,
    ).all()
    total_dividends = sum(float(d.total_amount or 0) for d in dividends)

    # Get net income from latest tax return
    tr = TaxReturn.query.filter_by(
        company_id=company_id, fiscal_year_id=fy.id,
    ).first()
    net_income = float(tr.net_income or 0) if tr else 0

    if total_dividends > 200000 or net_income > 500000:
        status = 'yellow'
        summary = ('Hög utdelning/vinst i enskilt bolag. Överväg holdingbolag '
                   'för skatteeffektiv utdelning (5:25-reglerna) och koncernbidrag.')
    else:
        status = 'green'
        summary = 'Nuvarande struktur bedöms lämplig för verksamhetens omfattning.'

    return {
        'area': 'group_structure',
        'title': 'Koncernstruktur',
        'status': status,
        'summary': summary,
        'details': {
            'in_group': False,
            'total_dividends': total_dividends,
            'net_income': net_income,
        },
    }


def get_group_tax_overview():
    """Get tax planning overview across all companies."""
    companies = Company.query.order_by(Company.name).all()
    overview = []

    for company in companies:
        fy = FiscalYear.query.filter_by(
            company_id=company.id, status='open'
        ).order_by(FiscalYear.year.desc()).first()

        if not fy:
            overview.append({
                'company': company,
                'fiscal_year': None,
                'status': 'grey',
                'summary': 'Inget öppet räkenskapsår',
            })
            continue

        data = get_tax_planning_suggestions(company.id, fy.id)
        statuses = [r['status'] for r in data['recommendations']]

        if 'red' in statuses:
            overall = 'red'
        elif 'yellow' in statuses:
            overall = 'yellow'
        else:
            overall = 'green'

        overview.append({
            'company': company,
            'fiscal_year': fy,
            'status': overall,
            'recommendation_count': len(data['recommendations']),
            'recommendations': data['recommendations'],
        })

    return overview
