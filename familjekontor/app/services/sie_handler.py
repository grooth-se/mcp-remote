"""SIE4 Import/Export handler for Swedish accounting data.

SIE (Standard Import Export) is the standard format for exchanging
accounting data between Swedish accounting software.

Handles CP437/ISO-8859-1 encoding used by older Swedish systems.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from app.extensions import db
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.company import Company


class SIEParser:
    """Parse SIE4 files."""

    def __init__(self):
        self.data = {
            'program': '',
            'format': '',
            'gen': '',
            'sietyp': '4',
            'fnamn': '',
            'orgnr': '',
            'adress': '',
            'ftyp': '',
            'valuta': 'SEK',
            'rar': {},       # Fiscal years: {0: (start, end), -1: (start, end)}
            'konto': {},     # Accounts: {number: name}
            'sru': {},       # SRU codes: {account: sru_code}
            'ib': {},        # Opening balances: {(year_idx, account): amount}
            'ub': {},        # Closing balances: {(year_idx, account): amount}
            'res': {},       # Result: {(year_idx, account): amount}
            'ver': [],       # Verifications: list of dicts
        }

    def parse(self, content):
        """Parse SIE file content (string)."""
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('//'):
                i += 1
                continue

            if line.startswith('#'):
                i = self._parse_line(line, lines, i)
            else:
                i += 1

        return self.data

    def _parse_line(self, line, lines, idx):
        """Parse a single SIE line. Returns next line index."""
        parts = self._tokenize(line)
        if not parts:
            return idx + 1

        tag = parts[0].upper()

        if tag == '#PROGRAM':
            self.data['program'] = parts[1] if len(parts) > 1 else ''
        elif tag == '#FORMAT':
            self.data['format'] = parts[1] if len(parts) > 1 else ''
        elif tag == '#GEN':
            self.data['gen'] = parts[1] if len(parts) > 1 else ''
        elif tag == '#SIETYP':
            self.data['sietyp'] = parts[1] if len(parts) > 1 else '4'
        elif tag == '#FNAMN':
            self.data['fnamn'] = parts[1] if len(parts) > 1 else ''
        elif tag == '#ORGNR':
            self.data['orgnr'] = parts[1] if len(parts) > 1 else ''
        elif tag == '#ADRESS':
            self.data['adress'] = ' '.join(parts[1:])
        elif tag == '#FTYP':
            self.data['ftyp'] = parts[1] if len(parts) > 1 else ''
        elif tag == '#VALUTA':
            self.data['valuta'] = parts[1] if len(parts) > 1 else 'SEK'
        elif tag == '#RAR':
            self._parse_rar(parts)
        elif tag == '#KONTO':
            self._parse_konto(parts)
        elif tag == '#SRU':
            self._parse_sru(parts)
        elif tag == '#IB':
            self._parse_balance(parts, 'ib')
        elif tag == '#UB':
            self._parse_balance(parts, 'ub')
        elif tag == '#RES':
            self._parse_balance(parts, 'res')
        elif tag == '#VER':
            return self._parse_verification(parts, lines, idx)

        return idx + 1

    def _tokenize(self, line):
        """Tokenize a SIE line, handling quoted strings and tab/space separators."""
        tokens = []
        current = ''
        in_quotes = False
        in_braces = False

        for char in line:
            if char == '"' and not in_braces:
                in_quotes = not in_quotes
            elif char == '{':
                in_braces = True
                current += char
            elif char == '}':
                in_braces = False
                current += char
            elif char in (' ', '\t') and not in_quotes and not in_braces:
                if current:
                    tokens.append(current)
                    current = ''
                continue
            else:
                current += char

        if current:
            tokens.append(current)

        return tokens

    def _parse_rar(self, parts):
        """Parse fiscal year: #RAR year_idx start end"""
        if len(parts) >= 4:
            year_idx = int(parts[1])
            start = self._parse_date(parts[2])
            end = self._parse_date(parts[3])
            if start and end:
                self.data['rar'][year_idx] = (start, end)

    def _parse_konto(self, parts):
        """Parse account: #KONTO number name"""
        if len(parts) >= 3:
            self.data['konto'][parts[1]] = parts[2]

    def _parse_sru(self, parts):
        """Parse SRU code: #SRU account sru_code"""
        if len(parts) >= 3:
            self.data['sru'][parts[1]] = parts[2]

    def _parse_balance(self, parts, balance_type):
        """Parse balance line: #IB/#UB/#RES year_idx account amount"""
        if len(parts) >= 4:
            year_idx = int(parts[1])
            account = parts[2]
            amount = self._parse_amount(parts[3])
            self.data[balance_type][(year_idx, account)] = amount

    def _parse_verification(self, parts, lines, idx):
        """Parse verification block with transaction rows."""
        # #VER series number date description
        ver = {
            'series': parts[1] if len(parts) > 1 else 'A',
            'number': parts[2] if len(parts) > 2 else '',
            'date': self._parse_date(parts[3]) if len(parts) > 3 else None,
            'description': parts[4] if len(parts) > 4 else '',
            'rows': [],
        }

        idx += 1
        # Look for opening brace
        while idx < len(lines):
            line = lines[idx].strip()
            if line == '{':
                idx += 1
                break
            elif line.startswith('{'):
                idx += 1
                break
            idx += 1

        # Parse transaction rows until closing brace
        while idx < len(lines):
            line = lines[idx].strip()
            if line == '}' or line.startswith('}'):
                break

            if line.startswith('#TRANS'):
                row = self._parse_trans(line)
                if row:
                    ver['rows'].append(row)

            idx += 1

        self.data['ver'].append(ver)
        return idx + 1

    def _parse_trans(self, line):
        """Parse transaction row: #TRANS account {} amount [date] [description]"""
        parts = self._tokenize(line)
        if len(parts) < 3:
            return None

        # Skip the {} object list (dimensions)
        account = parts[1]
        # Find amount - skip {} blocks
        amount_idx = 2
        for i, p in enumerate(parts[2:], 2):
            if p not in ('{}', '{', '}') and not p.startswith('{'):
                amount_idx = i
                break

        amount = self._parse_amount(parts[amount_idx]) if amount_idx < len(parts) else Decimal('0')
        trans_date = None
        description = ''

        if amount_idx + 1 < len(parts):
            trans_date = self._parse_date(parts[amount_idx + 1])
        if amount_idx + 2 < len(parts):
            description = parts[amount_idx + 2]

        return {
            'account': account,
            'amount': amount,
            'date': trans_date,
            'description': description,
        }

    def _parse_date(self, date_str):
        """Parse SIE date format YYYYMMDD."""
        if not date_str or len(date_str) != 8:
            return None
        try:
            return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except (ValueError, IndexError):
            return None

    def _parse_amount(self, amount_str):
        """Parse SIE amount (may use . or , as decimal separator)."""
        try:
            cleaned = amount_str.replace(',', '.').strip()
            return Decimal(cleaned)
        except Exception:
            return Decimal('0')


