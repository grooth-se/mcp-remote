"""Database models."""
from .user import (
    User,
    ROLE_OPERATOR, ROLE_ENGINEER, ROLE_APPROVER, ROLE_ADMIN,
    ROLES, ROLE_LABELS,
    admin_required, approver_required, engineer_required
)
from .test_record import TestRecord, AnalysisResult, AuditLog
from .certificate import Certificate
from .report_approval import (
    ReportApproval,
    STATUS_DRAFT, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_PUBLISHED,
    APPROVAL_STATUSES, STATUS_LABELS as APPROVAL_STATUS_LABELS, STATUS_COLORS
)
from .test_data import RawTestData, TestPhoto, ReportFile

__all__ = [
    # User
    'User',
    'ROLE_OPERATOR', 'ROLE_ENGINEER', 'ROLE_APPROVER', 'ROLE_ADMIN',
    'ROLES', 'ROLE_LABELS',
    'admin_required', 'approver_required', 'engineer_required',
    # Test records
    'TestRecord', 'AnalysisResult', 'AuditLog', 'Certificate',
    # Test data storage
    'RawTestData', 'TestPhoto', 'ReportFile',
    # Report approval
    'ReportApproval',
    'STATUS_DRAFT', 'STATUS_PENDING', 'STATUS_APPROVED', 'STATUS_REJECTED', 'STATUS_PUBLISHED',
    'APPROVAL_STATUSES', 'APPROVAL_STATUS_LABELS', 'STATUS_COLORS',
]
