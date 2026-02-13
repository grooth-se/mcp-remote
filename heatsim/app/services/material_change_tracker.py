"""Service for tracking material property changes."""
import json

from app.extensions import db
from app.models.material_changelog import MaterialChangeLog


class MaterialChangeTracker:
    """Tracks changes to material entities for audit/lineage purposes."""

    @staticmethod
    def _get_user_info():
        """Get current user info from request context."""
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                return current_user.id, current_user.username
        except RuntimeError:
            pass
        return None, 'system'

    @classmethod
    def log_create(cls, entity_type, entity, steel_grade_id):
        """Log creation of a material entity."""
        user_id, username = cls._get_user_info()
        entry = MaterialChangeLog(
            entity_type=entity_type,
            entity_id=entity.id,
            steel_grade_id=steel_grade_id,
            action='create',
            new_value=json.dumps(repr(entity)),
            changed_by_id=user_id,
            changed_by_username=username,
        )
        db.session.add(entry)

    @classmethod
    def log_update(cls, entity_type, entity_id, steel_grade_id, changes):
        """Log field-level changes.

        Parameters
        ----------
        changes : dict
            {field_name: (old_value, new_value)}
        """
        user_id, username = cls._get_user_info()
        for field_name, (old_val, new_val) in changes.items():
            entry = MaterialChangeLog(
                entity_type=entity_type,
                entity_id=entity_id,
                steel_grade_id=steel_grade_id,
                action='update',
                field_name=field_name,
                old_value=json.dumps(old_val) if old_val is not None else None,
                new_value=json.dumps(new_val) if new_val is not None else None,
                changed_by_id=user_id,
                changed_by_username=username,
            )
            db.session.add(entry)

    @classmethod
    def log_delete(cls, entity_type, entity_id, steel_grade_id, name=None):
        """Log deletion of a material entity."""
        user_id, username = cls._get_user_info()
        entry = MaterialChangeLog(
            entity_type=entity_type,
            entity_id=entity_id,
            steel_grade_id=steel_grade_id,
            action='delete',
            old_value=json.dumps(name) if name else None,
            changed_by_id=user_id,
            changed_by_username=username,
        )
        db.session.add(entry)

    @staticmethod
    def detect_changes(entity, field_values):
        """Detect which fields changed.

        Parameters
        ----------
        entity : db.Model instance
            The entity to check
        field_values : dict
            {field_name: new_value} from form data

        Returns
        -------
        dict
            {field_name: (old_value, new_value)} for changed fields
        """
        changes = {}
        for field, new_val in field_values.items():
            old_val = getattr(entity, field, None)
            if old_val != new_val:
                changes[field] = (old_val, new_val)
        return changes
