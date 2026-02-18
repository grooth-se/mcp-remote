"""Tensile test forms."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (StringField, FloatField, SelectField, TextAreaField,
                     SubmitField, HiddenField, IntegerField, BooleanField)
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
    """
    Form for entering specimen geometry and test parameters.

    Round specimens: D0, L0, Lp, D1, L1, Lf
    Rectangular specimens: a0, b0, L0, Lp, au, bu, L1, Lf

    Yield evaluation:
    - Offset method: Rp0.2, Rp0.5
    - Yield point method: ReH, ReL
    """
    # Specimen identification
    specimen_id = StringField('Specimen SN', validators=[DataRequired()])
    material = StringField('Material', validators=[Optional()])
    batch_number = StringField('Batch/Heat Number', validators=[Optional()])

    # Additional certificate fields
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])

    # Specimen type
    specimen_type = SelectField('Specimen Type', choices=[
        ('round', 'Round (Cylindrical)'),
        ('rectangular', 'Rectangular (Flat)')
    ], validators=[DataRequired()])

    # Yield evaluation method
    yield_method = SelectField('Yield Evaluation', choices=[
        ('offset', 'Offset method (Rp0.2 / Rp0.5)'),
        ('yield_point', 'Yield point (ReH / ReL)')
    ], validators=[DataRequired()])

    # Data source option
    use_displacement_only = BooleanField('Use Displacement Data Only',
        description='Use when extensometer data is unreliable. E modulus calculated from 10-30% Rm range.')

    # Test standard
    test_standard = SelectField('Test Standard', choices=[
        ('ASTM E8/E8M-22', 'ASTM E8/E8M-22'),
        ('ISO 6892-1:2019', 'ISO 6892-1:2019')
    ])

    # Test conditions
    test_temperature = FloatField('Test Temperature (°C)', validators=[Optional()])

    # === ROUND SPECIMEN - BEFORE TEST ===
    D0 = FloatField('D0 - Initial Diameter (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100, message='Diameter must be between 0.1 and 100 mm')
    ])

    # === RECTANGULAR SPECIMEN - BEFORE TEST ===
    a0 = FloatField('a0 - Initial Width (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=200, message='Width must be between 0.1 and 200 mm')
    ])
    b0 = FloatField('b0 - Initial Thickness (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100, message='Thickness must be between 0.1 and 100 mm')
    ])

    # === COMMON - BEFORE TEST ===
    L0 = FloatField('L0 - Extensometer Length (mm)', validators=[
        DataRequired(),
        NumberRange(min=1, max=200, message='Extensometer length must be between 1 and 200 mm')
    ])
    Lp = FloatField('Lp - Parallel Length (mm)', validators=[
        DataRequired(),
        NumberRange(min=1, max=500, message='Parallel length must be between 1 and 500 mm')
    ])

    # === ROUND SPECIMEN - AFTER TEST ===
    D1 = FloatField('D1 - Final Diameter (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100, message='Diameter must be between 0.1 and 100 mm')
    ])

    # === RECTANGULAR SPECIMEN - AFTER TEST ===
    au = FloatField('au - Final Width (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=200)
    ])
    bu = FloatField('bu - Final Thickness (mm)', validators=[
        Optional(),
        NumberRange(min=0.1, max=100)
    ])

    # === COMMON - AFTER TEST ===
    L1 = FloatField('L1 - Final Extensometer Length (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=1000, message='Length must be between 1 and 1000 mm')
    ])
    Lf = FloatField('Lf - Final Parallel Length (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=1000)
    ])

    # Uncertainty parameters (ISO 17025)
    force_uncertainty = FloatField('Force Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=10, message='Typically 0.5-2%')
    ], default=1.0)
    displacement_uncertainty = FloatField('Displacement/Strain Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=10)
    ], default=1.0)
    dimension_uncertainty = FloatField('Dimension Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=5)
    ], default=0.5)

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Run Analysis')

    def validate(self, extra_validators=None):
        """Custom validation for specimen geometry."""
        if not super().validate(extra_validators):
            return False

        # Require diameter for round specimens
        if self.specimen_type.data == 'round':
            if not self.D0.data:
                self.D0.errors.append('Diameter D0 required for round specimens')
                return False

        # Require width and thickness for rectangular specimens
        if self.specimen_type.data == 'rectangular':
            if not self.a0.data:
                self.a0.errors.append('Width a0 required for rectangular specimens')
                return False
            if not self.b0.data:
                self.b0.errors.append('Thickness b0 required for rectangular specimens')
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
