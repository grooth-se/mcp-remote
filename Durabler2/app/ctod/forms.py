"""Forms for CTOD (E1290) test module."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (StringField, FloatField, SelectField, TextAreaField,
                     SubmitField, FieldList)
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
    """Form for CTOD specimen geometry, material, and test parameters."""

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
    specimen_id = StringField('Specimen SN', validators=[DataRequired()])
    material = StringField('Material', validators=[Optional()])
    batch_number = StringField('Batch/Heat Number', validators=[Optional()])

    # Additional certificate fields
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])

    # Specimen type
    specimen_type = SelectField('Specimen Type', choices=[
        ('SE(B)', 'SE(B) - Single Edge Bend'),
        ('C(T)', 'C(T) - Compact Tension')
    ], validators=[DataRequired()])

    # Specimen geometry (Optional - can be populated from Excel file)
    W = FloatField('W - Width/Depth (mm)', validators=[
        Optional(),
        NumberRange(min=5, max=200, message='Width must be 5-200 mm')
    ])
    B = FloatField('B - Thickness (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=100, message='Thickness must be 1-100 mm')
    ])
    B_n = FloatField('Bn - Net Thickness (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=100)
    ])
    a_0 = FloatField('a₀ - Initial Crack Length (mm)', validators=[
        Optional(),
        NumberRange(min=1, max=150)
    ])
    S = FloatField('S - Span (mm)', validators=[
        Optional(),
        NumberRange(min=10, max=600)
    ])

    # 9-point crack measurements (pre-crack)
    a1 = FloatField('a₁ (Surface)', validators=[Optional()])
    a2 = FloatField('a₂', validators=[Optional()])
    a3 = FloatField('a₃', validators=[Optional()])
    a4 = FloatField('a₄', validators=[Optional()])
    a5 = FloatField('a₅ (Center)', validators=[Optional()])
    a6 = FloatField('a₆', validators=[Optional()])
    a7 = FloatField('a₇', validators=[Optional()])
    a8 = FloatField('a₈', validators=[Optional()])
    a9 = FloatField('a₉ (Surface)', validators=[Optional()])

    # Material properties (Optional - can be populated from Excel file)
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
    test_temperature = FloatField('Test Temperature (°C)', validators=[Optional()], default=23.0)
    notch_type = SelectField('Notch Type', choices=[
        ('fatigue', 'Fatigue Pre-crack'),
        ('edm', 'EDM Notch'),
        ('saw', 'Saw Cut')
    ])

    # Test standard
    test_standard = SelectField('Test Standard', choices=[
        ('ASTM E1290', 'ASTM E1290'),
        ('BS 7448', 'BS 7448'),
        ('ISO 12135', 'ISO 12135')
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

    submit = SubmitField('Run Analysis')


class ReportForm(FlaskForm):
    """Form for report generation options."""
    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_photos = SelectField('Include Crack Photos', choices=[
        ('no', 'No'),
        ('yes', 'Yes')
    ])
    submit = SubmitField('Generate Report')
