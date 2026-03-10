#!/usr/bin/env python3
"""One-time batch indexing of historical project folders.

Usage:
    python scripts/index_historical.py /path/to/projects [--dry-run] [--no-text] [--extract-metadata] [--embed]

Steps:
    1. Scans project folders, creates Project + Document records
    2. Extracts text from all documents (unless --no-text)
    3. Optionally extracts metadata via LLM (--extract-metadata)
    4. Optionally generates embeddings and stores in vector DB (--embed)
"""
import sys
import os
import argparse
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def main():
    parser = argparse.ArgumentParser(description='Index historical project folders')
    parser.add_argument('path', help='Root directory of historical projects')
    parser.add_argument('--dry-run', action='store_true', help='Report what would be done without writing')
    parser.add_argument('--no-text', action='store_true', help='Skip text extraction during scan')
    parser.add_argument('--extract-metadata', action='store_true', help='Use LLM to extract metadata')
    parser.add_argument('--embed', action='store_true', help='Generate embeddings and store in vector DB')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        db.create_all()

        # Step 1: Scan folders
        print(f'\n=== Scanning: {args.path} ===\n')
        from app.services.project_scanner import scan_directory
        scan_result = scan_directory(
            args.path,
            extract_text_flag=not args.no_text,
            dry_run=args.dry_run,
        )

        if scan_result.get('error'):
            print(f'ERROR: {scan_result["error"]}')
            sys.exit(1)

        print(f'Projects found:    {scan_result["projects_found"]}')
        print(f'Projects created:  {scan_result["projects_created"]}')
        print(f'Projects skipped:  {scan_result["projects_skipped"]}')
        print(f'Documents found:   {scan_result["documents_found"]}')
        print(f'Documents created: {scan_result["documents_created"]}')
        print(f'Documents skipped: {scan_result["documents_skipped"]}')

        if scan_result['errors']:
            print(f'\nErrors ({len(scan_result["errors"])}):')
            for err in scan_result['errors']:
                print(f'  - {err}')

        if args.dry_run:
            print('\n(Dry run — no changes made)')
            return

        # Step 2: Extract metadata via LLM
        if args.extract_metadata:
            print('\n=== Extracting metadata via LLM ===\n')
            from app.services.metadata_extractor import extract_project_metadata
            from app.models.project import Project

            projects = Project.query.filter(
                Project.metadata_.is_(None) | (Project.materials == [])
            ).all()

            for i, project in enumerate(projects):
                print(f'  [{i+1}/{len(projects)}] {project.project_number}...', end=' ', flush=True)
                t0 = time.time()
                result = extract_project_metadata(project.id)
                elapsed = time.time() - t0

                if 'error' in result:
                    print(f'FAILED ({result["error"]})')
                else:
                    materials = result.get('materials', [])
                    standards = result.get('standards', [])
                    print(f'OK ({elapsed:.1f}s, {len(materials)} materials, {len(standards)} standards)')

        # Step 3: Generate embeddings
        if args.embed:
            print('\n=== Generating embeddings ===\n')
            from app.services.embedder import index_document
            from app.models.document import Document

            docs = Document.query.filter(
                Document.extracted_text.isnot(None),
                Document.indexed_at.is_(None),
            ).all()

            total = len(docs)
            success = 0
            failed = 0

            for i, doc in enumerate(docs):
                print(f'  [{i+1}/{total}] {doc.file_name}...', end=' ', flush=True)
                t0 = time.time()
                result = index_document(doc.id)
                elapsed = time.time() - t0

                if 'error' in result:
                    print(f'FAILED ({result["error"]})')
                    failed += 1
                else:
                    print(f'OK ({elapsed:.1f}s, {result["chunks_indexed"]} chunks)')
                    success += 1

            print(f'\nEmbedding complete: {success} succeeded, {failed} failed')

        print('\nDone.')


if __name__ == '__main__':
    main()
