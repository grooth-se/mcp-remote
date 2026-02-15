"""Weld project models for multi-pass welding simulation.

Uses the 'materials' bind key to store in PostgreSQL alongside material data.
Supports GTAW, MIG/MAG, SAW welding with up to 6 layers x 12 strings per layer.
"""
from datetime import datetime
from typing import Optional, List
import json

from app.extensions import db


# Project status constants
STATUS_DRAFT = 'draft'
STATUS_CONFIGURED = 'configured'
STATUS_RUNNING = 'running'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
STATUS_CANCELLED = 'cancelled'

PROJECT_STATUSES = [STATUS_DRAFT, STATUS_CONFIGURED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED]

# Welding process types
PROCESS_GTAW = 'gtaw'
PROCESS_MIG_MAG = 'mig_mag'
PROCESS_SAW = 'saw'
PROCESS_SMAW = 'smaw'

WELD_PROCESS_TYPES = [PROCESS_GTAW, PROCESS_MIG_MAG, PROCESS_SAW, PROCESS_SMAW]

WELD_PROCESS_LABELS = {
    PROCESS_GTAW: 'GTAW (TIG)',
    PROCESS_MIG_MAG: 'MIG/MAG',
    PROCESS_SAW: 'SAW (Submerged Arc)',
    PROCESS_SMAW: 'SMAW (Stick)',
}

# String status constants
STRING_PENDING = 'pending'
STRING_RUNNING = 'running'
STRING_COMPLETED = 'completed'
STRING_FAILED = 'failed'

STRING_STATUSES = [STRING_PENDING, STRING_RUNNING, STRING_COMPLETED, STRING_FAILED]

# Initial temperature modes
TEMP_MODE_CALCULATED = 'calculated'
TEMP_MODE_MANUAL = 'manual'
TEMP_MODE_SOLIDIFICATION = 'solidification'

TEMP_MODES = [TEMP_MODE_CALCULATED, TEMP_MODE_MANUAL, TEMP_MODE_SOLIDIFICATION]

# Result types
RESULT_THERMAL_CYCLE = 'thermal_cycle'
RESULT_TEMPERATURE_FIELD = 'temperature_field'
RESULT_COOLING_RATE = 'cooling_rate'
RESULT_LINE_PROFILE = 'line_profile'

RESULT_HAZ_PROFILE = 'haz_profile'
RESULT_GOLDAK_FIELD = 'goldak_field'
RESULT_GOLDAK_COMPARISON = 'goldak_comparison'

RESULT_TYPES = [RESULT_THERMAL_CYCLE, RESULT_TEMPERATURE_FIELD, RESULT_COOLING_RATE,
                RESULT_LINE_PROFILE, RESULT_HAZ_PROFILE,
                RESULT_GOLDAK_FIELD, RESULT_GOLDAK_COMPARISON]


