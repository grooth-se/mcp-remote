#!/usr/bin/env python3
"""Import all Excel files into local SQLite database."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.services.import_service import ImportService

app = create_app('development')

with app.app_context():
    folder = app.config['EXCEL_EXPORTS_FOLDER']
    if len(sys.argv) > 1:
        folder = sys.argv[1]

    print(f"Importing Excel files from: {folder}")
    print()

    service = ImportService()
    log = service.run_full_import(folder)

    print(f"Import completed: {log.status}")
    print(f"Total records: {log.records_imported}")
    print(f"Batch ID: {log.batch_id}")

    if log.details:
        import json
        details = json.loads(log.details)
        print("\nDetails:")
        for key, info in details.items():
            status = info.get('status', '?')
            records = info.get('records', '-')
            error = info.get('error', '')
            print(f"  {key:30s} {status:10s} {records}")
            if error:
                print(f"    ERROR: {error}")

    if log.errors:
        import json
        errors = json.loads(log.errors)
        print(f"\nErrors ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
