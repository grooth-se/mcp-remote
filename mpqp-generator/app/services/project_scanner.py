"""Historical project folder scanner.

Walks a root directory of historical projects, discovers documents,
creates Project + Document records in the database, and optionally
triggers text extraction and metadata extraction via LLM.

Expected folder structure (flexible):
  historical_projects/
    P-2020-001 Customer TTR/
      specs/
        customer_spec.pdf
      mpqp/
        MPQP_Rev2.docx
      itp/
        ITP.xlsx
    P-2021-042 Valve Body/
      ...

The scanner is tolerant of varied naming conventions.
"""
import os
import re
import logging
from datetime import datetime

from flask import current_app

from app import db
from app.models.project import Project, Customer
from app.models.document import Document
from app.services.document_processor import extract_text, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# Patterns to guess document type from filename/path
# Use looser boundaries (\b matches between word chars and non-word chars,
# but underscore is a word char — so we also check for start/underscore/hyphen)
DOC_TYPE_PATTERNS = [
    (r'(?i)(?:^|[\\/_ -])mpqp(?:[\\/_ .-]|$)', 'MPQP'),
    (r'(?i)(?:^|[\\/_ -])mps(?:[\\/_ .-]|$)', 'MPS'),
    (r'(?i)(?:^|[\\/_ -])itp(?:[\\/_ .-]|$)', 'ITP'),
    (r'(?i)(?:^|[\\/_ -])spec', 'SPEC'),
    (r'(?i)(?:^|[\\/_ -])drawing', 'DRAWING'),
    (r'(?i)(?:^|[\\/_ -])contract', 'CONTRACT'),
    (r'(?i)(?:^|[\\/_ -])standard', 'STANDARD'),
    (r'(?i)(?:^|[\\/_ -])wps(?:[\\/_ .-]|$)', 'MPS'),
    (r'(?i)(?:^|[\\/_ -])pqr(?:[\\/_ .-]|$)', 'MPS'),
    (r'(?i)(?:^|[\\/_ -])wpqr(?:[\\/_ .-]|$)', 'MPS'),
]

# Patterns to guess product type from folder name
PRODUCT_PATTERNS = [
    (r'(?i)\bttr\b', 'TTR'),
    (r'(?i)\bscr\b', 'SCR'),
    (r'(?i)\bcwor\b', 'CWOR'),
    (r'(?i)\bsls\b', 'SLS'),
    (r'(?i)\bbod(?:y|ies)\b', 'BODY'),
    (r'(?i)\bvalve\b', 'VALVE'),
    (r'(?i)\bflange\b', 'FLANGE'),
    (r'(?i)\briser\b', 'TTR'),
]

# Project number patterns: P-YYYY-NNN, or XXXX_YYY / XXXX-YYY
PROJECT_NUMBER_PATTERNS = [
    re.compile(r'([A-Z]-?\d{4}-\d{2,4})'),    # P-2020-001 style (check first)
    re.compile(r'(\d{4}[_-]\d{2,4})'),         # Subseatec: 0116_145, 0002-101
]


def _is_project_folder(name):
    """Check if a folder name looks like a project (has a project number)."""
    for pattern in PROJECT_NUMBER_PATTERNS:
        if pattern.search(name):
            return True
    return False


def _collect_project_folders(root_path):
    """Collect project folders, recursing into container folders like 'Delivered'.

    A container folder is one that doesn't match a project number pattern
    but contains subdirectories that do (e.g. 'Delivered/', 'Archive/').
    """
    folders = []
    entries = sorted(os.listdir(root_path))

    for entry in entries:
        folder_path = os.path.join(root_path, entry)
        if not os.path.isdir(folder_path) or entry.startswith('.'):
            continue

        if _is_project_folder(entry):
            folders.append((folder_path, entry))
        else:
            # Check if this is a container folder with project subfolders
            try:
                sub_entries = os.listdir(folder_path)
                sub_projects = [
                    (os.path.join(folder_path, s), s)
                    for s in sorted(sub_entries)
                    if os.path.isdir(os.path.join(folder_path, s))
                    and not s.startswith('.')
                    and _is_project_folder(s)
                ]
                if sub_projects:
                    logger.info(f'Container folder "{entry}": found {len(sub_projects)} projects')
                    folders.extend(sub_projects)
                else:
                    # Not a container, treat as a project anyway
                    folders.append((folder_path, entry))
            except PermissionError:
                logger.warning(f'Permission denied: {folder_path}')

    return folders


def scan_directory(root_path, extract_text_flag=True, dry_run=False, progress_callback=None):
    """Scan a root directory for project folders and their documents.

    Args:
        root_path: Path to the historical projects root
        extract_text_flag: Whether to extract text from documents during scan
        dry_run: If True, report what would be done without writing to DB
        progress_callback: Optional callable(msg, processed, total) for progress updates

    Returns:
        Dict with scan results.
    """
    if not os.path.isdir(root_path):
        return {'error': f'Directory not found: {root_path}'}

    results = {
        'root_path': root_path,
        'projects_found': 0,
        'projects_created': 0,
        'projects_skipped': 0,
        'documents_found': 0,
        'documents_created': 0,
        'documents_skipped': 0,
        'errors': [],
        'details': [],
    }

    # Each immediate subdirectory is treated as a project folder.
    # Container folders (e.g. "Delivered") that hold project subfolders
    # are detected and recursed into automatically.
    project_folders = _collect_project_folders(root_path)
    total = len(project_folders)

    if progress_callback:
        progress_callback(f'Found {total} project folders', 0, total)

    for idx, (folder_path, folder_name) in enumerate(project_folders):
        if progress_callback:
            progress_callback(f'Scanning: {folder_name}', idx, total)

        try:
            project_result = _process_project_folder(
                folder_path, folder_name, extract_text_flag, dry_run
            )
            results['details'].append(project_result)

            if project_result.get('created'):
                results['projects_created'] += 1
            elif project_result.get('skipped'):
                results['projects_skipped'] += 1
            results['projects_found'] += 1
            results['documents_found'] += project_result.get('documents_found', 0)
            results['documents_created'] += project_result.get('documents_created', 0)
            results['documents_skipped'] += project_result.get('documents_skipped', 0)

        except Exception as e:
            logger.error(f'Error processing folder {folder_name}: {e}')
            results['errors'].append(f'{folder_name}: {str(e)}')

    if progress_callback:
        progress_callback('Complete', total, total)

    logger.info(
        f'Scan complete: {results["projects_found"]} projects, '
        f'{results["documents_found"]} documents'
    )
    return results


