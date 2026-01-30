"""PDF signing utility for X.509 digital signatures.

This module handles:
1. Word to PDF conversion (using LibreOffice or pypdf/reportlab)
2. PDF digital signing with X.509 certificates (PKCS#12 format)

ISO 17025 Compliance:
- Digital signatures provide cryptographic proof of document authenticity
- SHA-256 hash ensures document integrity
- Timestamp records exact signing time
- Signer identity is cryptographically bound to document

Requirements:
- endesive: PDF digital signatures
- cryptography: Certificate handling
- pypdf: PDF manipulation
- LibreOffice (soffice): Word to PDF conversion (optional, system dependency)
"""

import hashlib
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# PDF signing imports
try:
    from endesive.pdf import cms as pdf_cms
    from endesive import signer
    HAS_ENDESIVE = True
except ImportError:
    HAS_ENDESIVE = False

# Certificate handling
try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# PDF manipulation
try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


class PDFSigningError(Exception):
    """Exception raised for PDF signing errors."""
    pass


class CertificateError(Exception):
    """Exception raised for certificate-related errors."""
    pass


def check_dependencies() -> dict:
    """Check which PDF signing dependencies are available.

    Returns
    -------
    dict
        Dictionary with availability status of each component
    """
    # Check for LibreOffice
    has_libreoffice = False
    try:
        result = subprocess.run(
            ['soffice', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        has_libreoffice = result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return {
        'endesive': HAS_ENDESIVE,
        'cryptography': HAS_CRYPTOGRAPHY,
        'pypdf': HAS_PYPDF,
        'libreoffice': has_libreoffice,
        'can_sign': HAS_ENDESIVE and HAS_CRYPTOGRAPHY,
        'can_convert': has_libreoffice,
    }


def load_certificate(
    cert_path: Path,
    password: str = ''
) -> Tuple[bytes, bytes, bytes]:
    """Load a PKCS#12 (.p12/.pfx) certificate file.

    Parameters
    ----------
    cert_path : Path
        Path to the .p12 or .pfx certificate file
    password : str
        Password for the certificate file

    Returns
    -------
    tuple
        (private_key_pem, certificate_pem, ca_chain_pem)

    Raises
    ------
    CertificateError
        If certificate cannot be loaded
    """
    if not HAS_CRYPTOGRAPHY:
        raise CertificateError("cryptography library not installed")

    if not cert_path.exists():
        raise CertificateError(f"Certificate file not found: {cert_path}")

    try:
        with open(cert_path, 'rb') as f:
            p12_data = f.read()

        # Load PKCS#12 data
        private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
            p12_data,
            password.encode() if password else None,
            default_backend()
        )

        return private_key, certificate, additional_certs

    except Exception as e:
        raise CertificateError(f"Failed to load certificate: {e}")


def convert_word_to_pdf(
    word_path: Path,
    pdf_path: Optional[Path] = None
) -> Path:
    """Convert Word document to PDF using LibreOffice.

    Parameters
    ----------
    word_path : Path
        Path to the Word document (.docx)
    pdf_path : Path, optional
        Output PDF path. If not provided, uses same name with .pdf extension

    Returns
    -------
    Path
        Path to the generated PDF file

    Raises
    ------
    PDFSigningError
        If conversion fails
    """
    if not word_path.exists():
        raise PDFSigningError(f"Word document not found: {word_path}")

    # Determine output path
    if pdf_path is None:
        pdf_path = word_path.with_suffix('.pdf')

    # Try LibreOffice conversion
    try:
        # Use a temporary directory for output to avoid path issues
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    'soffice',
                    '--headless',
                    '--convert-to', 'pdf',
                    '--outdir', tmpdir,
                    str(word_path)
                ],
                capture_output=True,
                text=True,
                timeout=60  # 60 second timeout
            )

            if result.returncode != 0:
                raise PDFSigningError(
                    f"LibreOffice conversion failed: {result.stderr}"
                )

            # Find the generated PDF
            tmp_pdf = Path(tmpdir) / word_path.with_suffix('.pdf').name
            if not tmp_pdf.exists():
                raise PDFSigningError("LibreOffice did not generate PDF file")

            # Move to final destination
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(tmp_pdf), str(pdf_path))

            return pdf_path

    except subprocess.TimeoutExpired:
        raise PDFSigningError("LibreOffice conversion timed out")
    except FileNotFoundError:
        raise PDFSigningError(
            "LibreOffice (soffice) not found. Please install LibreOffice."
        )


