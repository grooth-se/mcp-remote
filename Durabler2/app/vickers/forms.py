"""Forms for Vickers Hardness tests - ASTM E92 / ISO 6507."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, FloatField, SelectField, DateField, TextAreaField,
    SubmitField, FieldList, FormField, IntegerField
)
from wtforms.validators import DataRequired, Optional, NumberRange


class ReadingForm(FlaskForm):
    """Subform for a single Vickers hardness reading."""
    class Meta:
        csrf = False  # Disable CSRF for subforms

    location = StringField('Location', validators=[Optional()])
    hardness_value = FloatField('HV', validators=[Optional(), NumberRange(min=1)])
    diagonal_1 = FloatField('d1 (um)', validators=[Optional(), NumberRange(min=0.1)])
    diagonal_2 = FloatField('d2 (um)', validators=[Optional(), NumberRange(min=0.1)])


class SpecimenForm(FlaskForm):
    """Form for Vickers specimen data entry."""

    # Test identification (Certificate and Specimen SN are main trace numbers)
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

    # Load level
    load_level = SelectField(
        'Load Level',
        choices=[
            ('HV 1', 'HV 1 (9.807 N)'),
            ('HV 5', 'HV 5 (49.03 N)'),
            ('HV 10', 'HV 10 (98.07 N)'),
            ('HV 30', 'HV 30 (294.2 N)'),
            ('HV 50', 'HV 50 (490.3 N)'),
            ('HV 100', 'HV 100 (980.7 N)'),
        ],
        default='HV 10',
        validators=[DataRequired()]
    )

    # Dwell time
    dwell_time = SelectField(
        'Dwell Time',
        choices=[
            ('10', '10 seconds'),
            ('15', '15 seconds (standard)'),
            ('30', '30 seconds'),
        ],
        default='15',
        validators=[Optional()]
    )

    # Number of indents to report
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
        validators=[DataRequired()]
    )

    # Hardness readings - up to 20 readings
    reading_1_location = StringField('Location 1', validators=[Optional()])
    reading_1_value = FloatField('HV 1', validators=[Optional(), NumberRange(min=1)])

    reading_2_location = StringField('Location 2', validators=[Optional()])
    reading_2_value = FloatField('HV 2', validators=[Optional(), NumberRange(min=1)])

    reading_3_location = StringField('Location 3', validators=[Optional()])
    reading_3_value = FloatField('HV 3', validators=[Optional(), NumberRange(min=1)])

    reading_4_location = StringField('Location 4', validators=[Optional()])
    reading_4_value = FloatField('HV 4', validators=[Optional(), NumberRange(min=1)])

    reading_5_location = StringField('Location 5', validators=[Optional()])
    reading_5_value = FloatField('HV 5', validators=[Optional(), NumberRange(min=1)])

    reading_6_location = StringField('Location 6', validators=[Optional()])
    reading_6_value = FloatField('HV 6', validators=[Optional(), NumberRange(min=1)])

    reading_7_location = StringField('Location 7', validators=[Optional()])
    reading_7_value = FloatField('HV 7', validators=[Optional(), NumberRange(min=1)])

    reading_8_location = StringField('Location 8', validators=[Optional()])
    reading_8_value = FloatField('HV 8', validators=[Optional(), NumberRange(min=1)])

    reading_9_location = StringField('Location 9', validators=[Optional()])
    reading_9_value = FloatField('HV 9', validators=[Optional(), NumberRange(min=1)])

    reading_10_location = StringField('Location 10', validators=[Optional()])
    reading_10_value = FloatField('HV 10', validators=[Optional(), NumberRange(min=1)])

    reading_11_location = StringField('Location 11', validators=[Optional()])
    reading_11_value = FloatField('HV 11', validators=[Optional(), NumberRange(min=1)])

    reading_12_location = StringField('Location 12', validators=[Optional()])
    reading_12_value = FloatField('HV 12', validators=[Optional(), NumberRange(min=1)])

    reading_13_location = StringField('Location 13', validators=[Optional()])
    reading_13_value = FloatField('HV 13', validators=[Optional(), NumberRange(min=1)])

    reading_14_location = StringField('Location 14', validators=[Optional()])
    reading_14_value = FloatField('HV 14', validators=[Optional(), NumberRange(min=1)])

    reading_15_location = StringField('Location 15', validators=[Optional()])
    reading_15_value = FloatField('HV 15', validators=[Optional(), NumberRange(min=1)])

    reading_16_location = StringField('Location 16', validators=[Optional()])
    reading_16_value = FloatField('HV 16', validators=[Optional(), NumberRange(min=1)])

    reading_17_location = StringField('Location 17', validators=[Optional()])
    reading_17_value = FloatField('HV 17', validators=[Optional(), NumberRange(min=1)])

    reading_18_location = StringField('Location 18', validators=[Optional()])
    reading_18_value = FloatField('HV 18', validators=[Optional(), NumberRange(min=1)])

    reading_19_location = StringField('Location 19', validators=[Optional()])
    reading_19_value = FloatField('HV 19', validators=[Optional(), NumberRange(min=1)])

    reading_20_location = StringField('Location 20', validators=[Optional()])
    reading_20_value = FloatField('HV 20', validators=[Optional(), NumberRange(min=1)])

    # Indent photo
    photo = FileField('Indent Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Image files only')
    ])

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Create Test')


class ReportForm(FlaskForm):
    """Form for Vickers report generation options."""

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
