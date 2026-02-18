"""Forms for KIC (Fracture Toughness) tests - ASTM E399."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, FloatField, SelectField, DateField, TextAreaField,
    SubmitField, IntegerField
)
from wtforms.validators import DataRequired, Optional, NumberRange


class UploadForm(FlaskForm):
    """Form for uploading Excel file - Step 1."""
    excel_file = FileField('MTS Analysis Report (Excel)', validators=[
        FileRequired('Excel file is required'),
        FileAllowed(['xlsx', 'xls'], 'Excel files only!')
    ])
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])
    submit = SubmitField('Upload & Verify Import')


class SpecimenForm(FlaskForm):
    """Form for KIC specimen data entry and file upload."""

    # Test identification
    test_id = StringField('Test ID', validators=[DataRequired()])
    specimen_id = StringField('Specimen SN', validators=[Optional()])
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])

    # Additional certificate fields (for display/reference)
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])

    # Specimen type
    specimen_type = SelectField(
        'Specimen Type',
        choices=[('SE(B)', 'SE(B) - Single Edge Bend'), ('C(T)', 'C(T) - Compact Tension')],
        validators=[DataRequired()]
    )

    # Specimen geometry (Optional - can be populated from Excel file)
    W = FloatField('W - Width (mm)', validators=[Optional(), NumberRange(min=0.1)])
    B = FloatField('B - Thickness (mm)', validators=[Optional(), NumberRange(min=0.1)])
    B_n = FloatField('Bn - Net Thickness (mm)', validators=[Optional(), NumberRange(min=0.1)])
    a_0 = FloatField('a0 - Initial Crack Length (mm)', validators=[Optional(), NumberRange(min=0.1)])
    S = FloatField('S - Span (mm, SE(B) only)', validators=[Optional(), NumberRange(min=0.1)])

    # 5-point crack measurements (ASTM E399)
    crack_1 = FloatField('a1 (mm)', validators=[Optional(), NumberRange(min=0)])
    crack_2 = FloatField('a2 (mm)', validators=[Optional(), NumberRange(min=0)])
    crack_3 = FloatField('a3 (mm)', validators=[Optional(), NumberRange(min=0)])
    crack_4 = FloatField('a4 (mm)', validators=[Optional(), NumberRange(min=0)])
    crack_5 = FloatField('a5 (mm)', validators=[Optional(), NumberRange(min=0)])

    # Material properties (Optional - can be populated from Excel file)
    material = StringField('Material', validators=[Optional()])
    yield_strength = FloatField('Yield Strength (MPa)', validators=[Optional(), NumberRange(min=1)])
    ultimate_strength = FloatField('Ultimate Tensile Strength (MPa)', validators=[Optional(), NumberRange(min=1)])
    youngs_modulus = FloatField("Young's Modulus (GPa)", validators=[Optional(), NumberRange(min=1)],
                                default=210.0)
    poissons_ratio = FloatField("Poisson's Ratio", validators=[Optional(), NumberRange(min=0.1, max=0.5)],
                                default=0.3)

    # Test conditions
    test_date = DateField('Test Date', validators=[Optional()])
    temperature = FloatField('Temperature (C)', validators=[Optional()], default=23.0)
    location_orientation = StringField('Location/Orientation', validators=[Optional()])

    # Data files
    csv_file = FileField('CSV Data File', validators=[
        Optional(),
        FileAllowed(['csv'], 'CSV files only')
    ])
    excel_file = FileField('Excel Analysis File', validators=[
        Optional(),
        FileAllowed(['xlsx', 'xls'], 'Excel files only')
    ])

    # Pre-crack data
    precrack_csv_file = FileField('Pre-crack Test Data (CSV)', validators=[
        Optional(),
        FileAllowed(['csv'], 'CSV files only')
    ])

    # Crack surface photos
    photo_1 = FileField('Crack Photo 1', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Image files only')
    ])
    photo_2 = FileField('Crack Photo 2', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Image files only')
    ])
    photo_3 = FileField('Crack Photo 3', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Image files only')
    ])
    photo_description_1 = StringField('Photo 1 Description', validators=[Optional()])
    photo_description_2 = StringField('Photo 2 Description', validators=[Optional()])
    photo_description_3 = StringField('Photo 3 Description', validators=[Optional()])

    # Uncertainty parameters (ISO 17025)
    force_uncertainty = FloatField('Force Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=10, message='Typically 0.5-2%')
    ], default=1.0)
    displacement_uncertainty = FloatField('Displacement Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=10)
    ], default=1.0)
    dimension_uncertainty = FloatField('Dimension Uncertainty (%)', validators=[
        Optional(),
        NumberRange(min=0.1, max=5)
    ], default=0.5)

    # Notes
    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Create Test')


class ReportForm(FlaskForm):
    """Form for KIC report generation options."""

    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_photos = SelectField(
        'Include Photos',
        choices=[('yes', 'Yes'), ('no', 'No')],
        default='yes'
    )
    submit = SubmitField('Generate Report')
