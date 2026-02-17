from app.extensions import db
from app.models.log import AccessLog, AuditLog


def log_access(user_id, app_id, action, ip_address=None, details=None):
    """Log an access event."""
    entry = AccessLog(
        user_id=user_id,
        app_id=app_id,
        action=action,
        ip_address=ip_address,
        details=details,
    )
    db.session.add(entry)
    db.session.commit()


def log_audit(admin_id, action, target_type=None, target_id=None, old_value=None, new_value=None):
    """Log an admin audit event."""
    entry = AuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=old_value,
        new_value=new_value,
    )
    db.session.add(entry)
    db.session.commit()
