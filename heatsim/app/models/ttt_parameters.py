"""TTT/CCT transformation parameter models - PostgreSQL database.

Models for storing JMAK kinetics parameters, martensite transformation
parameters, calibration data from dilatometry, and cached TTT/CCT curves.
Uses SQLAlchemy binds to connect to the materials database.
"""
import json
from datetime import datetime
from typing import Optional, Dict, List

from app.extensions import db


# Data source constants for TTT parameters
TTT_SOURCE_LITERATURE = 'literature'
TTT_SOURCE_CALIBRATED = 'calibrated'
TTT_SOURCE_EMPIRICAL = 'empirical'

TTT_SOURCES = [TTT_SOURCE_LITERATURE, TTT_SOURCE_CALIBRATED, TTT_SOURCE_EMPIRICAL]

# B-function model types for JMAK
B_MODEL_GAUSSIAN = 'gaussian'
B_MODEL_ARRHENIUS = 'arrhenius'
B_MODEL_POLYNOMIAL = 'polynomial'

B_MODEL_TYPES = [B_MODEL_GAUSSIAN, B_MODEL_ARRHENIUS, B_MODEL_POLYNOMIAL]

# Curve types
CURVE_TYPE_TTT = 'TTT'
CURVE_TYPE_CCT = 'CCT'

CURVE_TYPES = [CURVE_TYPE_TTT, CURVE_TYPE_CCT]

# Curve positions
CURVE_POS_START = 'start'
CURVE_POS_FIFTY = 'fifty'
CURVE_POS_FINISH = 'finish'

CURVE_POSITIONS = [CURVE_POS_START, CURVE_POS_FIFTY, CURVE_POS_FINISH]


class TTTParameters(db.Model):
    """Master TTT parameter set for a steel grade.

    One record per steel grade. Links to JMAKParameters (per phase)
    and MartensiteParameters. Stores critical transformation temperatures
    and austenite grain size.

    Attributes
    ----------
    id : int
        Primary key
    steel_grade_id : int
        Foreign key to steel_grades (unique)
    ae1 : float
        Eutectoid temperature (Ae1) in deg C
    ae3 : float
        Upper critical temperature (Ae3) in deg C
    bs : float
        Bainite start temperature in deg C
    ms : float
        Martensite start temperature in deg C
    mf : float
        Martensite finish temperature in deg C
    austenitizing_temperature : float
        Reference austenitizing temperature in deg C
    grain_size_astm : float
        Prior austenite grain size (ASTM number)
    data_source : str
        Source: 'literature', 'calibrated', 'empirical'
    notes : str
        Optional notes about the data
    """
    __tablename__ = 'ttt_parameters'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    steel_grade_id = db.Column(
        db.Integer, db.ForeignKey('steel_grades.id'),
        nullable=False, unique=True
    )

    # Critical transformation temperatures (deg C)
    ae1 = db.Column(db.Float)
    ae3 = db.Column(db.Float)
    bs = db.Column(db.Float)
    ms = db.Column(db.Float)
    mf = db.Column(db.Float)

    # Austenitizing conditions
    austenitizing_temperature = db.Column(db.Float, default=900.0)
    grain_size_astm = db.Column(db.Float, default=8.0)

    # Metadata
    data_source = db.Column(db.Text, default=TTT_SOURCE_EMPIRICAL)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    steel_grade = db.relationship('SteelGrade', backref=db.backref(
        'ttt_parameters', uselist=False, cascade='all, delete-orphan'
    ))
    jmak_parameters = db.relationship(
        'JMAKParameters', backref='ttt_parameters',
        lazy='dynamic', cascade='all, delete-orphan'
    )
    martensite_parameters = db.relationship(
        'MartensiteParameters', backref='ttt_parameters',
        uselist=False, cascade='all, delete-orphan'
    )
    calibration_data = db.relationship(
        'TTTCalibrationData', backref='ttt_parameters',
        lazy='dynamic', cascade='all, delete-orphan'
    )
    cached_curves = db.relationship(
        'TTTCurve', backref='ttt_parameters',
        lazy='dynamic', cascade='all, delete-orphan'
    )

    __table_args__ = (
        db.Index('ix_ttt_parameters_steel_grade', 'steel_grade_id'),
    )

    @property
    def temps_dict(self) -> Dict[str, Optional[float]]:
        """Return transformation temperatures as dict."""
        return {
            'Ae1': self.ae1,
            'Ae3': self.ae3,
            'Bs': self.bs,
            'Ms': self.ms,
            'Mf': self.mf,
        }

    def get_jmak_for_phase(self, phase: str) -> Optional['JMAKParameters']:
        """Get JMAK parameters for a specific phase."""
        return self.jmak_parameters.filter_by(phase=phase).first()

    @property
    def has_jmak_data(self) -> bool:
        """Check if JMAK parameters are available for at least one phase."""
        return self.jmak_parameters.count() > 0

    def __repr__(self) -> str:
        return f'<TTTParameters for grade_id={self.steel_grade_id}>'


