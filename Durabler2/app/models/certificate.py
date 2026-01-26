"""Certificate model for test certificate register."""
from datetime import datetime
from app.extensions import db


class Certificate(db.Model):
    """
    Certificate register model.

    Certificate number format: DUR-YYYY-NNNN where NNNN starts at 1001 per year.

    Attributes
    ----------
    id : int
        Primary key
    year : int
        Certificate year (e.g., 2026)
    cert_id : int
        Sequential ID within year (starts at 1001)
    revision : int
        Revision number (default 1)
    """
    __tablename__ = 'certificates'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    cert_id = db.Column(db.Integer, nullable=False)
    revision = db.Column(db.Integer, default=1)

    # Certificate date
    cert_date = db.Column(db.Date)

    # Test information
    test_project = db.Column(db.String(100))
    project_name = db.Column(db.String(100))
    test_standard = db.Column(db.String(50))

    # Customer information
    customer = db.Column(db.String(100))
    customer_order = db.Column(db.String(50))

    # Product/Specimen information
    product = db.Column(db.String(100))
    product_sn = db.Column(db.String(50))
    material = db.Column(db.String(100))
    specimen_id = db.Column(db.String(50))
    location_orientation = db.Column(db.String(100))
    temperature = db.Column(db.String(20))

    # Comment
    comment = db.Column(db.Text)

    # Status flags
    reported = db.Column(db.Boolean, default=False)
    invoiced = db.Column(db.Boolean, default=False)

    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationship to test records
    test_records = db.relationship('TestRecord', backref='certificate', lazy='dynamic',
                                   foreign_keys='TestRecord.certificate_id')

    # Unique constraint on year, cert_id, revision
    __table_args__ = (
        db.UniqueConstraint('year', 'cert_id', 'revision', name='uq_cert_year_id_rev'),
    )

    @property
    def certificate_number(self) -> str:
        """Generate certificate number string (DUR-YYYY-NNNN)."""
        return f"DUR-{self.year}-{self.cert_id}"

    @property
    def certificate_number_with_rev(self) -> str:
        """Generate certificate number with revision."""
        if self.revision > 1:
            return f"DUR-{self.year}-{self.cert_id} Rev.{self.revision}"
        return self.certificate_number

    @classmethod
    def get_next_cert_id(cls, year: int = None) -> int:
        """
        Get next available certificate ID for the year.

        Parameters
        ----------
        year : int, optional
            Year for certificate. Defaults to current year.

        Returns
        -------
        int
            Next available certificate ID (starts at 1001)
        """
        if year is None:
            year = datetime.now().year

        max_id = db.session.query(db.func.max(cls.cert_id))\
            .filter(cls.year == year).scalar()

        if max_id is None:
            return 1001
        return max_id + 1

    @classmethod
    def parse_certificate_number(cls, cert_num: str) -> tuple:
        """
        Parse certificate number string.

        Parameters
        ----------
        cert_num : str
            Certificate number like "DUR-2026-1001" or "DUR-2026-1001 Rev.2"

        Returns
        -------
        tuple
            (year, cert_id, revision) or (None, None, None) if invalid
        """
        import re
        match = re.match(r'DUR-(\d{4})-(\d+)(?:\s*Rev\.?(\d+))?', cert_num, re.IGNORECASE)
        if match:
            year = int(match.group(1))
            cert_id = int(match.group(2))
            revision = int(match.group(3)) if match.group(3) else None
            return year, cert_id, revision
        return None, None, None

    @classmethod
    def get_by_number(cls, cert_num: str):
        """Get certificate by number string."""
        year, cert_id, revision = cls.parse_certificate_number(cert_num)
        if year and cert_id:
            query = cls.query.filter_by(year=year, cert_id=cert_id)
            if revision:
                return query.filter_by(revision=revision).first()
            return query.order_by(cls.revision.desc()).first()
        return None

    @classmethod
    def get_years_list(cls) -> list:
        """Get list of years that have certificates."""
        result = db.session.query(cls.year).distinct().order_by(cls.year.desc()).all()
        return [r[0] for r in result]

    def __repr__(self) -> str:
        return f'<Certificate {self.certificate_number}>'
