"""OCR utilities for extracting text from images and PDFs.

Uses Tesseract (via pytesseract) for image OCR and pdfplumber for PDF text.
Falls back gracefully when dependencies are unavailable.
"""

import logging
import os

logger = logging.getLogger(__name__)


def is_tesseract_available():
    """Check if Tesseract OCR is installed and accessible."""
    try:
        import subprocess
        result = subprocess.run(['tesseract', '--version'],
                                capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def extract_text_from_image(image_path):
    """Extract text from an image file using Tesseract.

    Args:
        image_path: Path to image file (PNG, JPG, TIFF, etc.)

    Returns:
        Extracted text string, or None if OCR is unavailable.
    """
    if not os.path.exists(image_path):
        return None

    try:
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        # Use Swedish + English language for best results
        text = pytesseract.image_to_string(img, lang='swe+eng')
        return text.strip() if text else None

    except ImportError:
        logger.warning('pytesseract or Pillow not installed')
        return None
    except Exception as e:
        logger.warning('OCR failed for %s: %s', image_path, e)
        return None


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file.

    Uses pdfplumber for text-based PDFs. Falls back to Tesseract for scanned.

    Args:
        pdf_path: Path to PDF file.

    Returns:
        Extracted text string, or None if extraction fails.
    """
    if not os.path.exists(pdf_path):
        return None

    # Try pdfplumber first (fast, works for text-based PDFs)
    text = _extract_with_pdfplumber(pdf_path)
    if text and len(text.strip()) > 50:
        return text.strip()

    # Fall back to Tesseract OCR for scanned PDFs
    return _extract_pdf_with_tesseract(pdf_path)


def _extract_with_pdfplumber(pdf_path):
    """Extract text using pdfplumber."""
    try:
        import pdfplumber

        all_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    all_text.append(page_text)

        return '\n'.join(all_text) if all_text else None

    except ImportError:
        logger.warning('pdfplumber not installed')
        return None
    except Exception as e:
        logger.warning('pdfplumber extraction failed for %s: %s', pdf_path, e)
        return None


def _extract_pdf_with_tesseract(pdf_path):
    """Convert PDF to images and run Tesseract on each page."""
    try:
        import pytesseract
        from PIL import Image
        import subprocess
        import tempfile

        # Use pdftoppm to convert PDF to images
        with tempfile.TemporaryDirectory() as tmpdir:
            prefix = os.path.join(tmpdir, 'page')
            result = subprocess.run(
                ['pdftoppm', '-png', pdf_path, prefix],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                return None

            # OCR each page image
            all_text = []
            for f in sorted(os.listdir(tmpdir)):
                if f.endswith('.png'):
                    img = Image.open(os.path.join(tmpdir, f))
                    text = pytesseract.image_to_string(img, lang='swe+eng')
                    if text:
                        all_text.append(text)

            return '\n'.join(all_text) if all_text else None

    except (ImportError, FileNotFoundError):
        return None
    except Exception as e:
        logger.warning('PDF OCR failed for %s: %s', pdf_path, e)
        return None
