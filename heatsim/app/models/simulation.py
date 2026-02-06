"""Simulation models for heat treatment simulations.

Uses the 'materials' bind key to store in PostgreSQL alongside material data.
"""
from datetime import datetime
from typing import Optional
import json

from app.extensions import db


# Status constants
STATUS_DRAFT = 'draft'
STATUS_READY = 'ready'
STATUS_RUNNING = 'running'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'

STATUSES = [STATUS_DRAFT, STATUS_READY, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED]

# Geometry type constants
GEOMETRY_CYLINDER = 'cylinder'
GEOMETRY_PLATE = 'plate'
GEOMETRY_RING = 'ring'

GEOMETRY_TYPES = [GEOMETRY_CYLINDER, GEOMETRY_PLATE, GEOMETRY_RING]

# Process type constants
PROCESS_QUENCH_WATER = 'quench_water'
PROCESS_QUENCH_OIL = 'quench_oil'
PROCESS_QUENCH_POLYMER = 'quench_polymer'
PROCESS_QUENCH_AIR = 'quench_air'
PROCESS_TEMPERING = 'tempering'
PROCESS_NORMALIZING = 'normalizing'
PROCESS_STRESS_RELIEF = 'stress_relief'
PROCESS_CUSTOM = 'custom'

PROCESS_TYPES = [
    PROCESS_QUENCH_WATER, PROCESS_QUENCH_OIL, PROCESS_QUENCH_POLYMER,
    PROCESS_QUENCH_AIR, PROCESS_TEMPERING, PROCESS_NORMALIZING,
    PROCESS_STRESS_RELIEF, PROCESS_CUSTOM
]

PROCESS_LABELS = {
    PROCESS_QUENCH_WATER: 'Water Quench',
    PROCESS_QUENCH_OIL: 'Oil Quench',
    PROCESS_QUENCH_POLYMER: 'Polymer Quench',
    PROCESS_QUENCH_AIR: 'Air Cool',
    PROCESS_TEMPERING: 'Tempering',
    PROCESS_NORMALIZING: 'Normalizing',
    PROCESS_STRESS_RELIEF: 'Stress Relief',
    PROCESS_CUSTOM: 'Custom',
}

# Default HTC values for quench media (W/m²K)
DEFAULT_HTC = {
    PROCESS_QUENCH_WATER: 3000,
    PROCESS_QUENCH_OIL: 800,
    PROCESS_QUENCH_POLYMER: 1200,
    PROCESS_QUENCH_AIR: 50,
    PROCESS_TEMPERING: 25,
    PROCESS_NORMALIZING: 30,
    PROCESS_STRESS_RELIEF: 20,
    PROCESS_CUSTOM: 100,
}


class Simulation(db.Model):
    """Heat treatment simulation job.

    Stores simulation configuration including geometry, material,
    process parameters, and boundary conditions.
    """
    __tablename__ = 'simulations'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)

    # Foreign key to steel grade
    steel_grade_id = db.Column(db.Integer, db.ForeignKey('steel_grades.id'), nullable=False)

    # Owner (note: users table is in default bind, so no FK constraint)
    user_id = db.Column(db.Integer)

    # Status
    status = db.Column(db.Text, default=STATUS_DRAFT)

    # Geometry configuration
    geometry_type = db.Column(db.Text, nullable=False, default=GEOMETRY_CYLINDER)
    geometry_config = db.Column(db.Text)  # JSON

    # Process configuration
    process_type = db.Column(db.Text, nullable=False, default=PROCESS_QUENCH_WATER)
    initial_temperature = db.Column(db.Float, default=850.0)
    ambient_temperature = db.Column(db.Float, default=25.0)

    # Boundary conditions (JSON)
    boundary_conditions = db.Column(db.Text)

    # Solver settings (JSON)
    solver_config = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    # Error message if failed
    error_message = db.Column(db.Text)

    # Relationships
    steel_grade = db.relationship('SteelGrade', backref='simulations')
    results = db.relationship('SimulationResult', backref='simulation',
                              lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_simulations_user', 'user_id'),
        db.Index('ix_simulations_status', 'status'),
    )

    @property
    def geometry_dict(self) -> dict:
        """Parse geometry config JSON."""
        try:
            return json.loads(self.geometry_config) if self.geometry_config else {}
        except json.JSONDecodeError:
            return {}

    def set_geometry(self, config: dict) -> None:
        """Set geometry config from dict."""
        self.geometry_config = json.dumps(config)

    @property
    def bc_dict(self) -> dict:
        """Parse boundary conditions JSON."""
        try:
            return json.loads(self.boundary_conditions) if self.boundary_conditions else {}
        except json.JSONDecodeError:
            return {}

    def set_boundary_conditions(self, bc: dict) -> None:
        """Set boundary conditions from dict."""
        self.boundary_conditions = json.dumps(bc)

    @property
    def solver_dict(self) -> dict:
        """Parse solver config JSON."""
        try:
            return json.loads(self.solver_config) if self.solver_config else {}
        except json.JSONDecodeError:
            return {}

    def set_solver_config(self, config: dict) -> None:
        """Set solver config from dict."""
        self.solver_config = json.dumps(config)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate simulation runtime in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def process_label(self) -> str:
        """Human-readable process name."""
        return PROCESS_LABELS.get(self.process_type, self.process_type)

    @property
    def geometry_label(self) -> str:
        """Human-readable geometry name."""
        return self.geometry_type.title()

    @property
    def status_badge_class(self) -> str:
        """Bootstrap badge class for status."""
        classes = {
            STATUS_DRAFT: 'bg-secondary',
            STATUS_READY: 'bg-info',
            STATUS_RUNNING: 'bg-warning',
            STATUS_COMPLETED: 'bg-success',
            STATUS_FAILED: 'bg-danger',
        }
        return classes.get(self.status, 'bg-secondary')

    def __repr__(self) -> str:
        return f'<Simulation {self.id}: {self.name}>'


