"""Test record and analysis models."""
from datetime import datetime
from app.extensions import db


class TestRecord(db.Model):
    """Test record storing test metadata and status.

    Attributes
    ----------
    id : int
        Primary key
    test_id : str
        Unique test identifier (e.g., 'DUR-2026-0001')
    test_method : str
        Test type: TENSILE, SONIC, FCGR, CTOD, KIC, VICKERS
    test_standard : str
        Standard reference (e.g., 'ASTM E8/E8M-22')
    specimen_id : str
        Specimen identification
    material : str
        Material description
    test_date : datetime
        Date/time of test
    status : str
        Status: DRAFT, ANALYZED, REVIEWED, APPROVED
    """
    __tablename__ = 'test_records'

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    test_method = db.Column(db.String(20), nullable=False)  # TENSILE, SONIC, etc.
    test_standard = db.Column(db.String(50))
    specimen_id = db.Column(db.String(50))
    material = db.Column(db.String(100))
    batch_number = db.Column(db.String(50))

    # Specimen geometry (JSON for flexibility)
    geometry = db.Column(db.JSON)

    # Test conditions
    test_date = db.Column(db.DateTime)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    machine_id = db.Column(db.String(50))

    # File references
    raw_data_filename = db.Column(db.String(255))

    # Status tracking
    status = db.Column(db.String(20), default='DRAFT')
    certificate_number = db.Column(db.String(50))  # Legacy field for display

    # Link to certificate register
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'), index=True)

    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    results = db.relationship('AnalysisResult', backref='test_record',
                              lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<TestRecord {self.test_id}>'


class AnalysisResult(db.Model):
    """Analysis result with uncertainty.

    Stores individual calculated parameters with their uncertainties.
    """
    __tablename__ = 'analysis_results'

    id = db.Column(db.Integer, primary_key=True)
    test_record_id = db.Column(db.Integer, db.ForeignKey('test_records.id'), nullable=False)

    parameter_name = db.Column(db.String(50), nullable=False)  # Rp02, Rm, E, etc.
    value = db.Column(db.Float)
    uncertainty = db.Column(db.Float)  # Expanded uncertainty (k=2)
    unit = db.Column(db.String(20))

    calculation_method = db.Column(db.String(100))
    is_valid = db.Column(db.Boolean, default=True)
    validity_notes = db.Column(db.Text)

    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
    calculated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self) -> str:
        return f'<AnalysisResult {self.parameter_name}={self.value}>'


class AuditLog(db.Model):
    """Audit log for ISO 17025 compliance.

    Records all data modifications with user, timestamp, and reason.
    """
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    ip_address = db.Column(db.String(45))

    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE, VIEW
    table_name = db.Column(db.String(50))
    record_id = db.Column(db.Integer)

    old_values = db.Column(db.JSON)
    new_values = db.Column(db.JSON)
    reason = db.Column(db.Text)

    # Relationship
    user = db.relationship('User', backref='audit_logs')

    def __repr__(self) -> str:
        return f'<AuditLog {self.action} {self.table_name}:{self.record_id}>'
