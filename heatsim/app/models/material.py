"""Material models - PostgreSQL database.

Models for steel grades, material properties, and phase transformation data.
Uses SQLAlchemy binds to connect to PostgreSQL.
"""
from datetime import datetime
from typing import Optional

from app.extensions import db


# Property type constants
PROPERTY_TYPE_CONSTANT = 'constant'
PROPERTY_TYPE_CURVE = 'curve'
PROPERTY_TYPE_TABLE = 'table'
PROPERTY_TYPE_POLYNOMIAL = 'polynomial'
PROPERTY_TYPE_EQUATION = 'equation'

PROPERTY_TYPES = [
    PROPERTY_TYPE_CONSTANT,
    PROPERTY_TYPE_CURVE,
    PROPERTY_TYPE_TABLE,
    PROPERTY_TYPE_POLYNOMIAL,
    PROPERTY_TYPE_EQUATION,
]

# Data source constants
DATA_SOURCE_STANDARD = 'Standard'
DATA_SOURCE_SUBSEATEC = 'Subseatec'

DATA_SOURCES = [DATA_SOURCE_STANDARD, DATA_SOURCE_SUBSEATEC]

# Diagram type constants
DIAGRAM_TYPE_CCT = 'CCT'
DIAGRAM_TYPE_TTT = 'TTT'

DIAGRAM_TYPES = [DIAGRAM_TYPE_CCT, DIAGRAM_TYPE_TTT]


class SteelGrade(db.Model):
    """Steel grade with designation and data source.

    Attributes
    ----------
    id : int
        Primary key
    designation : str
        Steel grade designation (e.g., "A182 F22", "AISI 4340")
    data_source : str
        Data source: "Standard" (literature) or "Subseatec" (proprietary)
    description : str
        Optional description or notes
    created_at : datetime
        Record creation timestamp
    updated_at : datetime
        Last update timestamp
    """
    __tablename__ = 'steel_grades'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    designation = db.Column(db.Text, nullable=False)
    data_source = db.Column(db.Text, nullable=False, default=DATA_SOURCE_STANDARD)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    properties = db.relationship('MaterialProperty', backref='steel_grade',
                                 lazy='dynamic', cascade='all, delete-orphan')
    phase_diagrams = db.relationship('PhaseDiagram', backref='steel_grade',
                                     lazy='dynamic', cascade='all, delete-orphan')

    # Unique constraint on designation + data_source
    __table_args__ = (
        db.UniqueConstraint('designation', 'data_source', name='uq_designation_source'),
        db.Index('ix_steel_grades_designation', 'designation'),
    )

    @property
    def display_name(self) -> str:
        """Full display name with data source."""
        return f"{self.designation} ({self.data_source})"

    @property
    def is_standard(self) -> bool:
        """Check if this is standard literature data."""
        return self.data_source == DATA_SOURCE_STANDARD

    @property
    def is_subseatec(self) -> bool:
        """Check if this is Subseatec proprietary data."""
        return self.data_source == DATA_SOURCE_SUBSEATEC

    def get_property(self, property_name: str) -> Optional['MaterialProperty']:
        """Get a specific property by name."""
        return self.properties.filter_by(property_name=property_name).first()

    def __repr__(self) -> str:
        return f'<SteelGrade {self.display_name}>'