def read_sie_file(file_path=None, file_content=None):
    """Read and parse a SIE file.

    Args:
        file_path: Path to SIE file
        file_content: Raw bytes content of the file

    Returns:
        Parsed SIE data dict
    """
    if file_content is None and file_path:
        with open(file_path, 'rb') as f:
            file_content = f.read()

    if file_content is None:
        raise ValueError('No file content provided')

    # Try different encodings common in Swedish SIE files
    text = None
    for encoding in ('cp437', 'iso-8859-1', 'utf-8', 'latin-1'):
        try:
            text = file_content.decode(encoding)
            # Basic validation - should have #FLAGGA or #PROGRAM
            if '#' in text:
                break
        except (UnicodeDecodeError, AttributeError):
            continue

    if text is None:
        raise ValueError('Could not decode SIE file with any supported encoding')

    parser = SIEParser()
    return parser.parse(text)


def import_sie(company_id, sie_data, fiscal_year_id=None):
    """Import parsed SIE data into the database for a company.

    Args:
        company_id: Target company ID
        sie_data: Parsed SIE data dict from SIEParser
        fiscal_year_id: Specific fiscal year to import into (auto-detect if None)

    Returns:
        Dict with import statistics
    """
    stats = {
        'accounts_created': 0,
        'accounts_existing': 0,
        'verifications_created': 0,
        'rows_created': 0,
        'errors': [],
    }

    # Import accounts
    for acc_number, acc_name in sie_data.get('konto', {}).items():
        existing = Account.query.filter_by(
            company_id=company_id, account_number=acc_number
        ).first()

        if existing:
            stats['accounts_existing'] += 1
            continue

        # Determine account type from number
        account_type = _account_type_from_number(acc_number)
        account = Account(
            company_id=company_id,
            account_number=acc_number,
            name=acc_name,
            account_type=account_type,
            active=True,
        )
        db.session.add(account)
        stats['accounts_created'] += 1

    db.session.flush()

    # Determine fiscal year
    if not fiscal_year_id:
        rar = sie_data.get('rar', {})
        if 0 in rar:
            start, end = rar[0]
            fy = FiscalYear.query.filter_by(
                company_id=company_id, start_date=start, end_date=end
            ).first()
            if not fy:
                fy = FiscalYear(
                    company_id=company_id,
                    year=start.year,
                    start_date=start,
                    end_date=end,
                    status='open',
                )
                db.session.add(fy)
                db.session.flush()
            fiscal_year_id = fy.id
        else:
            # Use most recent open fiscal year
            fy = FiscalYear.query.filter_by(
                company_id=company_id, status='open'
            ).order_by(FiscalYear.year.desc()).first()
            if fy:
                fiscal_year_id = fy.id
            else:
                stats['errors'].append('Inget räkenskapsår hittat')
                return stats

    # Build account lookup
    account_lookup = {}
    for acc in Account.query.filter_by(company_id=company_id).all():
        account_lookup[acc.account_number] = acc.id

    # Import verifications
    for ver_data in sie_data.get('ver', []):
        if not ver_data.get('rows'):
            continue

        ver_date = ver_data.get('date') or date.today()

        from app.services.accounting_service import get_next_verification_number
        ver_number = get_next_verification_number(company_id, fiscal_year_id)

        verification = Verification(
            company_id=company_id,
            fiscal_year_id=fiscal_year_id,
            verification_number=ver_number,
            verification_date=ver_date,
            description=ver_data.get('description', ''),
            verification_type='manual',
            source='sie_import',
        )
        db.session.add(verification)
        db.session.flush()

        for row_data in ver_data['rows']:
            acc_number = row_data['account']
            if acc_number not in account_lookup:
                stats['errors'].append(f'Konto {acc_number} saknas')
                continue

            amount = row_data['amount']
            debit = max(amount, Decimal('0'))
            credit = abs(min(amount, Decimal('0')))

            row = VerificationRow(
                verification_id=verification.id,
                account_id=account_lookup[acc_number],
                debit=debit,
                credit=credit,
                description=row_data.get('description', ''),
            )
            db.session.add(row)
            stats['rows_created'] += 1

        stats['verifications_created'] += 1

    db.session.commit()
    return stats


