#!/usr/bin/env python3
"""Incremental indexing — scan for new/updated documents in existing project folders.

Usage:
    python scripts/update_index.py [--extract-metadata] [--embed]

Scans all registered project folder paths for new documents
that aren't yet in the database.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Incremental index update')
    parser.add_argument('--extract-metadata', action='store_true')
    parser.add_argument('--embed', action='store_true')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        from app.models.project import Project
        from app.models.document import Document
        from app.services.project_scanner import _find_documents, _guess_document_type
        from app.services.document_processor import extract_text

        projects = Project.query.all()
        new_docs = 0

        print(f'Checking {len(projects)} projects for new documents...\n')

        for project in projects:
            if not os.path.isdir(project.folder_path):
                print(f'  SKIP {project.project_number} — folder not found: {project.folder_path}')
                continue

            existing_files = {d.file_name for d in Document.query.filter_by(project_id=project.id).all()}
            all_files = _find_documents(project.folder_path)

            for file_path in all_files:
                file_name = os.path.basename(file_path)
                if file_name in existing_files:
                    continue

                ext = os.path.splitext(file_name)[1].lower()
                doc_type = _guess_document_type(file_path)
                fmt_map = {'.pdf': 'PDF', '.docx': 'DOCX', '.doc': 'DOC', '.xlsx': 'XLSX', '.xls': 'XLS'}

                doc = Document(
                    project_id=project.id,
                    document_type=doc_type,
                    file_name=file_name,
                    file_path=file_path,
                    file_format=fmt_map.get(ext, ext.upper().lstrip('.')),
                    file_size=os.path.getsize(file_path),
                )

                try:
                    extraction = extract_text(file_path)
                    doc.extracted_text = extraction.get('text', '')
                    doc.page_count = extraction.get('page_count', 0)
                except Exception as e:
                    print(f'  WARN text extraction failed: {file_name}: {e}')

                db.session.add(doc)
                new_docs += 1
                print(f'  NEW: {project.project_number}/{file_name} ({doc_type})')

        db.session.commit()
        print(f'\nFound {new_docs} new document(s).')

        # Optional metadata extraction
        if args.extract_metadata and new_docs > 0:
            print('\nExtracting metadata for projects with new documents...')
            from app.services.metadata_extractor import extract_project_metadata
            for project in projects:
                if not project.materials:
                    result = extract_project_metadata(project.id)
                    status = 'OK' if 'error' not in result else result['error']
                    print(f'  {project.project_number}: {status}')

        # Optional embedding
        if args.embed and new_docs > 0:
            print('\nEmbedding new documents...')
            from app.services.embedder import index_document
            docs = Document.query.filter(
                Document.extracted_text.isnot(None),
                Document.indexed_at.is_(None),
            ).all()
            for doc in docs:
                result = index_document(doc.id)
                status = f'{result["chunks_indexed"]} chunks' if 'error' not in result else result['error']
                print(f'  {doc.file_name}: {status}')

        print('Done.')


if __name__ == '__main__':
    main()