class MaterialProperty(db.Model):
    """Material property with dependency support.

    Stores properties that can be constant values, temperature-dependent curves,
    multi-variable tables, polynomial coefficients, or custom equations.

    Attributes
    ----------
    id : int
        Primary key
    steel_grade_id : int
        Foreign key to steel_grades
    property_name : str
        Property name (e.g., "thermal_conductivity", "specific_heat")
    property_type : str
        Type: "constant", "curve", "table", "polynomial", "equation"
    units : str
        Property units (e.g., "W/(m·K)", "J/(kg·K)")
    dependencies : str
        Comma-separated dependency variables (e.g., "temperature" or "temperature,phase")
    data : str
        JSON data containing the property values (structure depends on property_type)
    notes : str
        Optional notes about the data source or measurement conditions
    created_at : datetime
        Record creation timestamp
    """
    __tablename__ = 'material_properties'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    steel_grade_id = db.Column(db.Integer, db.ForeignKey('steel_grades.id'), nullable=False)
    property_name = db.Column(db.Text, nullable=False)
    property_type = db.Column(db.Text, nullable=False, default=PROPERTY_TYPE_CONSTANT)
    units = db.Column(db.Text)
    dependencies = db.Column(db.Text, default='')  # Comma-separated list
    data = db.Column(db.Text, nullable=False)  # JSON string
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_material_properties_steel_grade', 'steel_grade_id'),
        db.Index('ix_material_properties_name', 'property_name'),
    )

    @property
    def display_name(self) -> str:
        """Human-readable property name."""
        return self.property_name.replace('_', ' ').title()

    @property
    def dependencies_list(self) -> list:
        """Get dependencies as list."""
        if not self.dependencies:
            return []
        return [d.strip() for d in self.dependencies.split(',') if d.strip()]

    @property
    def is_temperature_dependent(self) -> bool:
        """Check if property depends on temperature."""
        return 'temperature' in self.dependencies_list

    @property
    def data_dict(self) -> dict:
        """Parse data JSON to dict."""
        import json
        try:
            return json.loads(self.data) if self.data else {}
        except json.JSONDecodeError:
            return {}

    def set_data(self, data: dict) -> None:
        """Set data from dict."""
        import json
        self.data = json.dumps(data)

    def __repr__(self) -> str:
        return f'<MaterialProperty {self.property_name} for grade_id={self.steel_grade_id}>'


class PhaseDiagram(db.Model):
    """Phase transformation diagram data (CCT or TTT).

    Stores digitized CCT/TTT diagram data including transformation temperatures
    and curves for phase transformations.

    Attributes
    ----------
    id : int
        Primary key
    steel_grade_id : int
        Foreign key to steel_grades
    diagram_type : str
        Type: "CCT" or "TTT"
    transformation_temps : str
        JSON with key temperatures {Ac1, Ac3, Ms, Mf, etc.}
    curves : str
        JSON with digitized transformation curves
    source_image : bytes
        Original diagram image (PNG/JPG)
    created_at : datetime
        Record creation timestamp
    """
    __tablename__ = 'phase_diagrams'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    steel_grade_id = db.Column(db.Integer, db.ForeignKey('steel_grades.id'), nullable=False)
    diagram_type = db.Column(db.Text, nullable=False)
    transformation_temps = db.Column(db.Text)  # JSON string
    curves = db.Column(db.Text)  # JSON string
    source_image = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_phase_diagrams_steel_grade', 'steel_grade_id'),
    )

    @property
    def has_image(self) -> bool:
        """Check if source image is stored."""
        return self.source_image is not None

    @property
    def temps_dict(self) -> dict:
        """Parse transformation temps JSON to dict."""
        import json
        try:
            return json.loads(self.transformation_temps) if self.transformation_temps else {}
        except json.JSONDecodeError:
            return {}

    def set_temps(self, temps: dict) -> None:
        """Set transformation temps from dict."""
        import json
        self.transformation_temps = json.dumps(temps)

    @property
    def curves_dict(self) -> dict:
        """Parse curves JSON to dict."""
        import json
        try:
            return json.loads(self.curves) if self.curves else {}
        except json.JSONDecodeError:
            return {}

    def set_curves(self, curves: dict) -> None:
        """Set curves from dict."""
        import json
        self.curves = json.dumps(curves)

    def get_temp(self, temp_name: str) -> Optional[float]:
        """Get a specific transformation temperature."""
        return self.temps_dict.get(temp_name)

    @property
    def ac1(self) -> Optional[float]:
        return self.get_temp('Ac1')

    @property
    def ac3(self) -> Optional[float]:
        return self.get_temp('Ac3')

    @property
    def ms(self) -> Optional[float]:
        return self.get_temp('Ms')

    @property
    def mf(self) -> Optional[float]:
        return self.get_temp('Mf')

    def __repr__(self) -> str:
        return f'<PhaseDiagram {self.diagram_type} for grade_id={self.steel_grade_id}>'