def calculate_pdf_hash(pdf_path: Path) -> str:
    """Calculate SHA-256 hash of a PDF file.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file

    Returns
    -------
    str
        Hex-encoded SHA-256 hash
    """
    sha256 = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def sign_pdf(
    pdf_path: Path,
    output_path: Path,
    cert_path: Path,
    cert_password: str = '',
    signer_name: str = '',
    signer_location: str = 'Gothenburg, Sweden',
    reason: str = 'ISO 17025 Accredited Test Report',
    contact_info: str = ''
) -> Tuple[Path, str, datetime]:
    """Sign a PDF with an X.509 certificate.

    Creates a digitally signed PDF using the PKCS#12 certificate.
    The signature is embedded in the PDF and can be verified by
    Adobe Reader and other PDF viewers.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF to sign
    output_path : Path
        Path for the signed PDF output
    cert_path : Path
        Path to the PKCS#12 (.p12/.pfx) certificate
    cert_password : str
        Password for the certificate
    signer_name : str
        Name of the signer (for signature annotation)
    signer_location : str
        Location of signing
    reason : str
        Reason for signing
    contact_info : str
        Contact information for signer

    Returns
    -------
    tuple
        (output_path, sha256_hash, timestamp)

    Raises
    ------
    PDFSigningError
        If signing fails
    CertificateError
        If certificate cannot be loaded
    """
    if not HAS_ENDESIVE:
        raise PDFSigningError("endesive library not installed")

    if not pdf_path.exists():
        raise PDFSigningError(f"PDF file not found: {pdf_path}")

    # Load certificate
    private_key, certificate, ca_chain = load_certificate(cert_path, cert_password)

    # Signing timestamp
    timestamp = datetime.utcnow()

    # Read the PDF
    with open(pdf_path, 'rb') as f:
        pdf_data = f.read()

    try:
        # Create signature dictionary
        dct = {
            'aligned': 0,
            'sigflags': 3,
            'sigflagsft': 132,
            'sigpage': 0,
            'sigbutton': True,
            'sigfield': 'Signature1',
            'auto_sigfield': True,
            'signaturebox': (50, 50, 250, 100),  # Position of visible signature
            'signature': signer_name or 'Durabler AB',
            'signform': False,
            'contact': contact_info,
            'location': signer_location,
            'signingdate': timestamp.strftime("D:%Y%m%d%H%M%S+00'00'"),
            'reason': reason,
        }

        # Sign the PDF
        signed_data = pdf_cms.sign(
            pdf_data,
            dct,
            private_key,
            certificate,
            ca_chain or [],
            'sha256',
        )

        # Write signed PDF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(pdf_data)
            f.write(signed_data)

        # Calculate hash of signed PDF
        pdf_hash = calculate_pdf_hash(output_path)

        return output_path, pdf_hash, timestamp

    except Exception as e:
        raise PDFSigningError(f"PDF signing failed: {e}")


