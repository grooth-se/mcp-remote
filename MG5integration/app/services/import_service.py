"""Orchestrate data imports from Excel files into local database."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.extensions import db
from app.models.extraction import ExtractionLog
from app.utils.excel_analyzer import find_file_for_key
from app.extractors import (
    AccountExtractor, VerificationExtractor,
    ProjectExtractor, ProjectAdjustmentExtractor,
    TimeTrackingExtractor, CrossRefExtractor,
    CustomerOrderExtractor, PurchaseOrderExtractor,
    QuoteExtractor, OrderIntakeExtractor,
    InvoiceLogExtractor, ExchangeRateExtractor,
    ArticleExtractor, MinimumStockExtractor,
)


# Import order matters: projects before adjustments/time (FK dependencies)
EXTRACTOR_REGISTRY = [
    ('kontoplan', AccountExtractor),
    ('projektuppf', ProjectExtractor),
    ('projectadjustments', ProjectAdjustmentExtractor),
    ('tiduppfoljning', TimeTrackingExtractor),
    ('CO_proj_crossref', CrossRefExtractor),
    ('kundorderforteckning', CustomerOrderExtractor),
    ('inkoporderforteckning', PurchaseOrderExtractor),
    ('offertforteckning', QuoteExtractor),
    ('orderingang', OrderIntakeExtractor),
    ('faktureringslogg', InvoiceLogExtractor),
    ('valutakurser', ExchangeRateExtractor),
    ('artikellista', ArticleExtractor),
    ('min_stock', MinimumStockExtractor),
    ('verlista', VerificationExtractor),  # Last: largest file
]


class ImportService:
    """Orchestrate full data import from Excel files."""

    @staticmethod
    def cleanup_stale_runs():
        """Mark any 'running' extraction logs as interrupted.

        Call on app startup to recover from lost connections / crashes.
        """
        stale = ExtractionLog.query.filter_by(status='running').all()
        for log in stale:
            log.status = 'interrupted'
            log.completed_at = datetime.now(timezone.utc)
            existing_errors = json.loads(log.errors) if log.errors else []
            existing_errors.append('Process interrupted (lost connection or crash)')
            log.errors = json.dumps(existing_errors)
        if stale:
            db.session.commit()
        return len(stale)

    def run_full_import(self, excel_folder):
        """Run full import of all Excel files.

        Returns ExtractionLog entry.
        """
        batch_id = str(uuid.uuid4())
        log = ExtractionLog(
            batch_id=batch_id,
            source='excel',
            status='running',
        )
        db.session.add(log)
        db.session.commit()

        total_records = 0
        details = {}
        errors = []

        try:
            for key, extractor_class in EXTRACTOR_REGISTRY:
                filepath = find_file_for_key(excel_folder, key)
                if filepath is None:
                    errors.append(f'{key}: file not found')
                    details[key] = {'status': 'skipped', 'reason': 'file not found'}
                    self._update_log_progress(log, total_records, details, errors)
                    continue

                try:
                    extractor = extractor_class()
                    count = extractor.extract_from_excel(str(filepath), batch_id)
                    total_records += count
                    details[key] = {'status': 'success', 'records': count}
                except Exception as e:
                    errors.append(f'{key}: {str(e)}')
                    details[key] = {'status': 'error', 'error': str(e)}
                    db.session.rollback()

                # Commit progress after each table so partial work is visible
                self._update_log_progress(log, total_records, details, errors)

            log.status = 'success' if not errors else 'partial'
        except Exception as e:
            errors.append(f'Fatal: {str(e)}')
            log.status = 'failed'
        finally:
            log.completed_at = datetime.now(timezone.utc)
            log.records_imported = total_records
            log.errors = json.dumps(errors) if errors else None
            log.details = json.dumps(details)
            db.session.commit()

        return log

    def _update_log_progress(self, log, total_records, details, errors):
        """Save incremental progress to the extraction log."""
        log.records_imported = total_records
        log.details = json.dumps(details)
        log.errors = json.dumps(errors) if errors else None
        db.session.commit()

    def run_single_import(self, key, filepath):
        """Import a single file by key.

        Returns dict with {records, status, error}.
        """
        for reg_key, extractor_class in EXTRACTOR_REGISTRY:
            if reg_key == key:
                batch_id = str(uuid.uuid4())
                try:
                    extractor = extractor_class()
                    count = extractor.extract_from_excel(filepath, batch_id)
                    return {'records': count, 'status': 'success', 'error': None}
                except Exception as e:
                    db.session.rollback()
                    return {'records': 0, 'status': 'error', 'error': str(e)}

        return {'records': 0, 'status': 'error', 'error': f'Unknown key: {key}'}