# Phase/Structure type constants
PHASE_FERRITE = 'ferrite'
PHASE_AUSTENITE = 'austenite'
PHASE_MARTENSITE = 'martensite'
PHASE_BAINITE = 'bainite'
PHASE_PEARLITE = 'pearlite'
PHASE_CEMENTITE = 'cementite'

PHASES = [
    PHASE_FERRITE,
    PHASE_AUSTENITE,
    PHASE_MARTENSITE,
    PHASE_BAINITE,
    PHASE_PEARLITE,
    PHASE_CEMENTITE,
]

PHASE_LABELS = {
    PHASE_FERRITE: 'Ferrite (α)',
    PHASE_AUSTENITE: 'Austenite (γ)',
    PHASE_MARTENSITE: 'Martensite',
    PHASE_BAINITE: 'Bainite',
    PHASE_PEARLITE: 'Pearlite',
    PHASE_CEMENTITE: 'Cementite (Fe₃C)',
}


class PhaseProperty(db.Model):
    """Phase-specific material properties.

    Stores properties that vary by crystallographic phase/structure,
    such as relative density and thermal expansion coefficients.
    These are critical for:
    - Volume change calculations during phase transformations
    - Residual stress prediction
    - Dimensional change estimation

    Attributes
    ----------
    id : int
        Primary key
    steel_grade_id : int
        Foreign key to steel_grades
    phase : str
        Phase/structure type (ferrite, austenite, martensite, etc.)
    relative_density : float
        Relative density compared to reference (typically ferrite at 20°C = 1.0)
    thermal_expansion_coeff : float
        Mean thermal expansion coefficient (1/K or 1/°C)
    expansion_type : str
        Type: "constant" or "temperature_dependent"
    expansion_data : str
        JSON data for temperature-dependent expansion
    reference_temperature : float
        Reference temperature for density/expansion (°C)
    notes : str
        Optional notes
    created_at : datetime
        Record creation timestamp
    """
    __tablename__ = 'phase_properties'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    steel_grade_id = db.Column(db.Integer, db.ForeignKey('steel_grades.id'), nullable=False)
    phase = db.Column(db.Text, nullable=False)

    # Relative density (dimensionless, reference = ferrite at 20°C)
    relative_density = db.Column(db.Float)

    # Thermal expansion coefficient
    thermal_expansion_coeff = db.Column(db.Float)  # Mean value (1/K)
    expansion_type = db.Column(db.Text, default='constant')  # constant or temperature_dependent
    expansion_data = db.Column(db.Text)  # JSON for T-dependent: {"temperature": [], "value": []}

    # Reference conditions
    reference_temperature = db.Column(db.Float, default=20.0)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    steel_grade = db.relationship('SteelGrade', backref=db.backref(
        'phase_properties', lazy='dynamic', cascade='all, delete-orphan'
    ))

    __table_args__ = (
        db.UniqueConstraint('steel_grade_id', 'phase', name='uq_grade_phase'),
        db.Index('ix_phase_properties_steel_grade', 'steel_grade_id'),
    )

    @property
    def phase_label(self) -> str:
        """Human-readable phase name."""
        return PHASE_LABELS.get(self.phase, self.phase.title())

    @property
    def expansion_data_dict(self) -> dict:
        """Parse expansion data JSON to dict."""
        import json
        try:
            return json.loads(self.expansion_data) if self.expansion_data else {}
        except json.JSONDecodeError:
            return {}

    def set_expansion_data(self, data: dict) -> None:
        """Set expansion data from dict."""
        import json
        self.expansion_data = json.dumps(data)

    @property
    def is_expansion_temperature_dependent(self) -> bool:
        """Check if expansion coefficient is temperature-dependent."""
        return self.expansion_type == 'temperature_dependent'

    def get_expansion_at_temperature(self, temperature: float) -> Optional[float]:
        """Get thermal expansion coefficient at given temperature.

        Parameters
        ----------
        temperature : float
            Temperature in °C

        Returns
        -------
        float or None
            Expansion coefficient (1/K), or None if unavailable
        """
        if self.expansion_type == 'constant':
            return self.thermal_expansion_coeff

        # Temperature-dependent interpolation
        data = self.expansion_data_dict
        temps = data.get('temperature', [])
        values = data.get('value', [])

        if not temps or not values or len(temps) != len(values):
            return self.thermal_expansion_coeff  # Fall back to constant

        import numpy as np
        from scipy import interpolate

        interp = interpolate.interp1d(
            temps, values,
            kind='linear',
            bounds_error=False,
            fill_value=(values[0], values[-1])
        )
        return float(interp(temperature))

    def __repr__(self) -> str:
        return f'<PhaseProperty {self.phase} for grade_id={self.steel_grade_id}>'


