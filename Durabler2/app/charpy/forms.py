"""Forms for Charpy Impact tests - ASTM E23 / ISO 148-1."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, FloatField, SelectField, DateField, TextAreaField,
    SubmitField
)
from wtforms.validators import DataRequired, Optional, NumberRange


class SpecimenForm(FlaskForm):
    """Form for Charpy impact specimen data entry."""

    # Test identification
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])
    specimen_id = StringField('Specimen Set ID', validators=[DataRequired()])

    # Material info
    material = StringField('Material', validators=[Optional()])

    # Additional certificate fields
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])

    # Test conditions
    test_date = DateField('Test Date', validators=[Optional()])
    test_temperature = FloatField('Test Temperature (°C)', validators=[
        Optional(), NumberRange(min=-200, max=300)
    ], default=-40.0)
    location_orientation = StringField('Notch Orientation', validators=[Optional()],
                                       description='e.g. L-T, T-L, L-S')

    # Specimen configuration
    notch_type = SelectField(
        'Notch Type',
        choices=[
            ('V', 'V-notch (Charpy V, 45°, r=0.25mm)'),
            ('U', 'U-notch (Charpy U, r=1mm)'),
        ],
        default='V',
        validators=[DataRequired()]
    )

    specimen_size = SelectField(
        'Specimen Size',
        choices=[
            ('10x10', '10 x 10 mm (full-size)'),
            ('10x7.5', '10 x 7.5 mm (sub-size)'),
            ('10x5', '10 x 5 mm (sub-size)'),
            ('10x2.5', '10 x 2.5 mm (sub-size)'),
        ],
        default='10x10',
        validators=[DataRequired()]
    )

    # Number of specimens
    num_specimens = SelectField(
        'Number of Specimens',
        choices=[
            ('3', '3 specimens (standard set)'),
            ('5', '5 specimens'),
            ('6', '6 specimens'),
        ],
        default='3',
        validate_choice=False,
        validators=[DataRequired()]
    )

    # Manual readings — up to 6 specimens
    # Specimen 1
    specimen_1_id = StringField('Specimen 1 ID', validators=[Optional()])
    specimen_1_energy = FloatField('Energy (J)', validators=[Optional(), NumberRange(min=0)])
    specimen_1_lateral_exp = FloatField('Lat. Exp. (mm)', validators=[Optional(), NumberRange(min=0)])
    specimen_1_shear_area = FloatField('Shear (%)', validators=[Optional(), NumberRange(min=0, max=100)])

    # Specimen 2
    specimen_2_id = StringField('Specimen 2 ID', validators=[Optional()])
    specimen_2_energy = FloatField('Energy (J)', validators=[Optional(), NumberRange(min=0)])
    specimen_2_lateral_exp = FloatField('Lat. Exp. (mm)', validators=[Optional(), NumberRange(min=0)])
    specimen_2_shear_area = FloatField('Shear (%)', validators=[Optional(), NumberRange(min=0, max=100)])

    # Specimen 3
    specimen_3_id = StringField('Specimen 3 ID', validators=[Optional()])
    specimen_3_energy = FloatField('Energy (J)', validators=[Optional(), NumberRange(min=0)])
    specimen_3_lateral_exp = FloatField('Lat. Exp. (mm)', validators=[Optional(), NumberRange(min=0)])
    specimen_3_shear_area = FloatField('Shear (%)', validators=[Optional(), NumberRange(min=0, max=100)])

    # Specimen 4
    specimen_4_id = StringField('Specimen 4 ID', validators=[Optional()])
    specimen_4_energy = FloatField('Energy (J)', validators=[Optional(), NumberRange(min=0)])
    specimen_4_lateral_exp = FloatField('Lat. Exp. (mm)', validators=[Optional(), NumberRange(min=0)])
    specimen_4_shear_area = FloatField('Shear (%)', validators=[Optional(), NumberRange(min=0, max=100)])

    # Specimen 5
    specimen_5_id = StringField('Specimen 5 ID', validators=[Optional()])
    specimen_5_energy = FloatField('Energy (J)', validators=[Optional(), NumberRange(min=0)])
    specimen_5_lateral_exp = FloatField('Lat. Exp. (mm)', validators=[Optional(), NumberRange(min=0)])
    specimen_5_shear_area = FloatField('Shear (%)', validators=[Optional(), NumberRange(min=0, max=100)])

    # Specimen 6
    specimen_6_id = StringField('Specimen 6 ID', validators=[Optional()])
    specimen_6_energy = FloatField('Energy (J)', validators=[Optional(), NumberRange(min=0)])
    specimen_6_lateral_exp = FloatField('Lat. Exp. (mm)', validators=[Optional(), NumberRange(min=0)])
    specimen_6_shear_area = FloatField('Shear (%)', validators=[Optional(), NumberRange(min=0, max=100)])

    # Photo of fracture surface
    photo = FileField('Fracture Surface Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Image files only')
    ])

    # Uncertainty parameters (ISO 17025)
    machine_uncertainty = FloatField('Machine Uncertainty (%)', validators=[
        Optional(), NumberRange(min=0.1, max=10)
    ], default=1.0)
    temperature_uncertainty = FloatField('Temperature Uncertainty (°C)', validators=[
        Optional(), NumberRange(min=0.1, max=5)
    ], default=1.0)
    dimension_uncertainty = FloatField('Dimension Uncertainty (%)', validators=[
        Optional(), NumberRange(min=0.1, max=5)
    ], default=0.5)

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Create Test')


class ReportForm(FlaskForm):
    """Form for Charpy report generation options."""

    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_photo = SelectField(
        'Include Fracture Photo',
        choices=[('yes', 'Yes'), ('no', 'No')],
        default='yes'
    )
    include_uncertainty_budget = SelectField(
        'Include Uncertainty Budget',
        choices=[('yes', 'Yes'), ('no', 'No')],
        default='yes'
    )
    submit = SubmitField('Generate Report')