def _process_project_folder(folder_path, folder_name, extract_text_flag, dry_run):
    """Process a single project folder."""
    result = {
        'folder': folder_name,
        'folder_path': folder_path,
        'documents_found': 0,
        'documents_created': 0,
        'documents_skipped': 0,
    }

    # Parse project number from folder name
    project_number = _extract_project_number(folder_name)
    if not project_number:
        project_number = folder_name[:50]  # Use folder name as fallback

    # Check if already exists
    existing = Project.query.filter_by(project_number=project_number).first()
    if existing:
        result['skipped'] = True
        result['reason'] = 'Project already exists'
        result['project_id'] = existing.id
        # Still scan for new documents
        _scan_documents_for_project(existing, folder_path, extract_text_flag, dry_run, result)
        return result

    if dry_run:
        result['created'] = False
        result['dry_run'] = True
        docs = _find_documents(folder_path)
        result['documents_found'] = len(docs)
        return result

    # Guess metadata from folder name
    product_type = _guess_product_type(folder_name)
    customer_name = _guess_customer_name(folder_name, project_number)

    # Get or create customer
    customer_id = None
    if customer_name:
        customer = Customer.query.filter_by(name=customer_name).first()
        if not customer:
            customer = Customer(name=customer_name)
            db.session.add(customer)
            db.session.flush()
        customer_id = customer.id

    # Create project
    project = Project(
        project_number=project_number,
        project_name=folder_name,
        customer_id=customer_id,
        product_type=product_type,
        product_category=Project.PRODUCT_CATEGORIES.get(product_type, ''),
        folder_path=folder_path,
    )
    db.session.add(project)
    db.session.flush()

    result['created'] = True
    result['project_id'] = project.id
    result['project_number'] = project_number

    # Scan and create documents
    _scan_documents_for_project(project, folder_path, extract_text_flag, dry_run, result)

    db.session.commit()
    return result


def _scan_documents_for_project(project, folder_path, extract_text_flag, dry_run, result):
    """Recursively find and register documents for a project."""
    doc_files = _find_documents(folder_path)
    result['documents_found'] = len(doc_files)

    for file_path in doc_files:
        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lower()

        # Check if document already registered
        existing_doc = Document.query.filter_by(
            project_id=project.id, file_name=file_name
        ).first()
        if existing_doc:
            result['documents_skipped'] += 1
            continue

        if dry_run:
            result['documents_created'] += 1
            continue

        # Determine document type and format
        doc_type = _guess_document_type(file_path)
        file_format = Document.FORMAT_EXTENSIONS.get(ext, ext.upper().lstrip('.'))
        file_size = os.path.getsize(file_path)

        doc = Document(
            project_id=project.id,
            document_type=doc_type,
            file_name=file_name,
            file_path=file_path,
            file_format=file_format,
            file_size=file_size,
        )

        # Optionally extract text during scan
        if extract_text_flag:
            try:
                extraction = extract_text(file_path)
                doc.extracted_text = extraction.get('text', '')
                doc.page_count = extraction.get('page_count', 0)
                doc.metadata_ = extraction.get('metadata', {})
            except Exception as e:
                logger.warning(f'Text extraction failed for {file_path}: {e}')

        db.session.add(doc)
        result['documents_created'] += 1


def _find_documents(folder_path):
    """Recursively find all supported document files in a folder."""
    documents = []
    for root, dirs, files in os.walk(folder_path):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in sorted(files):
            if f.startswith('.') or f.startswith('~$'):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                documents.append(os.path.join(root, f))
    return documents


def _extract_project_number(folder_name):
    """Try to extract a project number from the folder name."""
    for pattern in PROJECT_NUMBER_PATTERNS:
        match = pattern.search(folder_name)
        if match:
            return match.group(1)
    return None


def _guess_product_type(folder_name):
    """Guess product type from folder name."""
    for pattern, ptype in PRODUCT_PATTERNS:
        if re.search(pattern, folder_name):
            return ptype
    return ''


def _guess_customer_name(folder_name, project_number):
    """Try to extract customer name from folder name.

    Heuristic: remove the project number and product type keywords,
    the remainder is likely the customer name.
    """
    name = folder_name
    # Remove project number
    if project_number:
        name = name.replace(project_number, '')
    # Remove product type keywords
    for pattern, _ in PRODUCT_PATTERNS:
        name = re.sub(pattern, '', name)
    # Clean up separators and whitespace
    name = re.sub(r'[-_]+', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)
    # If too short or just numbers, skip
    if len(name) < 2 or name.isdigit():
        return None
    return name


def _guess_document_type(file_path):
    """Guess document type from filename and path."""
    combined = file_path.lower()
    for pattern, doc_type in DOC_TYPE_PATTERNS:
        if re.search(pattern, combined):
            return doc_type
    return 'OTHER'
