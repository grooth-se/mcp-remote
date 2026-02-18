"""Report approval model for workflow tracking.

Certificate-centric workflow:
- Each Certificate has one ReportApproval record
- Word document is saved on server and tracked
- Approval workflow: DRAFT -> PENDING_REVIEW -> APPROVED/REJECTED -> PUBLISHED
"""
from datetime import datetime
from app.extensions import db


# Approval status constants
STATUS_DRAFT = 'DRAFT'
STATUS_PENDING = 'PENDING_REVIEW'
STATUS_APPROVED = 'APPROVED'
STATUS_REJECTED = 'REJECTED'
STATUS_PUBLISHED = 'PUBLISHED'

APPROVAL_STATUSES = [STATUS_DRAFT, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_PUBLISHED]

STATUS_LABELS = {
    STATUS_DRAFT: 'Draft',
    STATUS_PENDING: 'Pending Review',
    STATUS_APPROVED: 'Approved',
    STATUS_REJECTED: 'Rejected',
    STATUS_PUBLISHED: 'Published',
}

STATUS_COLORS = {
    STATUS_DRAFT: 'secondary',
    STATUS_PENDING: 'warning',
    STATUS_APPROVED: 'success',
    STATUS_REJECTED: 'danger',
    STATUS_PUBLISHED: 'primary',
}


class ReportApproval(db.Model):
    """
    Report approval workflow tracking - linked to Certificate.

    Each certificate has one approval workflow that covers all its test records.
    The Word document is saved on the server and tracked through this model.

    Attributes
    ----------
    id : int
        Primary key
    certificate_id : int
        Foreign key to certificates (one approval per certificate)
    certificate_number : str
        Certificate number (cached for quick lookup)
    status : str
        Approval status: DRAFT, PENDING_REVIEW, APPROVED, REJECTED, PUBLISHED
    """
    __tablename__ = 'report_approvals'

    id = db.Column(db.Integer, primary_key=True)

    # Link to Certificate (one approval per certificate)
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'),
                               nullable=True, unique=True, index=True)
    certificate_number = db.Column(db.String(50), index=True)

    # Legacy: keep test_record_id for backwards compatibility during migration
    test_record_id = db.Column(db.Integer, db.ForeignKey('test_records.id'),
                               nullable=True, unique=True, index=True)

    status = db.Column(db.String(20), default=STATUS_DRAFT, index=True)

    # Creation/submission
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    submitted_at = db.Column(db.DateTime)

    # Review/approval
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_comments = db.Column(db.Text)  # For rejections

    # Report files
    word_report_path = db.Column(db.String(255))  # Draft Word document (saved on server)
    signed_pdf_path = db.Column(db.String(255))   # Final PDF
    pdf_hash = db.Column(db.String(64))           # SHA-256 for integrity
    signature_timestamp = db.Column(db.DateTime)

    # Relationships
    cert = db.relationship('Certificate', backref=db.backref('approval', uselist=False))
    test_record = db.relationship('TestRecord', backref=db.backref('approval', uselist=False))
    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref='reports_created')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id],
                                   backref='reports_submitted')
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id],
                                  backref='reports_reviewed')

    @property
    def status_label(self) -> str:
        """Get human-readable status label."""
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self) -> str:
        """Get Bootstrap color class for status badge."""
        return STATUS_COLORS.get(self.status, 'secondary')

    @property
    def can_edit(self) -> bool:
        """Check if report can be edited."""
        return self.status in [STATUS_DRAFT, STATUS_REJECTED]

    @property
    def can_submit(self) -> bool:
        """Check if report can be submitted for approval."""
        return self.status in [STATUS_DRAFT, STATUS_REJECTED]

    @property
    def can_review(self) -> bool:
        """Check if report can be reviewed."""
        return self.status == STATUS_PENDING

    @property
    def can_download_signed(self) -> bool:
        """Check if signed PDF is available for download."""
        return self.status == STATUS_PUBLISHED and self.signed_pdf_path is not None

    def submit_for_approval(self, user) -> None:
        """Submit report for approval."""
        self.status = STATUS_PENDING
        self.submitted_by_id = user.id
        self.submitted_at = datetime.utcnow()
        # Clear any previous rejection
        self.review_comments = None

    def approve(self, user) -> None:
        """Approve the report."""
        self.status = STATUS_APPROVED
        self.reviewed_by_id = user.id
        self.reviewed_at = datetime.utcnow()

    def reject(self, user, comments: str) -> None:
        """Reject the report with comments."""
        self.status = STATUS_REJECTED
        self.reviewed_by_id = user.id
        self.reviewed_at = datetime.utcnow()
        self.review_comments = comments

    def publish(self, pdf_path: str, pdf_hash: str) -> None:
        """Mark as published with signed PDF."""
        self.status = STATUS_PUBLISHED
        self.signed_pdf_path = pdf_path
        self.pdf_hash = pdf_hash
        self.signature_timestamp = datetime.utcnow()

    @classmethod
    def get_or_create_for_certificate(cls, certificate, user):
        """Get existing approval or create new one for a certificate."""
        approval = cls.query.filter_by(certificate_id=certificate.id).first()
        if not approval:
            approval = cls(
                certificate_id=certificate.id,
                certificate_number=certificate.certificate_number_with_rev,
                created_by_id=user.id,
                status=STATUS_DRAFT
            )
            db.session.add(approval)
        return approval

    @classmethod
    def get_or_create(cls, test_record, user):
        """Legacy: Get existing approval or create new one for a test record."""
        approval = cls.query.filter_by(test_record_id=test_record.id).first()
        if not approval:
            approval = cls(
                test_record_id=test_record.id,
                certificate_number=test_record.certificate_number,
                created_by_id=user.id,
                status=STATUS_DRAFT
            )
            db.session.add(approval)
        return approval

    @classmethod
    def get_pending_count(cls) -> int:
        """Get count of reports pending approval."""
        return cls.query.filter_by(status=STATUS_PENDING).count()

    def set_word_report(self, path: str) -> None:
        """Set the Word report path (saved on server)."""
        self.word_report_path = path

    def __repr__(self) -> str:
        return f'<ReportApproval {self.certificate_number} [{self.status}]>'
