"""Simulation snapshot model for immutable run history."""
import json
from datetime import datetime

from app.extensions import db


class SimulationSnapshot(db.Model):
    """Immutable snapshot of simulation inputs captured at run time."""
    __tablename__ = 'simulation_snapshots'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    simulation_id = db.Column(db.Integer, db.ForeignKey('simulations.id'), nullable=False)
    version = db.Column(db.Integer, nullable=False)

    # Frozen simulation config
    geometry_type = db.Column(db.Text, nullable=False)
    geometry_config = db.Column(db.Text)
    heat_treatment_config = db.Column(db.Text)
    solver_config = db.Column(db.Text)
    boundary_conditions = db.Column(db.Text)

    # Frozen material data
    steel_grade_designation = db.Column(db.Text, nullable=False)
    steel_grade_data_source = db.Column(db.Text)
    material_properties_snapshot = db.Column(db.Text)
    phase_diagram_snapshot = db.Column(db.Text)
    composition_snapshot = db.Column(db.Text)
    phase_properties_snapshot = db.Column(db.Text)

    # CAD data
    cad_filename = db.Column(db.Text)
    cad_analysis = db.Column(db.Text)
    cad_equivalent_type = db.Column(db.Text)

    # Run metadata
    user_id = db.Column(db.Integer)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.Text)
    error_message = db.Column(db.Text)
    duration_seconds = db.Column(db.Float)

    # Summary results (denormalized)
    t_800_500 = db.Column(db.Float)
    predicted_hardness_surface = db.Column(db.Float)
    predicted_hardness_center = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    simulation = db.relationship('Simulation', backref=db.backref(
        'snapshots', lazy='dynamic', order_by='SimulationSnapshot.version.desc()',
        cascade='all, delete-orphan',
    ))

    __table_args__ = (
        db.UniqueConstraint('simulation_id', 'version', name='uq_sim_version'),
        db.Index('ix_snapshots_simulation', 'simulation_id'),
    )

    @property
    def geometry_dict(self):
        try:
            return json.loads(self.geometry_config) if self.geometry_config else {}
        except json.JSONDecodeError:
            return {}

    @property
    def ht_config(self):
        try:
            return json.loads(self.heat_treatment_config) if self.heat_treatment_config else {}
        except json.JSONDecodeError:
            return {}

    @property
    def solver_dict(self):
        try:
            return json.loads(self.solver_config) if self.solver_config else {}
        except json.JSONDecodeError:
            return {}

    @property
    def material_props_dict(self):
        try:
            return json.loads(self.material_properties_snapshot) if self.material_properties_snapshot else []
        except json.JSONDecodeError:
            return []

    @property
    def phase_diagram_dict(self):
        try:
            return json.loads(self.phase_diagram_snapshot) if self.phase_diagram_snapshot else None
        except json.JSONDecodeError:
            return None

    @property
    def composition_dict(self):
        try:
            return json.loads(self.composition_snapshot) if self.composition_snapshot else None
        except json.JSONDecodeError:
            return None

    @property
    def phase_props_dict(self):
        try:
            return json.loads(self.phase_properties_snapshot) if self.phase_properties_snapshot else []
        except json.JSONDecodeError:
            return []

    @property
    def display_label(self):
        return f"v{self.version}"

    def __repr__(self):
        return f'<SimulationSnapshot sim={self.simulation_id} v{self.version}>'