class SteelComposition(db.Model):
    """Chemical composition for a steel grade.

    Stores element percentages (wt%) for hardness prediction using
    Maynier equations and carbon equivalent calculations.

    Attributes
    ----------
    id : int
        Primary key
    steel_grade_id : int
        Foreign key to steel_grades (unique, one composition per grade)
    carbon : float
        Carbon content (wt%), required
    manganese : float
        Manganese content (wt%)
    silicon : float
        Silicon content (wt%)
    chromium : float
        Chromium content (wt%)
    nickel : float
        Nickel content (wt%)
    molybdenum : float
        Molybdenum content (wt%)
    vanadium : float
        Vanadium content (wt%)
    tungsten : float
        Tungsten content (wt%)
    copper : float
        Copper content (wt%)
    phosphorus : float
        Phosphorus content (wt%)
    sulfur : float
        Sulfur content (wt%)
    nitrogen : float
        Nitrogen content (wt%)
    boron : float
        Boron content (wt%)
    source : str
        Data source (e.g., "ASTM A29", "Mill certificate")
    notes : str
        Optional notes
    created_at : datetime
        Record creation timestamp
    """
    __tablename__ = 'steel_compositions'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    steel_grade_id = db.Column(db.Integer, db.ForeignKey('steel_grades.id'),
                                nullable=False, unique=True)

    # Primary alloying elements (wt%)
    carbon = db.Column(db.Float, nullable=False)
    manganese = db.Column(db.Float, default=0.0)
    silicon = db.Column(db.Float, default=0.0)

    # Secondary alloying elements
    chromium = db.Column(db.Float, default=0.0)
    nickel = db.Column(db.Float, default=0.0)
    molybdenum = db.Column(db.Float, default=0.0)
    vanadium = db.Column(db.Float, default=0.0)

    # Additional elements
    tungsten = db.Column(db.Float, default=0.0)
    copper = db.Column(db.Float, default=0.0)
    phosphorus = db.Column(db.Float, default=0.0)
    sulfur = db.Column(db.Float, default=0.0)
    nitrogen = db.Column(db.Float, default=0.0)
    boron = db.Column(db.Float, default=0.0)

    # Tempering properties
    hollomon_jaffe_c = db.Column(db.Float, default=20.0)

    # Metadata
    source = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    steel_grade = db.relationship('SteelGrade', backref=db.backref(
        'composition', uselist=False, cascade='all, delete-orphan'
    ))

    __table_args__ = (
        db.Index('ix_steel_compositions_steel_grade', 'steel_grade_id'),
    )

    @property
    def carbon_equivalent_iiw(self) -> float:
        """Calculate IIW carbon equivalent.

        CE(IIW) = C + Mn/6 + (Cr+Mo+V)/5 + (Ni+Cu)/15

        Returns
        -------
        float
            Carbon equivalent (IIW formula)
        """
        C = self.carbon or 0.0
        Mn = self.manganese or 0.0
        Cr = self.chromium or 0.0
        Mo = self.molybdenum or 0.0
        V = self.vanadium or 0.0
        Ni = self.nickel or 0.0
        Cu = self.copper or 0.0

        return C + Mn/6 + (Cr + Mo + V)/5 + (Ni + Cu)/15

    @property
    def carbon_equivalent_pcm(self) -> float:
        """Calculate Pcm carbon equivalent.

        Pcm = C + Si/30 + (Mn+Cu+Cr)/20 + Ni/60 + Mo/15 + V/10 + 5*B

        Returns
        -------
        float
            Carbon equivalent (Pcm formula)
        """
        C = self.carbon or 0.0
        Si = self.silicon or 0.0
        Mn = self.manganese or 0.0
        Cu = self.copper or 0.0
        Cr = self.chromium or 0.0
        Ni = self.nickel or 0.0
        Mo = self.molybdenum or 0.0
        V = self.vanadium or 0.0
        B = self.boron or 0.0

        return C + Si/30 + (Mn + Cu + Cr)/20 + Ni/60 + Mo/15 + V/10 + 5*B

    @property
    def carbon_equivalent_cen(self) -> float:
        """Calculate CEN carbon equivalent (Yurioka formula).

        CEN = C + A(C) × [Si/24 + Mn/6 + Cu/15 + Ni/20 + (Cr+Mo+Nb+V)/5 + 5B]
        A(C) = 0.75 + 0.25 × tanh(20 × (C - 0.12))

        Returns
        -------
        float
            Carbon equivalent (CEN formula)
        """
        import math
        C = self.carbon or 0.0
        Si = self.silicon or 0.0
        Mn = self.manganese or 0.0
        Cu = self.copper or 0.0
        Cr = self.chromium or 0.0
        Ni = self.nickel or 0.0
        Mo = self.molybdenum or 0.0
        V = self.vanadium or 0.0
        Nb = getattr(self, 'niobium', 0.0) or 0.0
        B = self.boron or 0.0

        A_C = 0.75 + 0.25 * math.tanh(20 * (C - 0.12))
        alloy_term = (Si/24 + Mn/6 + Cu/15 + Ni/20 +
                      (Cr + Mo + Nb + V)/5 + 5*B)
        return C + A_C * alloy_term

    @property
    def ideal_diameter_di(self) -> float:
        """Calculate Grossmann ideal critical diameter (DI).

        Estimates hardenability using multiplying factors.

        Returns
        -------
        float
            Ideal diameter in inches
        """
        C = self.carbon or 0.0
        Mn = self.manganese or 0.0
        Si = self.silicon or 0.0
        Cr = self.chromium or 0.0
        Ni = self.nickel or 0.0
        Mo = self.molybdenum or 0.0

        # Base DI from carbon content (simplified from Grossmann)
        if C <= 0.0:
            return 0.0
        DI_base = 0.54 * (C ** 0.5)

        # Multiplying factors (simplified)
        f_Mn = 1.0 + 3.33 * Mn
        f_Si = 1.0 + 0.70 * Si
        f_Cr = 1.0 + 2.16 * Cr
        f_Ni = 1.0 + 0.36 * Ni
        f_Mo = 1.0 + 3.00 * Mo

        return DI_base * f_Mn * f_Si * f_Cr * f_Ni * f_Mo

    def to_dict(self) -> dict:
        """Convert composition to dictionary for calculations.

        Returns
        -------
        dict
            Element symbols as keys, wt% as values
        """
        return {
            'C': self.carbon or 0.0,
            'Mn': self.manganese or 0.0,
            'Si': self.silicon or 0.0,
            'Cr': self.chromium or 0.0,
            'Ni': self.nickel or 0.0,
            'Mo': self.molybdenum or 0.0,
            'V': self.vanadium or 0.0,
            'W': self.tungsten or 0.0,
            'Cu': self.copper or 0.0,
            'P': self.phosphorus or 0.0,
            'S': self.sulfur or 0.0,
            'N': self.nitrogen or 0.0,
            'B': self.boron or 0.0,
            'Hp': self.hollomon_jaffe_c or 20.0,
        }

    def __repr__(self) -> str:
        return f'<SteelComposition C={self.carbon} for grade_id={self.steel_grade_id}>'
