"""Forms for materials management."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, FloatField,
    SubmitField, HiddenField, BooleanField
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange

from app.models import (
    DATA_SOURCES, DATA_SOURCE_STANDARD,
    PROPERTY_TYPES, PROPERTY_TYPE_CONSTANT,
    DIAGRAM_TYPES, DIAGRAM_TYPE_CCT,
    PHASES, PHASE_LABELS,
)


class SteelGradeForm(FlaskForm):
    """Form for creating/editing steel grades."""
    designation = StringField(
        'Designation',
        validators=[DataRequired(), Length(max=100)],
        render_kw={'placeholder': 'e.g., AISI 4340'}
    )
    data_source = SelectField(
        'Data Source',
        choices=[(s, s) for s in DATA_SOURCES],
        default=DATA_SOURCE_STANDARD
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)],
        render_kw={'placeholder': 'Optional description or notes', 'rows': 3}
    )
    submit = SubmitField('Save')


class MaterialPropertyForm(FlaskForm):
    """Form for creating/editing material properties."""
    property_name = SelectField(
        'Property',
        choices=[
            ('thermal_conductivity', 'Thermal Conductivity'),
            ('specific_heat', 'Specific Heat'),
            ('density', 'Density'),
            ('emissivity', 'Emissivity'),
            ('youngs_modulus', 'Young\'s Modulus'),
            ('poissons_ratio', 'Poisson\'s Ratio'),
            ('thermal_expansion', 'Thermal Expansion Coefficient'),
            ('custom', 'Custom Property...'),
        ],
        validators=[DataRequired()]
    )
    custom_name = StringField(
        'Custom Property Name',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'Enter custom property name'}
    )
    property_type = SelectField(
        'Type',
        choices=[(t, t.title()) for t in PROPERTY_TYPES],
        default=PROPERTY_TYPE_CONSTANT
    )
    units = StringField(
        'Units',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., W/(m·K)'}
    )
    dependencies = StringField(
        'Dependencies',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., temperature (comma-separated)'}
    )

    # Constant value
    constant_value = FloatField(
        'Value',
        validators=[Optional()]
    )

    # Curve data (JSON)
    curve_data = TextAreaField(
        'Curve Data (JSON)',
        validators=[Optional()],
        render_kw={
            'placeholder': '{"temperature": [20, 200, 400], "value": [50, 45, 40]}',
            'rows': 5
        }
    )

    # Polynomial coefficients
    polynomial_variable = StringField(
        'Variable',
        validators=[Optional()],
        default='temperature'
    )
    polynomial_coefficients = StringField(
        'Coefficients (comma-separated)',
        validators=[Optional()],
        render_kw={'placeholder': 'a0, a1, a2, ... (a0 + a1*x + a2*x² + ...)'}
    )

    # Equation
    equation = StringField(
        'Equation',
        validators=[Optional(), Length(max=200)],
        render_kw={'placeholder': 'e.g., 42.5 - 0.015*T'}
    )
    equation_variables = StringField(
        'Variable Mapping (JSON)',
        validators=[Optional()],
        render_kw={'placeholder': '{"T": "temperature"}'}
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)],
        render_kw={'placeholder': 'Optional notes about data source', 'rows': 2}
    )

    submit = SubmitField('Save Property')


class PhaseDiagramForm(FlaskForm):
    """Form for creating/editing phase diagrams."""
    diagram_type = SelectField(
        'Diagram Type',
        choices=[(t, t) for t in DIAGRAM_TYPES],
        default=DIAGRAM_TYPE_CCT
    )

    # Transformation temperatures
    ac1 = FloatField('Ac1 (°C)', validators=[Optional()])
    ac3 = FloatField('Ac3 (°C)', validators=[Optional()])
    ms = FloatField('Ms (°C)', validators=[Optional()])
    mf = FloatField('Mf (°C)', validators=[Optional()])
    bs = FloatField('Bs (°C)', validators=[Optional()])
    bf = FloatField('Bf (°C)', validators=[Optional()])

    # Curves data (JSON)
    curves_data = TextAreaField(
        'Curves Data (JSON)',
        validators=[Optional()],
        render_kw={'placeholder': 'Optional: digitized transformation curves', 'rows': 5}
    )

    # Source image
    source_image = FileField(
        'Source Diagram Image',
        validators=[FileAllowed(['png', 'jpg', 'jpeg'], 'Images only!')]
    )

    submit = SubmitField('Save Diagram')


class ImportForm(FlaskForm):
    """Form for importing material data from Excel."""
    file = FileField(
        'Excel File',
        validators=[
            DataRequired(),
            FileAllowed(['xlsx', 'xls'], 'Excel files only!')
        ]
    )
    data_source = SelectField(
        'Data Source',
        choices=[(s, s) for s in DATA_SOURCES],
        default=DATA_SOURCE_STANDARD
    )
    submit = SubmitField('Import')


class PropertyEvaluateForm(FlaskForm):
    """Form for evaluating property at specific conditions."""
    property_id = HiddenField()
    temperature = FloatField(
        'Temperature (°C)',
        validators=[Optional()]
    )
    submit = SubmitField('Evaluate')


class PhasePropertyForm(FlaskForm):
    """Form for creating/editing phase-specific properties."""
    phase = SelectField(
        'Phase/Structure',
        choices=[(p, PHASE_LABELS[p]) for p in PHASES],
        validators=[DataRequired()]
    )

    relative_density = FloatField(
        'Relative Density',
        validators=[Optional(), NumberRange(min=0.8, max=1.2)],
        render_kw={'placeholder': 'e.g., 1.000 (Ferrite at 20°C = 1.0)', 'step': '0.0001'}
    )

    thermal_expansion_coeff = FloatField(
        'Thermal Expansion Coefficient (10⁻⁶/K)',
        validators=[Optional(), NumberRange(min=0, max=50)],
        render_kw={'placeholder': 'e.g., 12.5 (mean value)', 'step': '0.1'}
    )

    expansion_type = SelectField(
        'Expansion Data Type',
        choices=[
            ('constant', 'Constant (mean value)'),
            ('temperature_dependent', 'Temperature-dependent curve'),
        ],
        default='constant'
    )

    expansion_data = TextAreaField(
        'Temperature-Dependent Expansion Data (JSON)',
        validators=[Optional()],
        render_kw={
            'placeholder': '{"temperature": [20, 200, 400, 600], "value": [11.5, 12.0, 13.0, 14.0]}',
            'rows': 4
        }
    )

    reference_temperature = FloatField(
        'Reference Temperature (°C)',
        validators=[Optional(), NumberRange(min=-273, max=1500)],
        default=20.0
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)],
        render_kw={'placeholder': 'Optional notes about data source', 'rows': 2}
    )

    submit = SubmitField('Save Phase Property')
