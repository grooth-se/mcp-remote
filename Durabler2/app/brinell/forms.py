"""Forms for Brinell Hardness tests - ASTM E10 / ISO 6506."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, FloatField, SelectField, DateField, TextAreaField,
    SubmitField, IntegerField
)
from wtforms.validators import DataRequired, Optional, NumberRange


class SpecimenForm(FlaskForm):
    """Form for Brinell specimen data entry."""

    # Test identification
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])
    specimen_id = StringField('Specimen SN', validators=[DataRequired()])

    # Material info
    material = StringField('Material', validators=[Optional()])

    # Additional certificate fields
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])

    # Test conditions
    test_date = DateField('Test Date', validators=[Optional()])
    temperature = FloatField('Temperature (C)', validators=[Optional()], default=23.0)
    location_orientation = StringField('Location/Orientation', validators=[Optional()])

    # Load level — Brinell uses HBW D/F designation
    load_level = SelectField(
        'Load Level',
        choices=[
            ('HBW 10/3000', 'HBW 10/3000 (F/D²=30)'),
            ('HBW 10/1500', 'HBW 10/1500 (F/D²=15)'),
            ('HBW 5/750', 'HBW 5/750 (F/D²=30)'),
            ('HBW 5/250', 'HBW 5/250 (F/D²=10)'),
            ('HBW 2.5/187.5', 'HBW 2.5/187.5 (F/D²=30)'),
            ('HBW 2.5/62.5', 'HBW 2.5/62.5 (F/D²=10)'),
            ('HBW 1/30', 'HBW 1/30 (F/D²=30)'),
            ('HBW 1/10', 'HBW 1/10 (F/D²=10)'),
            ('HBW 1/1', 'HBW 1/1 (F/D²=1)'),
        ],
        default='HBW 10/3000',
        validate_choice=False,
        validators=[DataRequired()]
    )

    # Dwell time
    dwell_time = SelectField(
        'Dwell Time',
        choices=[
            ('10', '10 seconds (ferrous, standard)'),
            ('15', '15 seconds (non-ferrous)'),
            ('30', '30 seconds'),
        ],
        default='10',
        validators=[Optional()]
    )

    # Number of indents to report
    # validate_choice=False: CSV import can inject any count via JS
    num_readings = SelectField(
        'Number of Indents',
        choices=[
            ('3', '3 indents'),
            ('5', '5 indents'),
            ('6', '6 indents'),
            ('10', '10 indents'),
            ('15', '15 indents'),
            ('20', '20 indents'),
        ],
        default='5',
        validate_choice=False,
        validators=[DataRequired()]
    )

    # Hardness readings - up to 20 readings (manual entry)
    reading_1_location = StringField('Location 1', validators=[Optional()])
    reading_1_value = FloatField('HBW 1', validators=[Optional(), NumberRange(min=1)])

    reading_2_location = StringField('Location 2', validators=[Optional()])
    reading_2_value = FloatField('HBW 2', validators=[Optional(), NumberRange(min=1)])

    reading_3_location = StringField('Location 3', validators=[Optional()])
    reading_3_value = FloatField('HBW 3', validators=[Optional(), NumberRange(min=1)])

    reading_4_location = StringField('Location 4', validators=[Optional()])
    reading_4_value = FloatField('HBW 4', validators=[Optional(), NumberRange(min=1)])

    reading_5_location = StringField('Location 5', validators=[Optional()])
    reading_5_value = FloatField('HBW 5', validators=[Optional(), NumberRange(min=1)])

    reading_6_location = StringField('Location 6', validators=[Optional()])
    reading_6_value = FloatField('HBW 6', validators=[Optional(), NumberRange(min=1)])

    reading_7_location = StringField('Location 7', validators=[Optional()])
    reading_7_value = FloatField('HBW 7', validators=[Optional(), NumberRange(min=1)])

    reading_8_location = StringField('Location 8', validators=[Optional()])
    reading_8_value = FloatField('HBW 8', validators=[Optional(), NumberRange(min=1)])

    reading_9_location = StringField('Location 9', validators=[Optional()])
    reading_9_value = FloatField('HBW 9', validators=[Optional(), NumberRange(min=1)])

    reading_10_location = StringField('Location 10', validators=[Optional()])
    reading_10_value = FloatField('HBW 10', validators=[Optional(), NumberRange(min=1)])

    reading_11_location = StringField('Location 11', validators=[Optional()])
    reading_11_value = FloatField('HBW 11', validators=[Optional(), NumberRange(min=1)])

    reading_12_location = StringField('Location 12', validators=[Optional()])
    reading_12_value = FloatField('HBW 12', validators=[Optional(), NumberRange(min=1)])

    reading_13_location = StringField('Location 13', validators=[Optional()])
    reading_13_value = FloatField('HBW 13', validators=[Optional(), NumberRange(min=1)])

    reading_14_location = StringField('Location 14', validators=[Optional()])
    reading_14_value = FloatField('HBW 14', validators=[Optional(), NumberRange(min=1)])

    reading_15_location = StringField('Location 15', validators=[Optional()])
    reading_15_value = FloatField('HBW 15', validators=[Optional(), NumberRange(min=1)])

    reading_16_location = StringField('Location 16', validators=[Optional()])
    reading_16_value = FloatField('HBW 16', validators=[Optional(), NumberRange(min=1)])

    reading_17_location = StringField('Location 17', validators=[Optional()])
    reading_17_value = FloatField('HBW 17', validators=[Optional(), NumberRange(min=1)])

    reading_18_location = StringField('Location 18', validators=[Optional()])
    reading_18_value = FloatField('HBW 18', validators=[Optional(), NumberRange(min=1)])

    reading_19_location = StringField('Location 19', validators=[Optional()])
    reading_19_value = FloatField('HBW 19', validators=[Optional(), NumberRange(min=1)])

    reading_20_location = StringField('Location 20', validators=[Optional()])
    reading_20_value = FloatField('HBW 20', validators=[Optional(), NumberRange(min=1)])

    # CSV import from test machine
    csv_file = FileField('Import Readings from CSV', validators=[
        Optional(),
        FileAllowed(['csv', 'txt'], 'CSV files only')
    ])

    # PDF attachment for report
    pdf_attachment = FileField('PDF Attachment (added to report)', validators=[
        Optional(),
        FileAllowed(['pdf'], 'PDF files only')
    ])

    # Indent photo
    photo = FileField('Indent Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Image files only')
    ])

    # Uncertainty parameters (ISO 17025)
    force_uncertainty = FloatField('Force Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.01, max=10)
    ], default=0.31)
    diameter_uncertainty = FloatField('Diameter Measurement Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=10)
    ], default=1.0)
    machine_uncertainty = FloatField('Machine Calibration Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=5)
    ], default=0.5)

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Create Test')


class ReportForm(FlaskForm):
    """Form for Brinell report generation options."""

    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_photo = SelectField(
        'Include Indent Photo',
        choices=[('yes', 'Yes'), ('no', 'No')],
        default='yes'
    )
    include_uncertainty_budget = SelectField(
        'Include Uncertainty Budget',
        choices=[('yes', 'Yes'), ('no', 'No')],
        default='yes'
    )
    submit = SubmitField('Generate Report')