def export_sie(company_id, fiscal_year_id):
    """Export company data as SIE4 format string.

    Args:
        company_id: Company to export
        fiscal_year_id: Fiscal year to export

    Returns:
        SIE4 file content as string
    """
    company = db.session.get(Company, company_id)
    fiscal_year = db.session.get(FiscalYear, fiscal_year_id)

    if not company or not fiscal_year:
        raise ValueError('Företag eller räkenskapsår hittades inte')

    lines = []
    now = datetime.now()

    # Header
    lines.append(f'#FLAGGA 0')
    lines.append(f'#PROGRAM "Familjekontor" "1.0"')
    lines.append(f'#FORMAT PC8')
    lines.append(f'#GEN {now.strftime("%Y%m%d")}')
    lines.append(f'#SIETYP 4')
    lines.append(f'#FNAMN "{company.name}"')
    lines.append(f'#ORGNR {company.org_number}')
    lines.append(f'#VALUTA {company.base_currency}')

    # Fiscal year
    start_str = fiscal_year.start_date.strftime('%Y%m%d')
    end_str = fiscal_year.end_date.strftime('%Y%m%d')
    lines.append(f'#RAR 0 {start_str} {end_str}')

    # Accounts
    accounts = Account.query.filter_by(company_id=company_id, active=True).order_by(
        Account.account_number
    ).all()
    for acc in accounts:
        lines.append(f'#KONTO {acc.account_number} "{acc.name}"')

    # Opening and closing balances (IB/UB for balance sheet accounts)
    from app.services.accounting_service import get_account_balance
    for acc in accounts:
        if acc.account_number[0] in ('1', '2'):
            balance = get_account_balance(company_id, fiscal_year_id, acc.account_number)
            if balance != 0:
                lines.append(f'#UB 0 {acc.account_number} {balance}')

    # Result accounts
    for acc in accounts:
        if acc.account_number[0] in ('3', '4', '5', '6', '7', '8'):
            balance = get_account_balance(company_id, fiscal_year_id, acc.account_number)
            if balance != 0:
                lines.append(f'#RES 0 {acc.account_number} {balance}')

    # Verifications
    verifications = Verification.query.filter_by(
        company_id=company_id, fiscal_year_id=fiscal_year_id
    ).order_by(Verification.verification_number).all()

    for ver in verifications:
        ver_date = ver.verification_date.strftime('%Y%m%d')
        desc = ver.description or ''
        lines.append(f'#VER A {ver.verification_number} {ver_date} "{desc}"')
        lines.append('{')

        for row in ver.rows:
            amount = float(row.debit) - float(row.credit)
            row_desc = row.description or ''
            lines.append(f'  #TRANS {row.account.account_number} {{}} {amount:.2f} "" "{row_desc}"')

        lines.append('}')

    return '\n'.join(lines)


def _account_type_from_number(account_number):
    """Determine account type from BAS account number."""
    if not account_number:
        return 'expense'
    first = account_number[0]
    if first == '1':
        return 'asset'
    elif first == '2':
        # 20xx = equity, rest = liability
        if account_number[:2] in ('20', '21'):
            return 'equity'
        return 'liability'
    elif first == '3':
        return 'revenue'
    elif first in ('4', '5', '6', '7'):
        return 'expense'
    elif first == '8':
        # 8xxx can be revenue or expense
        if account_number[:2] in ('80', '81', '82', '83', '88', '89'):
            if account_number.startswith('823') or account_number.startswith('825') or \
               account_number.startswith('828') or account_number.startswith('83') or \
               account_number.startswith('84') or account_number.startswith('88') or \
               account_number.startswith('89'):
                return 'expense'
            return 'revenue'
        return 'expense'
    return 'expense'
