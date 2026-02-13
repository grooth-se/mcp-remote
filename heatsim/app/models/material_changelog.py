"""Material change log model for tracking property changes."""
import json
from datetime import datetime

from app.extensions import db


class MaterialChangeLog(db.Model):
    """Tracks changes to material data (steel grades, properties, etc.)."""
    __tablename__ = 'material_change_logs'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.Text, nullable=False)  # steel_grade, material_property, phase_diagram, composition, phase_property
    entity_id = db.Column(db.Integer, nullable=False)
    steel_grade_id = db.Column(db.Integer, nullable=False)  # Denormalized
    action = db.Column(db.Text, nullable=False)  # create, update, delete
    field_name = db.Column(db.Text)  # Null for create/delete
    old_value = db.Column(db.Text)  # JSON-encoded
    new_value = db.Column(db.Text)  # JSON-encoded
    changed_by_id = db.Column(db.Integer)  # No FK across binds
    changed_by_username = db.Column(db.Text)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_material_changelog_entity', 'entity_type', 'entity_id'),
        db.Index('ix_material_changelog_grade', 'steel_grade_id'),
        db.Index('ix_material_changelog_time', 'changed_at'),
    )

    @property
    def action_badge(self):
        return {'create': 'success', 'update': 'info', 'delete': 'danger'}.get(self.action, 'secondary')

    @property
    def old_value_parsed(self):
        if self.old_value:
            try:
                return json.loads(self.old_value)
            except json.JSONDecodeError:
                return self.old_value
        return None

    @property
    def new_value_parsed(self):
        if self.new_value:
            try:
                return json.loads(self.new_value)
            except json.JSONDecodeError:
                return self.new_value
        return None