class SimulationResult(db.Model):
    """Simulation result data.

    Stores time-series temperature data and phase fractions at
    monitoring points (center, surface, quarter-thickness, etc.).
    """
    __tablename__ = 'simulation_results'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    simulation_id = db.Column(db.Integer, db.ForeignKey('simulations.id'), nullable=False)

    # Result type: 'cooling_curve', 'temperature_profile', 'phase_fraction', 'cooling_rate'
    result_type = db.Column(db.Text, nullable=False)

    # Location identifier: 'center', 'surface', 'quarter', 'all'
    location = db.Column(db.Text)

    # Time-series data (JSON arrays)
    time_data = db.Column(db.Text)
    value_data = db.Column(db.Text)

    # Summary statistics
    cooling_rate_max = db.Column(db.Float)
    cooling_rate_800_500 = db.Column(db.Float)
    t_800_500 = db.Column(db.Float)

    # Phase transformation results (JSON)
    phase_fractions = db.Column(db.Text)

    # Stored plot image (PNG bytes)
    plot_image = db.Column(db.LargeBinary)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_simulation_results_sim', 'simulation_id'),
    )

    @property
    def time_array(self) -> list:
        """Parse time data JSON to list."""
        try:
            return json.loads(self.time_data) if self.time_data else []
        except json.JSONDecodeError:
            return []

    @property
    def value_array(self) -> list:
        """Parse value data JSON to list."""
        try:
            return json.loads(self.value_data) if self.value_data else []
        except json.JSONDecodeError:
            return []

    def set_time_data(self, data: list) -> None:
        """Set time data from list."""
        self.time_data = json.dumps(data)

    def set_value_data(self, data: list) -> None:
        """Set value data from list."""
        self.value_data = json.dumps(data)

    @property
    def phases_dict(self) -> dict:
        """Parse phase fractions JSON."""
        try:
            return json.loads(self.phase_fractions) if self.phase_fractions else {}
        except json.JSONDecodeError:
            return {}

    def set_phase_fractions(self, phases: dict) -> None:
        """Set phase fractions from dict."""
        self.phase_fractions = json.dumps(phases)

    @property
    def has_plot(self) -> bool:
        """Check if plot image is stored."""
        return self.plot_image is not None

    @property
    def result_label(self) -> str:
        """Human-readable result type."""
        labels = {
            'cooling_curve': 'Cooling Curve',
            'temperature_profile': 'Temperature Profile',
            'phase_fraction': 'Phase Fractions',
            'cooling_rate': 'Cooling Rate',
        }
        return labels.get(self.result_type, self.result_type)

    def __repr__(self) -> str:
        return f'<SimulationResult {self.id}: {self.result_type} at {self.location}>'
