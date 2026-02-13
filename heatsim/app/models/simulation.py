"""Simulation models for heat treatment simulations.

Uses the 'materials' bind key to store in PostgreSQL alongside material data.
Supports multi-phase heat treatment: heating, transfer, quenching, tempering.
"""
from datetime import datetime
from typing import Optional, List, Dict
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
GEOMETRY_HOLLOW_CYLINDER = 'hollow_cylinder'
GEOMETRY_CAD = 'cad'

GEOMETRY_TYPES = [GEOMETRY_CYLINDER, GEOMETRY_PLATE, GEOMETRY_RING, GEOMETRY_HOLLOW_CYLINDER, GEOMETRY_CAD]

# Quench media types
QUENCH_WATER = 'water'
QUENCH_OIL = 'oil'
QUENCH_POLYMER = 'polymer'
QUENCH_BRINE = 'brine'
QUENCH_AIR = 'air'

QUENCH_MEDIA = [QUENCH_WATER, QUENCH_OIL, QUENCH_POLYMER, QUENCH_BRINE, QUENCH_AIR]

QUENCH_MEDIA_LABELS = {
    QUENCH_WATER: 'Water',
    QUENCH_OIL: 'Oil',
    QUENCH_POLYMER: 'Polymer',
    QUENCH_BRINE: 'Brine (Salt Water)',
    QUENCH_AIR: 'Air',
}

# Agitation levels
AGITATION_NONE = 'none'
AGITATION_MILD = 'mild'
AGITATION_MODERATE = 'moderate'
AGITATION_STRONG = 'strong'
AGITATION_VIOLENT = 'violent'

AGITATION_LEVELS = [AGITATION_NONE, AGITATION_MILD, AGITATION_MODERATE, AGITATION_STRONG, AGITATION_VIOLENT]

AGITATION_LABELS = {
    AGITATION_NONE: 'None (Still)',
    AGITATION_MILD: 'Mild',
    AGITATION_MODERATE: 'Moderate',
    AGITATION_STRONG: 'Strong',
    AGITATION_VIOLENT: 'Violent',
}

# Agitation HTC multipliers
AGITATION_MULTIPLIERS = {
    AGITATION_NONE: 1.0,
    AGITATION_MILD: 1.3,
    AGITATION_MODERATE: 1.6,
    AGITATION_STRONG: 2.0,
    AGITATION_VIOLENT: 2.5,
}

# Base HTC values for quench media (W/m²K) - still conditions
BASE_HTC = {
    QUENCH_WATER: 3000,
    QUENCH_OIL: 800,
    QUENCH_POLYMER: 1200,
    QUENCH_BRINE: 4500,
    QUENCH_AIR: 25,
}

# Legacy process types for backwards compatibility
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

# Legacy default HTC (kept for backwards compatibility)
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

# Furnace atmosphere types
FURNACE_AIR = 'air'
FURNACE_INERT = 'inert'
FURNACE_VACUUM = 'vacuum'
FURNACE_PROTECTIVE = 'protective'

FURNACE_ATMOSPHERES = [FURNACE_AIR, FURNACE_INERT, FURNACE_VACUUM, FURNACE_PROTECTIVE]

FURNACE_ATMOSPHERE_LABELS = {
    FURNACE_AIR: 'Air',
    FURNACE_INERT: 'Inert (N2/Ar)',
    FURNACE_VACUUM: 'Vacuum',
    FURNACE_PROTECTIVE: 'Protective Gas',
}


def calculate_quench_htc(media: str, agitation: str, temperature: float = 25.0) -> float:
    """Calculate effective HTC for quench media with agitation.

    Parameters
    ----------
    media : str
        Quench media type
    agitation : str
        Agitation level
    temperature : float
        Quench media temperature in Celsius

    Returns
    -------
    float
        Effective heat transfer coefficient (W/m²K)
    """
    base = BASE_HTC.get(media, 1000)
    multiplier = AGITATION_MULTIPLIERS.get(agitation, 1.0)

    # Temperature correction for water (higher temp = lower HTC due to vapor film)
    if media == QUENCH_WATER and temperature > 40:
        temp_factor = max(0.5, 1.0 - (temperature - 40) * 0.01)
        base *= temp_factor

    return base * multiplier


