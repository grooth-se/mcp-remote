"""Forms for simulation setup."""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, FloatField,
    IntegerField, SubmitField
)
from wtforms.validators import DataRequired, Optional, NumberRange, Length

from app.models.simulation import GEOMETRY_TYPES, PROCESS_LABELS


class SimulationForm(FlaskForm):
    """Form for creating a new simulation."""
    name = StringField(
        'Simulation Name',
        validators=[DataRequired(), Length(max=100)],
        render_kw={'placeholder': 'e.g., Shaft Quench Study'}
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)],
        render_kw={'rows': 3, 'placeholder': 'Optional description'}
    )
    steel_grade_id = SelectField(
        'Steel Grade',
        coerce=int,
        validators=[DataRequired()]
    )
    geometry_type = SelectField(
        'Geometry',
        choices=[(g, g.title()) for g in GEOMETRY_TYPES],
        default='cylinder'
    )
    process_type = SelectField(
        'Heat Treatment Process',
        choices=[(k, v) for k, v in PROCESS_LABELS.items()],
        default='quench_water'
    )
    initial_temperature = FloatField(
        'Initial Temperature (°C)',
        validators=[DataRequired(), NumberRange(min=20, max=1500)],
        default=850
    )
    ambient_temperature = FloatField(
        'Ambient/Quench Temperature (°C)',
        validators=[DataRequired(), NumberRange(min=-50, max=500)],
        default=25
    )
    submit = SubmitField('Create Simulation')


class GeometryForm(FlaskForm):
    """Form for geometry configuration."""
    # Cylinder
    radius = FloatField(
        'Radius (mm)',
        validators=[Optional(), NumberRange(min=1, max=1000)],
        default=50
    )
    # Plate
    thickness = FloatField(
        'Thickness (mm)',
        validators=[Optional(), NumberRange(min=1, max=1000)],
        default=20
    )
    # Common
    length = FloatField(
        'Length (mm)',
        validators=[Optional(), NumberRange(min=1, max=5000)],
        default=100
    )
    width = FloatField(
        'Width (mm)',
        validators=[Optional(), NumberRange(min=1, max=5000)],
        default=100
    )
    # Ring
    inner_radius = FloatField(
        'Inner Radius (mm)',
        validators=[Optional(), NumberRange(min=1, max=1000)],
        default=20
    )
    outer_radius = FloatField(
        'Outer Radius (mm)',
        validators=[Optional(), NumberRange(min=1, max=1000)],
        default=50
    )


class SolverForm(FlaskForm):
    """Form for solver configuration."""
    n_nodes = IntegerField(
        'Number of Nodes',
        validators=[DataRequired(), NumberRange(min=11, max=201)],
        default=51
    )
    dt = FloatField(
        'Time Step (s)',
        validators=[DataRequired(), NumberRange(min=0.001, max=10)],
        default=0.1
    )
    max_time = FloatField(
        'Maximum Time (s)',
        validators=[DataRequired(), NumberRange(min=10, max=36000)],
        default=600
    )
    htc = FloatField(
        'Heat Transfer Coefficient (W/m²K)',
        validators=[Optional(), NumberRange(min=1, max=50000)]
    )
    emissivity = FloatField(
        'Surface Emissivity',
        validators=[Optional(), NumberRange(min=0, max=1)],
        default=0.85
    )
    submit = SubmitField('Save Configuration')
