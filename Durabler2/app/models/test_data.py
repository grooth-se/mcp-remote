"""Models for storing raw test data, photos, and reports in database.

These models enable full data persistence without relying on external files,
supporting ISO 17025 data traceability requirements.
"""
import zlib
from datetime import datetime
from app.extensions import db


class RawTestData(db.Model):
    """Store raw test data (CSV/Excel) as compressed BLOB.

    Enables complete data recall without original files.
    Data is compressed with zlib to reduce storage size.
    """
    __tablename__ = 'raw_test_data'

    id = db.Column(db.Integer, primary_key=True)
    test_record_id = db.Column(db.Integer, db.ForeignKey('test_records.id'),
                               nullable=False, index=True)

    # File information
    data_type = db.Column(db.String(20), nullable=False)  # 'csv', 'excel', 'precrack_csv'
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)  # Original uncompressed size in bytes

    # Compressed data storage
    data_compressed = db.Column(db.LargeBinary)  # zlib compressed
    compression_ratio = db.Column(db.Float)  # For info: original_size / compressed_size

    # Metadata
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    test_record = db.relationship('TestRecord', backref=db.backref(
        'raw_data_files', lazy='dynamic', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def set_data(self, data: bytes):
        """Store data with compression."""
        self.file_size = len(data)
        self.data_compressed = zlib.compress(data, level=6)
        compressed_size = len(self.data_compressed)
        self.compression_ratio = self.file_size / compressed_size if compressed_size > 0 else 1.0

    def get_data(self) -> bytes:
        """Retrieve and decompress data."""
        if self.data_compressed:
            return zlib.decompress(self.data_compressed)
        return b''

    @property
    def compressed_size(self) -> int:
        """Get compressed data size."""
        return len(self.data_compressed) if self.data_compressed else 0

    def __repr__(self) -> str:
        return f'<RawTestData {self.data_type}: {self.original_filename}>'


class TestPhoto(db.Model):
    """Store test photos (crack surfaces, specimens) as BLOB.

    Photos are stored uncompressed since JPEG/PNG are already compressed.
    """
    __tablename__ = 'test_photos'

    id = db.Column(db.Integer, primary_key=True)
    test_record_id = db.Column(db.Integer, db.ForeignKey('test_records.id'),
                               nullable=False, index=True)

    # Photo information
    photo_number = db.Column(db.Integer, default=1)  # 1, 2, 3 for ordering
    description = db.Column(db.String(255))
    original_filename = db.Column(db.String(255))
    mime_type = db.Column(db.String(50))  # 'image/jpeg', 'image/png'
    file_size = db.Column(db.Integer)

    # Image dimensions (optional, for display)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)

    # Image data (stored as-is, already compressed)
    data = db.Column(db.LargeBinary, nullable=False)

    # Metadata
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    test_record = db.relationship('TestRecord', backref=db.backref(
        'photos', lazy='dynamic', cascade='all, delete-orphan',
        order_by='TestPhoto.photo_number'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def set_image(self, data: bytes, filename: str = None):
        """Store image data and detect dimensions if possible."""
        self.data = data
        self.file_size = len(data)

        if filename:
            self.original_filename = filename
            # Set mime type based on extension
            ext = filename.lower().rsplit('.', 1)[-1]
            mime_types = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif'
            }
            self.mime_type = mime_types.get(ext, 'image/jpeg')

        # Try to detect image dimensions
        self._detect_dimensions(data)

    def _detect_dimensions(self, data: bytes):
        """Detect image dimensions from header bytes."""
        try:
            # PNG detection
            if data[:8] == b'\x89PNG\r\n\x1a\n':
                if len(data) >= 24:
                    self.width = int.from_bytes(data[16:20], 'big')
                    self.height = int.from_bytes(data[20:24], 'big')
                return

            # JPEG detection (simplified)
            if data[:2] == b'\xff\xd8':
                # Find SOF0 marker for dimensions
                i = 2
                while i < len(data) - 9:
                    if data[i] == 0xff:
                        marker = data[i+1]
                        if marker in (0xc0, 0xc1, 0xc2):  # SOF markers
                            self.height = int.from_bytes(data[i+5:i+7], 'big')
                            self.width = int.from_bytes(data[i+7:i+9], 'big')
                            return
                        elif marker == 0xd9:  # EOI
                            break
                        else:
                            # Skip to next marker
                            length = int.from_bytes(data[i+2:i+4], 'big')
                            i += 2 + length
                    else:
                        i += 1
        except Exception:
            pass  # Dimensions are optional

    def __repr__(self) -> str:
        return f'<TestPhoto #{self.photo_number}: {self.description or self.original_filename}>'


class ReportFile(db.Model):
    """Store generated reports (Word, PDF) as BLOB.

    Maintains complete report history for audit trail.
    """
    __tablename__ = 'report_files'

    id = db.Column(db.Integer, primary_key=True)
    test_record_id = db.Column(db.Integer, db.ForeignKey('test_records.id'),
                               nullable=False, index=True)

    # Report information
    report_type = db.Column(db.String(20), nullable=False)  # 'word_draft', 'pdf_signed'
    version = db.Column(db.Integer, default=1)
    original_filename = db.Column(db.String(255))
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)

    # For signed PDFs
    certificate_number = db.Column(db.String(50))
    pdf_hash = db.Column(db.String(64))  # SHA-256 hash for integrity
    signed_by = db.Column(db.String(100))  # Approver name
    signed_at = db.Column(db.DateTime)

    # Compressed data storage (Word docs compress well)
    data_compressed = db.Column(db.LargeBinary)
    compression_ratio = db.Column(db.Float)

    # Metadata
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    test_record = db.relationship('TestRecord', backref=db.backref(
        'report_files', lazy='dynamic', cascade='all, delete-orphan',
        order_by='ReportFile.generated_at.desc()'))
    generated_by = db.relationship('User', foreign_keys=[generated_by_id])

    def set_data(self, data: bytes):
        """Store report data with compression."""
        self.file_size = len(data)
        self.data_compressed = zlib.compress(data, level=6)
        compressed_size = len(self.data_compressed)
        self.compression_ratio = self.file_size / compressed_size if compressed_size > 0 else 1.0

    def get_data(self) -> bytes:
        """Retrieve and decompress report data."""
        if self.data_compressed:
            return zlib.decompress(self.data_compressed)
        return b''

    @property
    def compressed_size(self) -> int:
        """Get compressed data size."""
        return len(self.data_compressed) if self.data_compressed else 0

    def __repr__(self) -> str:
        return f'<ReportFile {self.report_type} v{self.version}: {self.original_filename}>'
