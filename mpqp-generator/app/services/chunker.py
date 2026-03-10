"""Semantic chunking for document text.

Splits documents into meaningful chunks that preserve context,
optimized for embedding and retrieval of technical manufacturing documents.
"""
import re
import logging

from flask import current_app

logger = logging.getLogger(__name__)

# Section header patterns common in MPQP/MPS/ITP documents
SECTION_PATTERNS = [
    r'^\d+\.\d+[\.\d]*\s+',          # Numbered sections: 1.1, 2.3.1
    r'^[A-Z][A-Z\s]{3,}$',            # ALL CAPS headings
    r'^(?:Section|SECTION)\s+\d+',     # "Section 1"
    r'^(?:Table|TABLE)\s+\d+',         # "Table 1"
    r'^(?:Appendix|APPENDIX)\s+[A-Z]', # "Appendix A"
    r'^\[Sheet:\s',                     # Excel sheet markers
]
SECTION_RE = re.compile('|'.join(SECTION_PATTERNS), re.MULTILINE)


def chunk_document(text, chunk_size=None, chunk_overlap=None):
    """Split document text into semantic chunks.

    Strategy:
    1. Split on section boundaries first (headers, numbered sections)
    2. If a section is too large, split on paragraph boundaries
    3. If still too large, split on sentence boundaries
    4. Add overlap between chunks for context continuity

    Returns list of dicts: [{'text': str, 'chunk_index': int, 'section': str}]
    """
    if not text or not text.strip():
        return []

    chunk_size = chunk_size or current_app.config.get('CHUNK_SIZE', 1000)
    chunk_overlap = chunk_overlap or current_app.config.get('CHUNK_OVERLAP', 200)

    # Approximate word count for chunk size (1 token ~ 0.75 words)
    max_words = int(chunk_size * 0.75)
    overlap_words = int(chunk_overlap * 0.75)

    # Step 1: Split into sections
    sections = _split_into_sections(text)

    # Step 2: Process each section into chunks
    chunks = []
    for section_title, section_text in sections:
        words = section_text.split()
        if len(words) <= max_words:
            # Section fits in one chunk
            chunks.append({
                'text': section_text.strip(),
                'section': section_title,
            })
        else:
            # Split large section into overlapping chunks
            sub_chunks = _split_large_section(section_text, max_words, overlap_words)
            for sc in sub_chunks:
                chunks.append({
                    'text': sc.strip(),
                    'section': section_title,
                })

    # Add chunk indices
    for i, chunk in enumerate(chunks):
        chunk['chunk_index'] = i

    # Filter out empty chunks
    chunks = [c for c in chunks if c['text'] and len(c['text'].split()) >= 10]

    logger.info(f'Chunked document into {len(chunks)} chunks')
    return chunks


def _split_into_sections(text):
    """Split text into sections based on header patterns.

    Returns list of (section_title, section_text) tuples.
    """
    lines = text.split('\n')
    sections = []
    current_title = ''
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and SECTION_RE.match(stripped):
            # Save previous section
            if current_lines:
                section_text = '\n'.join(current_lines)
                if section_text.strip():
                    sections.append((current_title, section_text))
            current_title = stripped[:100]  # Truncate very long headers
            current_lines = [line]
        else:
            current_lines.append(line)

    # Save last section
    if current_lines:
        section_text = '\n'.join(current_lines)
        if section_text.strip():
            sections.append((current_title, section_text))

    # If no sections found, treat entire text as one section
    if not sections:
        sections = [('', text)]

    return sections


def _split_large_section(text, max_words, overlap_words):
    """Split a large section into overlapping chunks.

    Tries paragraph boundaries first, then falls back to word splitting.
    """
    # Try splitting on paragraphs first
    paragraphs = re.split(r'\n\s*\n', text)
    if len(paragraphs) > 1:
        return _merge_paragraphs(paragraphs, max_words, overlap_words)

    # Fall back to word splitting with overlap
    return _word_split_with_overlap(text, max_words, overlap_words)


def _merge_paragraphs(paragraphs, max_words, overlap_words):
    """Merge paragraphs into chunks that fit within max_words."""
    chunks = []
    current_chunk = []
    current_words = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_words = len(para.split())

        if current_words + para_words > max_words and current_chunk:
            # Save current chunk
            chunks.append('\n\n'.join(current_chunk))

            # Keep overlap: find paragraphs from end that fit in overlap
            overlap_chunk = []
            overlap_count = 0
            for prev_para in reversed(current_chunk):
                pw = len(prev_para.split())
                if overlap_count + pw > overlap_words:
                    break
                overlap_chunk.insert(0, prev_para)
                overlap_count += pw

            current_chunk = overlap_chunk + [para]
            current_words = overlap_count + para_words
        else:
            current_chunk.append(para)
            current_words += para_words

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def _word_split_with_overlap(text, max_words, overlap_words):
    """Simple word-based splitting with overlap."""
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + max_words
        chunk = ' '.join(words[start:end])
        chunks.append(chunk)
        start = end - overlap_words

    return chunks
