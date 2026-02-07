#!/usr/bin/env python3
"""CLI script for batch importing SIE files."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import app
from app.extensions import db
from app.services.sie_handler import read_sie_file, import_sie


def main():
    if len(sys.argv) < 3:
        print('Usage: python import_sie.py <company_id> <sie_file_path> [fiscal_year_id]')
        sys.exit(1)

    company_id = int(sys.argv[1])
    file_path = sys.argv[2]
    fiscal_year_id = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if not os.path.exists(file_path):
        print(f'File not found: {file_path}')
        sys.exit(1)

    with app.app_context():
        print(f'Parsing SIE file: {file_path}')
        sie_data = read_sie_file(file_path=file_path)

        print(f'Company: {sie_data.get("fnamn", "Unknown")}')
        print(f'Org.nr: {sie_data.get("orgnr", "Unknown")}')
        print(f'Accounts: {len(sie_data.get("konto", {}))}')
        print(f'Verifications: {len(sie_data.get("ver", []))}')
        print()

        stats = import_sie(company_id, sie_data, fiscal_year_id)

        print('Import results:')
        print(f'  Accounts created: {stats["accounts_created"]}')
        print(f'  Accounts existing: {stats["accounts_existing"]}')
        print(f'  Verifications: {stats["verifications_created"]}')
        print(f'  Rows: {stats["rows_created"]}')
        if stats['errors']:
            print(f'  Errors: {len(stats["errors"])}')
            for err in stats['errors'][:20]:
                print(f'    - {err}')


if __name__ == '__main__':
    main()
