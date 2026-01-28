"""Forms for FCGR (E647) test module."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, FloatField, SelectField, TextAreaField,
                     SubmitField, IntegerField)
from wtforms.validators import DataRequired, Optional, NumberRange


class SpecimenForm(FlaskForm):
    """Form for FCGR specimen geometry, material, and test parameters."""

    # Certificate selection (populated dynamically in route)
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])

    # Data file upload
    excel_file = FileField('MTS Analysis Report (Excel)', validators=[
        FileAllowed(['xlsx', 'xls'], 'Excel files only!')
    ])
    csv_file = FileField('Raw Test Data (CSV)', validators=[
        FileAllowed(['csv'], 'CSV files only!')
    ])

    # Specimen identification
    specimen_id = StringField('Specimen ID', validators=[DataRequired()])
    material = StringField('Material', validators=[Optional()])
    batch_number = StringField('Batch/Heat Number', validators=[Optional()])

    # Specimen type
    specimen_type = SelectField('Specimen Type', choices=[
        ('C(T)', 'C(T) - Compact Tension'),
        ('M(T)', 'M(T) - Middle Tension')
    ], validators=[DataRequired()])

    # Specimen geometry (Optional - can be populated from Excel file)
    W = FloatField('W - Width (mm)', validators=[
        Optional(),
        NumberRange(min=10, max=500, message='Width must be 10-500 mm')
    ])
    B = FloatField('B - Thickness (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=100, message='Thickness must be 1-100 mm')
    ])
    B_n = FloatField('Bn - Net Thickness (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=100)
    ])
    a_0 = FloatField('a₀ - Initial Notch Length (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=200)
    ])
    notch_height = FloatField('h - Notch Height (mm)', validators=[
        Optional(),
        NumberRange(min=0, max=50)
    ])

    # Material properties
    yield_strength = FloatField('Yield Strength (MPa)', validators=[
        Optional(),
        NumberRange(min=50, max=3000)
    ])
    ultimate_strength = FloatField('Ultimate Strength (MPa)', validators=[
        Optional(),
        NumberRange(min=100, max=3000)
    ])
    youngs_modulus = FloatField("Young's Modulus (GPa)", validators=[
        Optional(),
        NumberRange(min=50, max=500, message='E must be 50-500 GPa')
    ], default=210.0)
    poissons_ratio = FloatField("Poisson's Ratio", validators=[
        Optional(),
        NumberRange(min=0.1, max=0.5)
    ], default=0.3)

    # Test parameters
    control_mode = SelectField('Control Mode', choices=[
        ('Load Control', 'Load Control (Constant ΔP)'),
        ('Delta-K Control', 'Delta-K Control (K-decreasing)')
    ])
    load_ratio = FloatField('R - Load Ratio (Pmin/Pmax)', validators=[
        Optional(),
        NumberRange(min=-1, max=0.99)
    ], default=0.1)
    frequency = FloatField('Frequency (Hz)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100)
    ], default=10.0)
    wave_shape = SelectField('Wave Shape', choices=[
        ('Sine', 'Sine'),
        ('Triangle', 'Triangle'),
        ('Square', 'Square')
    ])
    test_temperature = FloatField('Test Temperature (°C)', validators=[Optional()], default=23.0)
    environment = StringField('Environment', validators=[Optional()], default='Laboratory Air')

    # Analysis parameters
    dadn_method = SelectField('da/dN Calculation Method', choices=[
        ('secant', 'Secant (Point-to-Point)'),
        ('polynomial', 'Incremental Polynomial')
    ])
    outlier_threshold = FloatField('Outlier Threshold (%)', validators=[
        Optional(),
        NumberRange(min=5, max=100)
    ], default=30.0)

    # Test standard
    test_standard = SelectField('Test Standard', choices=[
        ('ASTM E647', 'ASTM E647')
    ])

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Run Analysis')


class ReportForm(FlaskForm):
    """Form for report generation options."""
    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_photos = SelectField('Include Crack Photos', choices=[
        ('no', 'No'),
        ('yes', 'Yes')
    ])
    submit = SubmitField('Generate Report')
