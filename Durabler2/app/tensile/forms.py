"""Tensile test forms."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (StringField, FloatField, SelectField, TextAreaField,
                     SubmitField, HiddenField, IntegerField)
from wtforms.validators import DataRequired, Optional, NumberRange


class CSVUploadForm(FlaskForm):
    """Form for uploading MTS CSV test data."""
    csv_file = FileField('MTS CSV File', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'CSV files only!')
    ])
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])
    submit = SubmitField('Upload')


class SpecimenForm(FlaskForm):
    """Form for entering specimen geometry and test parameters."""
    # Specimen identification
    specimen_id = StringField('Specimen ID', validators=[DataRequired()])
    material = StringField('Material', validators=[Optional()])
    batch_number = StringField('Batch/Heat Number', validators=[Optional()])

    # Specimen geometry
    specimen_type = SelectField('Specimen Type', choices=[
        ('round', 'Round (Cylindrical)'),
        ('rectangular', 'Rectangular (Flat)')
    ], validators=[DataRequired()])

    # Round specimen
    diameter = FloatField('Diameter d₀ (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100, message='Diameter must be between 0.1 and 100 mm')
    ])

    # Rectangular specimen
    width = FloatField('Width w₀ (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=200, message='Width must be between 0.1 and 200 mm')
    ])
    thickness = FloatField('Thickness t₀ (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100, message='Thickness must be between 0.1 and 100 mm')
    ])

    # Common geometry
    gauge_length = FloatField('Gauge Length L₀ (mm)', validators=[
        DataRequired(),
        NumberRange(min=1, max=500, message='Gauge length must be between 1 and 500 mm')
    ])
    parallel_length = FloatField('Parallel Length Lc (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=500)
    ])

    # Test conditions
    test_temperature = FloatField('Test Temperature (°C)', validators=[Optional()])
    test_standard = SelectField('Test Standard', choices=[
        ('ASTM E8/E8M-22', 'ASTM E8/E8M-22'),
        ('ISO 6892-1:2019', 'ISO 6892-1:2019')
    ])

    # Post-fracture measurements (optional)
    final_diameter = FloatField('Final Diameter df (mm)', validators=[Optional()])
    final_gauge_length = FloatField('Final Gauge Length Lf (mm)', validators=[Optional()])

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Run Analysis')

    def validate(self, extra_validators=None):
        """Custom validation for specimen geometry."""
        if not super().validate(extra_validators):
            return False

        # Require diameter for round specimens
        if self.specimen_type.data == 'round':
            if not self.diameter.data:
                self.diameter.errors.append('Diameter required for round specimens')
                return False

        # Require width and thickness for rectangular specimens
        if self.specimen_type.data == 'rectangular':
            if not self.width.data:
                self.width.errors.append('Width required for rectangular specimens')
                return False
            if not self.thickness.data:
                self.thickness.errors.append('Thickness required for rectangular specimens')
                return False

        return True


class ReportForm(FlaskForm):
    """Form for report generation options."""
    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_raw_data = SelectField('Include Raw Data', choices=[
        ('no', 'No'),
        ('summary', 'Summary Only'),
        ('full', 'Full Data')
    ])
    submit = SubmitField('Generate Report')