class WeldProject(db.Model):
    """Multi-pass weld simulation project.

    Stores project configuration including CAD geometry, material selection,
    welding process parameters, and overall simulation status.
    """
    __tablename__ = 'weld_projects'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)

    # Owner (note: users table is in default bind, so no FK constraint)
    user_id = db.Column(db.Integer)

    # Material selection
    steel_grade_id = db.Column(db.Integer, db.ForeignKey('steel_grades.id'))

    # CAD geometry
    cad_filename = db.Column(db.Text)  # Original filename
    cad_file = db.Column(db.LargeBinary)  # STEP/IGES file content
    cad_format = db.Column(db.Text)  # 'step', 'iges', 'stl'
    string_bodies = db.Column(db.Text)  # JSON: [{id, name, layer, position}]

    # Welding process
    process_type = db.Column(db.Text, default=PROCESS_GTAW)
    preheat_temperature = db.Column(db.Float, default=20.0)  # C
    interpass_temperature = db.Column(db.Float, default=150.0)  # C max
    interpass_time_default = db.Column(db.Float, default=60.0)  # seconds default

    # Default welding parameters (can be overridden per string)
    default_heat_input = db.Column(db.Float, default=1.5)  # kJ/mm
    default_travel_speed = db.Column(db.Float, default=5.0)  # mm/s
    default_solidification_temp = db.Column(db.Float, default=1500.0)  # C

    # COMSOL model reference
    comsol_model_path = db.Column(db.Text)  # Path to .mph file

    # Status tracking
    status = db.Column(db.Text, default=STATUS_DRAFT)
    current_string = db.Column(db.Integer, default=0)
    total_strings = db.Column(db.Integer, default=0)
    progress_percent = db.Column(db.Float, default=0.0)
    progress_message = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    # Error tracking
    error_message = db.Column(db.Text)

    # Relationships
    steel_grade = db.relationship('SteelGrade', backref='weld_projects')
    strings = db.relationship('WeldString', backref='project',
                              lazy='dynamic', cascade='all, delete-orphan',
                              order_by='WeldString.string_number')
    results = db.relationship('WeldResult', backref='project',
                              lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_weld_projects_user', 'user_id'),
        db.Index('ix_weld_projects_status', 'status'),
    )

    @property
    def string_bodies_list(self) -> List[dict]:
        """Parse string bodies JSON."""
        try:
            return json.loads(self.string_bodies) if self.string_bodies else []
        except json.JSONDecodeError:
            return []

    def set_string_bodies(self, bodies: List[dict]) -> None:
        """Set string bodies from list."""
        self.string_bodies = json.dumps(bodies)

    @property
    def process_label(self) -> str:
        """Human-readable process name."""
        return WELD_PROCESS_LABELS.get(self.process_type, self.process_type)

    @property
    def status_badge_class(self) -> str:
        """Bootstrap badge class for status."""
        classes = {
            STATUS_DRAFT: 'bg-secondary',
            STATUS_CONFIGURED: 'bg-info',
            STATUS_RUNNING: 'bg-warning',
            STATUS_COMPLETED: 'bg-success',
            STATUS_FAILED: 'bg-danger',
            STATUS_CANCELLED: 'bg-dark',
        }
        return classes.get(self.status, 'bg-secondary')

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate simulation runtime in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def can_run(self) -> bool:
        """Check if project can be run."""
        return (self.status in [STATUS_CONFIGURED, STATUS_FAILED, STATUS_CANCELLED] and
                self.total_strings > 0)

    @property
    def is_running(self) -> bool:
        """Check if simulation is currently running."""
        return self.status == STATUS_RUNNING

    @property
    def completed_strings_count(self) -> int:
        """Count of completed strings."""
        return self.strings.filter_by(status=STRING_COMPLETED).count()

    def __repr__(self) -> str:
        return f'<WeldProject {self.id}: {self.name}>'


class WeldString(db.Model):
    """Individual weld string (bead) in a multi-pass weld.

    Represents a single weld pass with its sequence, parameters, and results.
    """
    __tablename__ = 'weld_strings'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('weld_projects.id'), nullable=False)

    # Identity and sequence
    string_number = db.Column(db.Integer, nullable=False)  # Execution order (1, 2, 3...)
    body_name = db.Column(db.Text)  # CAD body identifier
    layer = db.Column(db.Integer, default=1)  # Layer number (1-6)
    position_in_layer = db.Column(db.Integer, default=1)  # Position within layer

    # String name (optional, for user reference)
    name = db.Column(db.Text)

    # Welding parameters
    heat_input = db.Column(db.Float)  # kJ/mm (if null, use project default)
    travel_speed = db.Column(db.Float)  # mm/s (if null, use project default)
    interpass_time = db.Column(db.Float)  # seconds before next string

    # Initial conditions
    initial_temp_mode = db.Column(db.Text, default=TEMP_MODE_SOLIDIFICATION)
    initial_temperature = db.Column(db.Float)  # C (if manual mode)
    solidification_temp = db.Column(db.Float)  # C (default from project)

    # Calculated initial temperature (filled during simulation)
    calculated_initial_temp = db.Column(db.Float)

    # Simulation timing
    simulation_start_time = db.Column(db.Float, default=0.0)  # Global time when this string starts
    simulation_duration = db.Column(db.Float, default=120.0)  # seconds to simulate

    # Status tracking
    status = db.Column(db.Text, default=STRING_PENDING)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    # Relationships
    results = db.relationship('WeldResult', backref='string',
                              lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_weld_strings_project', 'project_id'),
        db.Index('ix_weld_strings_number', 'project_id', 'string_number'),
    )

    @property
    def effective_heat_input(self) -> float:
        """Get heat input (string value or project default)."""
        if self.heat_input is not None:
            return self.heat_input
        return self.project.default_heat_input if self.project else 1.5

    @property
    def effective_travel_speed(self) -> float:
        """Get travel speed (string value or project default)."""
        if self.travel_speed is not None:
            return self.travel_speed
        return self.project.default_travel_speed if self.project else 5.0

    @property
    def effective_solidification_temp(self) -> float:
        """Get solidification temperature (string value or project default)."""
        if self.solidification_temp is not None:
            return self.solidification_temp
        return self.project.default_solidification_temp if self.project else 1500.0

    @property
    def effective_interpass_time(self) -> float:
        """Get interpass time (string value or project default)."""
        if self.interpass_time is not None:
            return self.interpass_time
        return self.project.interpass_time_default if self.project else 60.0

    @property
    def display_name(self) -> str:
        """User-friendly display name."""
        if self.name:
            return self.name
        return f"String {self.string_number} (L{self.layer}-P{self.position_in_layer})"

    @property
    def status_badge_class(self) -> str:
        """Bootstrap badge class for status."""
        classes = {
            STRING_PENDING: 'bg-secondary',
            STRING_RUNNING: 'bg-warning',
            STRING_COMPLETED: 'bg-success',
            STRING_FAILED: 'bg-danger',
        }
        return classes.get(self.status, 'bg-secondary')

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate simulation runtime in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def __repr__(self) -> str:
        return f'<WeldString {self.id}: #{self.string_number} in project {self.project_id}>'