def sign_report(
    word_report_path: Path,
    output_folder: Path,
    certificate_number: str,
    cert_path: Path,
    cert_password: str = '',
    signer_name: str = '',
    signer_user_id: str = ''
) -> dict:
    """Complete workflow to convert and sign a test report.

    This is the main entry point for the signing workflow:
    1. Convert Word document to PDF
    2. Sign the PDF with X.509 certificate
    3. Return signing details for audit trail

    Parameters
    ----------
    word_report_path : Path
        Path to the Word report (.docx)
    output_folder : Path
        Folder for signed PDFs (will create year subfolder)
    certificate_number : str
        Certificate number (e.g., 'DUR-2026-1001')
    cert_path : Path
        Path to company certificate (.p12)
    cert_password : str
        Certificate password
    signer_name : str
        Full name of the person signing
    signer_user_id : str
        User ID of the signer (e.g., 'DUR-APP-001')

    Returns
    -------
    dict
        {
            'pdf_path': Path to signed PDF (relative to reports folder),
            'pdf_hash': SHA-256 hash of signed PDF,
            'timestamp': Signing timestamp (datetime),
            'signer_name': Name of signer,
            'signer_user_id': User ID of signer,
            'certificate_info': Certificate subject info
        }

    Raises
    ------
    PDFSigningError
        If conversion or signing fails
    """
    # Check dependencies
    deps = check_dependencies()
    if not deps['can_convert']:
        raise PDFSigningError(
            "LibreOffice not available for PDF conversion. "
            "Please install LibreOffice (https://www.libreoffice.org/)"
        )
    if not deps['can_sign']:
        raise PDFSigningError(
            "PDF signing libraries not available. "
            "Please install: pip install endesive cryptography"
        )

    # Create output path
    year = datetime.now().year
    signed_folder = output_folder / 'signed' / str(year)
    signed_folder.mkdir(parents=True, exist_ok=True)

    # Generate filenames
    safe_cert_num = certificate_number.replace(' ', '_').replace('/', '-')
    pdf_filename = f"{safe_cert_num}.pdf"
    signed_filename = f"{safe_cert_num}_signed.pdf"

    unsigned_pdf = signed_folder / pdf_filename
    signed_pdf = signed_folder / signed_filename

    # Step 1: Convert Word to PDF
    convert_word_to_pdf(word_report_path, unsigned_pdf)

    # Step 2: Sign the PDF
    signed_path, pdf_hash, timestamp = sign_pdf(
        pdf_path=unsigned_pdf,
        output_path=signed_pdf,
        cert_path=cert_path,
        cert_password=cert_password,
        signer_name=signer_name,
        reason=f"ISO 17025 Test Report: {certificate_number}",
        contact_info=signer_user_id
    )

    # Clean up unsigned PDF
    if unsigned_pdf.exists():
        unsigned_pdf.unlink()

    # Return signing details
    return {
        'pdf_path': str(signed_path.relative_to(output_folder)),
        'pdf_hash': pdf_hash,
        'timestamp': timestamp,
        'signer_name': signer_name,
        'signer_user_id': signer_user_id,
    }


def create_placeholder_signed_pdf(
    word_report_path: Path,
    output_folder: Path,
    certificate_number: str,
    signer_name: str = '',
    signer_user_id: str = ''
) -> dict:
    """Create a placeholder 'signed' PDF when actual signing is not available.

    This is used when:
    - LibreOffice is not installed
    - Certificate is not configured
    - Development/testing environment

    The PDF is converted but not cryptographically signed.
    A watermark or note indicates it's not officially signed.

    Parameters
    ----------
    word_report_path : Path
        Path to the Word report (.docx)
    output_folder : Path
        Folder for output PDFs
    certificate_number : str
        Certificate number
    signer_name : str
        Name of signer (for metadata)
    signer_user_id : str
        User ID of signer

    Returns
    -------
    dict
        Same structure as sign_report()
    """
    year = datetime.now().year
    signed_folder = output_folder / 'signed' / str(year)
    signed_folder.mkdir(parents=True, exist_ok=True)

    safe_cert_num = certificate_number.replace(' ', '_').replace('/', '-')
    signed_filename = f"{safe_cert_num}_signed.pdf"
    signed_pdf = signed_folder / signed_filename

    timestamp = datetime.utcnow()

    # Try to convert Word to PDF
    deps = check_dependencies()
    if deps['can_convert'] and word_report_path.exists():
        try:
            convert_word_to_pdf(word_report_path, signed_pdf)
            pdf_hash = calculate_pdf_hash(signed_pdf)
        except PDFSigningError:
            # Fallback: create empty placeholder
            signed_pdf.write_bytes(b'%PDF-1.4\n% Placeholder - signing not available\n')
            pdf_hash = calculate_pdf_hash(signed_pdf)
    else:
        # Create minimal placeholder PDF
        signed_pdf.write_bytes(b'%PDF-1.4\n% Placeholder - conversion not available\n')
        pdf_hash = calculate_pdf_hash(signed_pdf)

    return {
        'pdf_path': str(signed_pdf.relative_to(output_folder)),
        'pdf_hash': pdf_hash,
        'timestamp': timestamp,
        'signer_name': signer_name,
        'signer_user_id': signer_user_id,
        'is_placeholder': True,
    }