class Simulation(db.Model):
    """Heat treatment simulation job.

    Stores simulation configuration including geometry, material,
    and multi-phase process parameters (heating, transfer, quenching, tempering).
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

    # CAD geometry fields (for geometry_type == 'cad')
    cad_filename = db.Column(db.Text)       # Original filename
    cad_file_path = db.Column(db.Text)      # Stored file path
    cad_analysis = db.Column(db.Text)       # JSON: CADAnalysisResult
    cad_equivalent_type = db.Column(db.Text)  # 'cylinder' or 'plate'

    # Legacy process fields (kept for backwards compatibility)
    process_type = db.Column(db.Text, nullable=False, default=PROCESS_QUENCH_WATER)
    initial_temperature = db.Column(db.Float, default=850.0)
    ambient_temperature = db.Column(db.Float, default=25.0)

    # Multi-phase heat treatment configuration (JSON)
    # Structure: {heating: {...}, transfer: {...}, quenching: {...}, tempering: {...}}
    heat_treatment_config = db.Column(db.Text)

    # Boundary conditions (JSON) - legacy, now part of phase configs
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
    def cad_analysis_dict(self) -> dict:
        """Parse CAD analysis JSON."""
        try:
            return json.loads(self.cad_analysis) if self.cad_analysis else {}
        except json.JSONDecodeError:
            return {}

    def set_cad_analysis(self, analysis: dict) -> None:
        """Set CAD analysis from dict."""
        self.cad_analysis = json.dumps(analysis)

    @property
    def has_cad_geometry(self) -> bool:
        """Check if this simulation uses CAD-imported geometry."""
        return self.geometry_type == GEOMETRY_CAD and self.cad_analysis is not None

    @property
    def cad_equivalent_geometry_dict(self) -> dict:
        """Get the equivalent geometry parameters for CAD geometry.

        Returns the geometry config that should be used for the 1D simulation.
        """
        if not self.has_cad_geometry:
            return {}
        analysis = self.cad_analysis_dict
        return analysis.get('equivalent_params', {})

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
    def ht_config(self) -> dict:
        """Parse heat treatment configuration JSON."""
        try:
            return json.loads(self.heat_treatment_config) if self.heat_treatment_config else {}
        except json.JSONDecodeError:
            return {}

    def set_ht_config(self, config: dict) -> None:
        """Set heat treatment configuration from dict."""
        self.heat_treatment_config = json.dumps(config)

    @property
    def heating_config(self) -> dict:
        """Get heating phase configuration."""
        return self.ht_config.get('heating', {})

    @property
    def transfer_config(self) -> dict:
        """Get transfer phase configuration."""
        return self.ht_config.get('transfer', {})

    @property
    def quenching_config(self) -> dict:
        """Get quenching phase configuration."""
        return self.ht_config.get('quenching', {})

    @property
    def tempering_config(self) -> dict:
        """Get tempering phase configuration."""
        return self.ht_config.get('tempering', {})

    @property
    def has_heating(self) -> bool:
        """Check if heating phase is enabled."""
        return self.heating_config.get('enabled', False)

    @property
    def has_transfer(self) -> bool:
        """Check if transfer phase is enabled."""
        return self.transfer_config.get('enabled', False)

    @property
    def has_tempering(self) -> bool:
        """Check if tempering phase is enabled."""
        return self.tempering_config.get('enabled', False)

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
        if self.geometry_type == GEOMETRY_CAD:
            equiv = self.cad_equivalent_type or 'auto'
            return f"CAD ({equiv.title()})"
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

    def get_phases_summary(self) -> List[str]:
        """Get list of enabled phases for display."""
        phases = []
        if self.has_heating:
            h = self.heating_config
            phases.append(f"Heating: {h.get('target_temperature', 850)}°C for {h.get('hold_time', 0)}min")
        if self.has_transfer:
            t = self.transfer_config
            phases.append(f"Transfer: {t.get('duration', 0)}s")

        q = self.quenching_config
        if q:
            media = QUENCH_MEDIA_LABELS.get(q.get('media', 'water'), 'Water')
            agitation = AGITATION_LABELS.get(q.get('agitation', 'none'), 'None')
            phases.append(f"Quench: {media} ({agitation})")

        if self.has_tempering:
            t = self.tempering_config
            phases.append(f"Tempering: {t.get('temperature', 550)}°C for {t.get('hold_time', 60)}min")

        return phases

    def create_default_ht_config(self) -> dict:
        """Create default heat treatment configuration."""
        return {
            'heating': {
                'enabled': True,
                'initial_temperature': 25.0,
                'target_temperature': self.initial_temperature or 850.0,
                'heating_rate': 10.0,  # °C/min (for furnace control, not simulation)
                'hold_time': 60.0,  # minutes at target temperature
                'furnace_atmosphere': FURNACE_AIR,
                'furnace_htc': 25.0,  # W/m²K (convection in furnace)
                'furnace_emissivity': 0.85,
                'use_radiation': True,
            },
            'transfer': {
                'enabled': True,
                'duration': 10.0,  # seconds from furnace to quench
                'ambient_temperature': 25.0,
                'htc': 10.0,  # W/m²K (natural convection in air)
                'emissivity': 0.85,
                'use_radiation': True,
            },
            'quenching': {
                'enabled': True,
                'media': QUENCH_WATER,
                'media_temperature': 25.0,
                'agitation': AGITATION_MODERATE,
                'htc_override': None,  # Use calculated if None
                'duration': 300.0,  # seconds
                'emissivity': 0.3,  # Lower due to steam/oil film
                'use_radiation': False,  # Usually negligible in liquid quench
            },
            'tempering': {
                'enabled': False,
                'temperature': 550.0,
                'hold_time': 120.0,  # minutes
                'cooling_method': 'air',  # air, furnace
                'htc': 25.0,
                'emissivity': 0.85,
            },
        }

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
    snapshot_id = db.Column(db.Integer, db.ForeignKey('simulation_snapshots.id'), nullable=True)

    # Result type: 'cooling_curve', 'temperature_profile', 'phase_fraction', 'cooling_rate', 'full_cycle'
    result_type = db.Column(db.Text, nullable=False)

    # Phase identifier: 'heating', 'transfer', 'quenching', 'tempering', 'full'
    phase = db.Column(db.Text)

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

    # Generic result data (JSON) - for hardness, etc.
    result_data = db.Column(db.Text)

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
    def data_dict(self) -> dict:
        """Parse result data JSON to dict."""
        try:
            return json.loads(self.result_data) if self.result_data else {}
        except json.JSONDecodeError:
            return {}

    def set_data(self, data: dict) -> None:
        """Set result data from dict."""
        self.result_data = json.dumps(data)

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
            'full_cycle': 'Full Heat Treatment Cycle',
            'heating_curve': 'Heating Curve',
            'hardness_prediction': 'Predicted Hardness',
        }
        return labels.get(self.result_type, self.result_type)

    def __repr__(self) -> str:
        return f'<SimulationResult {self.id}: {self.result_type} at {self.location}>'


class HeatTreatmentTemplate(db.Model):
    """Reusable heat treatment configuration template.

    Allows users to save and reuse common heat treatment configurations
    like "Standard Q&T for 4140" or "Normalizing for Low Carbon Steel".
    """
    __tablename__ = 'heat_treatment_templates'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)

    # Owner (note: users table is in default bind, so no FK constraint)
    user_id = db.Column(db.Integer, nullable=False)

    # Public templates are visible to all users
    is_public = db.Column(db.Boolean, default=False)

    # Category for organization
    category = db.Column(db.Text)  # e.g., 'quench_temper', 'normalizing', 'stress_relief'

    # Heat treatment configuration (JSON) - same structure as Simulation.heat_treatment_config
    heat_treatment_config = db.Column(db.Text, nullable=False)

    # Optional: suggested geometry type and config
    suggested_geometry_type = db.Column(db.Text)
    suggested_geometry_config = db.Column(db.Text)  # JSON

    # Optional: solver settings
    solver_config = db.Column(db.Text)  # JSON

    # Usage statistics
    use_count = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_templates_user', 'user_id'),
        db.Index('ix_templates_public', 'is_public'),
        db.Index('ix_templates_category', 'category'),
    )

    # Category constants
    CATEGORY_QUENCH_TEMPER = 'quench_temper'
    CATEGORY_NORMALIZING = 'normalizing'
    CATEGORY_STRESS_RELIEF = 'stress_relief'
    CATEGORY_ANNEALING = 'annealing'
    CATEGORY_HARDENING = 'hardening'
    CATEGORY_CUSTOM = 'custom'

    CATEGORIES = [
        CATEGORY_QUENCH_TEMPER,
        CATEGORY_NORMALIZING,
        CATEGORY_STRESS_RELIEF,
        CATEGORY_ANNEALING,
        CATEGORY_HARDENING,
        CATEGORY_CUSTOM,
    ]

    CATEGORY_LABELS = {
        CATEGORY_QUENCH_TEMPER: 'Quench & Temper',
        CATEGORY_NORMALIZING: 'Normalizing',
        CATEGORY_STRESS_RELIEF: 'Stress Relief',
        CATEGORY_ANNEALING: 'Annealing',
        CATEGORY_HARDENING: 'Hardening',
        CATEGORY_CUSTOM: 'Custom',
    }

    @property
    def ht_config(self) -> dict:
        """Parse heat treatment config JSON."""
        try:
            return json.loads(self.heat_treatment_config) if self.heat_treatment_config else {}
        except json.JSONDecodeError:
            return {}

    def set_ht_config(self, config: dict) -> None:
        """Set heat treatment config from dict."""
        self.heat_treatment_config = json.dumps(config)

    @property
    def geometry_dict(self) -> dict:
        """Parse suggested geometry config JSON."""
        try:
            return json.loads(self.suggested_geometry_config) if self.suggested_geometry_config else {}
        except json.JSONDecodeError:
            return {}

    def set_geometry(self, config: dict) -> None:
        """Set suggested geometry config from dict."""
        self.suggested_geometry_config = json.dumps(config)

    @property
    def solver_dict(self) -> dict:
        """Parse solver config JSON."""
        try:
            return json.loads(self.solver_config) if self.solver_config else {}
        except json.JSONDecodeError:
            return {}

    def set_solver(self, config: dict) -> None:
        """Set solver config from dict."""
        self.solver_config = json.dumps(config)

    @property
    def category_label(self) -> str:
        """Human-readable category label."""
        return self.CATEGORY_LABELS.get(self.category, self.category or 'Uncategorized')

    def get_summary(self) -> str:
        """Get a brief summary of the heat treatment configuration."""
        ht = self.ht_config
        parts = []

        heating = ht.get('heating', {})
        if heating.get('enabled'):
            parts.append(f"Heat to {heating.get('target_temperature', 850):.0f}°C")

        quenching = ht.get('quenching', {})
        if quenching:
            media = quenching.get('media', 'water').title()
            parts.append(f"{media} quench")

        tempering = ht.get('tempering', {})
        if tempering.get('enabled'):
            parts.append(f"Temper at {tempering.get('temperature', 550):.0f}°C")

        return ' → '.join(parts) if parts else 'No configuration'

    def increment_use_count(self) -> None:
        """Increment the use count when template is applied."""
        self.use_count = (self.use_count or 0) + 1

    def __repr__(self) -> str:
        return f'<HeatTreatmentTemplate {self.id}: {self.name}>'
