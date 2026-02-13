"""System settings key-value store."""
from datetime import datetime

from app.extensions import db


class SystemSetting(db.Model):
    """Key-value settings store with typed values."""
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(10), default='string')  # string, int, float, bool
    description = db.Column(db.String(300), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(80), nullable=True)

    @classmethod
    def get(cls, key, default=None):
        """Get a setting value with type casting."""
        setting = cls.query.filter_by(key=key).first()
        if setting is None or setting.value is None:
            return default

        try:
            if setting.value_type == 'int':
                return int(setting.value)
            elif setting.value_type == 'float':
                return float(setting.value)
            elif setting.value_type == 'bool':
                return setting.value.lower() in ('true', '1', 'yes')
            return setting.value
        except (ValueError, AttributeError):
            return default

    @classmethod
    def set(cls, key, value, value_type='string', description=None):
        """Set a setting value."""
        from flask_login import current_user

        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            setting = cls(key=key, value_type=value_type, description=description)
            db.session.add(setting)

        setting.value = str(value) if value is not None else None
        if value_type:
            setting.value_type = value_type
        if description:
            setting.description = description

        if current_user and hasattr(current_user, 'username') and current_user.is_authenticated:
            setting.updated_by = current_user.username

        db.session.commit()
        return setting

    @classmethod
    def get_all(cls):
        """Get all settings as a dict."""
        settings = cls.query.all()
        return {s.key: cls.get(s.key) for s in settings}