class JMAKParameters(db.Model):
    """JMAK kinetics parameters for a specific phase transformation.

    The JMAK equation is: X(t) = 1 - exp(-b(T) * t^n)
    where X is fraction transformed, t is time, n is the Avrami exponent,
    and b(T) is the temperature-dependent rate parameter.

    b(T) can be modeled as:
    - Gaussian: b(T) = b_max * exp(-0.5 * ((T - T_nose) / sigma)^2)
    - Arrhenius: b(T) = b0 * exp(-Q / (R * T_abs))
    - Polynomial: b(T) = sum(a_i * T^i)

    Attributes
    ----------
    id : int
        Primary key
    ttt_parameters_id : int
        Foreign key to ttt_parameters
    phase : str
        Phase name: 'ferrite', 'pearlite', 'bainite'
    n_value : float
        Avrami exponent (typically 1-4)
    b_model_type : str
        Model for b(T): 'gaussian', 'arrhenius', 'polynomial'
    b_parameters : str
        JSON with model-specific parameters
    nose_temperature : float
        C-curve nose temperature in deg C
    nose_time : float
        Time at nose (seconds) for 1% transformation
    temp_range_min : float
        Lower bound of valid temperature range (deg C)
    temp_range_max : float
        Upper bound of valid temperature range (deg C)
    """
    __tablename__ = 'jmak_parameters'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    ttt_parameters_id = db.Column(
        db.Integer, db.ForeignKey('ttt_parameters.id'),
        nullable=False
    )
    phase = db.Column(db.Text, nullable=False)

    # JMAK kinetics
    n_value = db.Column(db.Float, nullable=False, default=2.0)

    # b(T) rate parameter model
    b_model_type = db.Column(db.Text, nullable=False, default=B_MODEL_GAUSSIAN)
    b_parameters = db.Column(db.Text)  # JSON

    # C-curve nose characteristics
    nose_temperature = db.Column(db.Float)  # deg C
    nose_time = db.Column(db.Float)  # seconds (at 1% transformation)

    # Valid temperature range
    temp_range_min = db.Column(db.Float)
    temp_range_max = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('ttt_parameters_id', 'phase', name='uq_ttt_phase'),
        db.Index('ix_jmak_parameters_ttt', 'ttt_parameters_id'),
    )

    @property
    def b_params_dict(self) -> dict:
        """Parse b_parameters JSON to dict."""
        try:
            return json.loads(self.b_parameters) if self.b_parameters else {}
        except json.JSONDecodeError:
            return {}

    def set_b_params(self, params: dict) -> None:
        """Set b_parameters from dict."""
        self.b_parameters = json.dumps(params)

    def __repr__(self) -> str:
        return f'<JMAKParameters {self.phase} n={self.n_value}>'