class WeldResult(db.Model):
    """Weld simulation result data.

    Stores thermal cycles, temperature fields, cooling rates, and derived
    phase transformation predictions.
    """
    __tablename__ = 'weld_results'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('weld_projects.id'), nullable=False)
    string_id = db.Column(db.Integer, db.ForeignKey('weld_strings.id'))

    # Result identification
    result_type = db.Column(db.Text, nullable=False)  # thermal_cycle, temperature_field, etc.
    location = db.Column(db.Text)  # Probe name, 'full_field', line name, etc.

    # Time-series data (for probes and thermal cycles)
    time_data = db.Column(db.Text)  # JSON array
    temperature_data = db.Column(db.Text)  # JSON array

    # Position data (for line profiles)
    position_data = db.Column(db.Text)  # JSON array

    # Field data (for 3D visualization)
    vtk_filename = db.Column(db.Text)  # Path to VTK file on disk
    timestamp = db.Column(db.Float)  # Time in simulation for this snapshot

    # Summary statistics
    peak_temperature = db.Column(db.Float)  # C
    t_800_500 = db.Column(db.Float)  # Cooling time 800-500 C (seconds)
    cooling_rate_max = db.Column(db.Float)  # C/s
    cooling_rate_800_500 = db.Column(db.Float)  # C/s average in range

    # Phase prediction (calculated from cooling rates)
    phase_fractions = db.Column(db.Text)  # JSON: {martensite, bainite, ferrite, pearlite}
    hardness_hv = db.Column(db.Float)  # Predicted hardness

    # Stored plot image (PNG bytes)
    plot_image = db.Column(db.LargeBinary)

    # Animation file reference
    animation_filename = db.Column(db.Text)  # Path to MP4 file

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_weld_results_project', 'project_id'),
        db.Index('ix_weld_results_string', 'string_id'),
        db.Index('ix_weld_results_type', 'result_type'),
    )

    @property
    def time_array(self) -> List[float]:
        """Parse time data JSON to list."""
        try:
            return json.loads(self.time_data) if self.time_data else []
        except json.JSONDecodeError:
            return []

    def set_time_data(self, data: List[float]) -> None:
        """Set time data from list."""
        self.time_data = json.dumps(data)

    @property
    def temperature_array(self) -> List[float]:
        """Parse temperature data JSON to list."""
        try:
            return json.loads(self.temperature_data) if self.temperature_data else []
        except json.JSONDecodeError:
            return []

    def set_temperature_data(self, data: List[float]) -> None:
        """Set temperature data from list."""
        self.temperature_data = json.dumps(data)

    @property
    def position_array(self) -> List[float]:
        """Parse position data JSON to list."""
        try:
            return json.loads(self.position_data) if self.position_data else []
        except json.JSONDecodeError:
            return []

    def set_position_data(self, data: List[float]) -> None:
        """Set position data from list."""
        self.position_data = json.dumps(data)

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
    def has_vtk(self) -> bool:
        """Check if VTK file exists."""
        return self.vtk_filename is not None

    @property
    def has_animation(self) -> bool:
        """Check if animation file exists."""
        return self.animation_filename is not None

    @property
    def result_label(self) -> str:
        """Human-readable result type."""
        labels = {
            RESULT_THERMAL_CYCLE: 'Thermal Cycle',
            RESULT_TEMPERATURE_FIELD: 'Temperature Field',
            RESULT_COOLING_RATE: 'Cooling Rate',
            RESULT_LINE_PROFILE: 'Line Profile',
        }
        return labels.get(self.result_type, self.result_type)

    def __repr__(self) -> str:
        return f'<WeldResult {self.id}: {self.result_type} at {self.location}>'
