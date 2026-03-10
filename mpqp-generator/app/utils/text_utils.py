"""Text processing utilities for document chunking and cleaning."""


def clean_text(text):
    """Remove excessive whitespace and normalize text."""
    import re
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into overlapping chunks by approximate token count.

    Uses simple word-based splitting (1 token ~ 0.75 words).
    """
    words = text.split()
    word_chunk_size = int(chunk_size * 0.75)
    word_overlap = int(overlap * 0.75)

    if len(words) <= word_chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + word_chunk_size
        chunk = ' '.join(words[start:end])
        chunks.append(chunk)
        start = end - word_overlap

    return chunks
