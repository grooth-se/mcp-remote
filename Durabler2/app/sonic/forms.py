"""Forms for Sonic Resonance (E1875) test module."""

from flask_wtf import FlaskForm
from wtforms import (StringField, FloatField, SelectField, TextAreaField,
                     SubmitField, RadioField)
from wtforms.validators import DataRequired, Optional, NumberRange


class SpecimenForm(FlaskForm):
    """Form for sonic specimen geometry and velocity measurements."""

    # Certificate selection (populated dynamically in route)
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])

    # Specimen identification
    specimen_id = StringField('Specimen SN', validators=[DataRequired()])
    material = StringField('Material', validators=[Optional()])
    batch_number = StringField('Batch/Heat Number', validators=[Optional()])

    # Additional certificate fields
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])

    # Test info
    test_standard = SelectField('Test Standard', choices=[
        ('Modified ASTM E1875', 'Modified ASTM E1875'),
        ('ASTM E1875-20', 'ASTM E1875-20'),
        ('ISO 12680-1', 'ISO 12680-1')
    ])
    test_temperature = FloatField('Test Temperature (°C)', default=23.0)

    # Specimen type
    specimen_type = RadioField('Specimen Type', choices=[
        ('round', 'Round Bar'),
        ('square', 'Square Bar')
    ], default='round')

    # Dimensions - Round
    diameter = FloatField('Diameter (mm)', validators=[Optional()],
                         description='For round specimens')

    # Dimensions - Square
    side_length = FloatField('Side Length (mm)', validators=[Optional()],
                            description='For square specimens')

    # Common dimensions
    length = FloatField('Length (mm)', validators=[DataRequired(),
                        NumberRange(min=1, message='Length must be positive')])
    mass = FloatField('Mass (g)', validators=[DataRequired(),
                      NumberRange(min=0.1, message='Mass must be positive')])

    # Longitudinal velocity measurements (3 readings)
    vl1 = FloatField('Vl₁ (m/s)', validators=[DataRequired(),
                     NumberRange(min=1000, max=10000, message='Typical range: 3000-7000 m/s')])
    vl2 = FloatField('Vl₂ (m/s)', validators=[DataRequired(),
                     NumberRange(min=1000, max=10000)])
    vl3 = FloatField('Vl₃ (m/s)', validators=[DataRequired(),
                     NumberRange(min=1000, max=10000)])

    # Shear velocity measurements (3 readings)
    vs1 = FloatField('Vs₁ (m/s)', validators=[DataRequired(),
                     NumberRange(min=500, max=6000, message='Typical range: 2000-4000 m/s')])
    vs2 = FloatField('Vs₂ (m/s)', validators=[DataRequired(),
                     NumberRange(min=500, max=6000)])
    vs3 = FloatField('Vs₃ (m/s)', validators=[DataRequired(),
                     NumberRange(min=500, max=6000)])

    # Uncertainty parameters (ISO 17025)
    velocity_uncertainty = FloatField('Velocity Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=10, message='Typically 0.5-2%')
    ], default=1.0)
    dimension_uncertainty = FloatField('Dimension Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=5)
    ], default=0.5)
    mass_uncertainty = FloatField('Mass Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=5)
    ], default=0.1)

    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Calculate Results')


class ReportForm(FlaskForm):
    """Form for report generation options."""

    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_chart = SelectField('Include Chart', choices=[
        ('yes', 'Yes'),
        ('no', 'No')
    ], default='yes')

    submit = SubmitField('Generate Report')