class MartensiteParameters(db.Model):
    """Koistinen-Marburger parameters for martensite transformation.

    f_m = 1 - exp(-alpha_m * (Ms - T))

    Attributes
    ----------
    id : int
        Primary key
    ttt_parameters_id : int
        Foreign key to ttt_parameters (unique)
    ms : float
        Martensite start temperature (deg C)
    mf : float
        Martensite finish temperature (deg C)
    alpha_m : float
        Koistinen-Marburger rate parameter (1/K), typically 0.011
    """
    __tablename__ = 'martensite_parameters'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    ttt_parameters_id = db.Column(
        db.Integer, db.ForeignKey('ttt_parameters.id'),
        nullable=False, unique=True
    )

    ms = db.Column(db.Float, nullable=False)
    mf = db.Column(db.Float)
    alpha_m = db.Column(db.Float, nullable=False, default=0.011)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f'<MartensiteParameters Ms={self.ms} alpha={self.alpha_m}>'


class TTTCalibrationData(db.Model):
    """Experimental dilatometry data for TTT parameter calibration.

    Stores individual data points from isothermal or continuous cooling
    dilatometry tests used to fit JMAK parameters.

    Attributes
    ----------
    id : int
        Primary key
    ttt_parameters_id : int
        Foreign key to ttt_parameters
    test_type : str
        'isothermal' or 'continuous_cooling'
    phase : str
        Phase being measured
    temperature : float
        Hold temperature (isothermal) or measured temperature (deg C)
    time : float
        Time in seconds
    fraction_transformed : float
        Measured fraction transformed (0-1)
    cooling_rate : float
        Cooling rate for continuous cooling tests (K/s)
    notes : str
        Optional notes about the data point
    """
    __tablename__ = 'ttt_calibration_data'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    ttt_parameters_id = db.Column(
        db.Integer, db.ForeignKey('ttt_parameters.id'),
        nullable=False
    )

    test_type = db.Column(db.Text, nullable=False, default='isothermal')
    phase = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    time = db.Column(db.Float, nullable=False)
    fraction_transformed = db.Column(db.Float, nullable=False)
    cooling_rate = db.Column(db.Float)  # Only for continuous cooling
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_ttt_calibration_ttt', 'ttt_parameters_id'),
        db.Index('ix_ttt_calibration_phase', 'phase'),
    )

    def __repr__(self) -> str:
        return (f'<TTTCalibrationData {self.phase} T={self.temperature} '
                f't={self.time} f={self.fraction_transformed}>')


class TTTCurve(db.Model):
    """Cached generated TTT or CCT curve data.

    Stores pre-computed curve data to avoid regeneration on every request.
    Invalidated when TTT parameters change.

    Attributes
    ----------
    id : int
        Primary key
    ttt_parameters_id : int
        Foreign key to ttt_parameters
    curve_type : str
        'TTT' or 'CCT'
    phase : str
        Phase name
    curve_position : str
        'start' (1%), 'fifty' (50%), or 'finish' (99%)
    data_points : str
        JSON array of [time, temperature] pairs
    cooling_rate : float
        For CCT curves, the cooling rate this curve corresponds to (K/s)
    """
    __tablename__ = 'ttt_curves'
    __bind_key__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    ttt_parameters_id = db.Column(
        db.Integer, db.ForeignKey('ttt_parameters.id'),
        nullable=False
    )

    curve_type = db.Column(db.Text, nullable=False)  # TTT or CCT
    phase = db.Column(db.Text, nullable=False)
    curve_position = db.Column(db.Text, nullable=False)  # start, fifty, finish
    data_points = db.Column(db.Text)  # JSON array of [time, temperature]
    cooling_rate = db.Column(db.Float)  # For CCT curves only

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_ttt_curves_ttt', 'ttt_parameters_id'),
        db.Index('ix_ttt_curves_type_phase', 'curve_type', 'phase'),
    )

    @property
    def points(self) -> List[List[float]]:
        """Parse data_points JSON to list of [time, temperature] pairs."""
        try:
            return json.loads(self.data_points) if self.data_points else []
        except json.JSONDecodeError:
            return []

    def set_points(self, points: List[List[float]]) -> None:
        """Set data_points from list."""
        self.data_points = json.dumps(points)

    def __repr__(self) -> str:
        return f'<TTTCurve {self.curve_type} {self.phase} {self.curve_position}>'
