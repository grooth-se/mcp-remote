"""Forms for Metallographic Examination - ASTM E45/E381, ISO 4967/4969."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, FloatField, SelectField, DateField, TextAreaField,
    SubmitField
)
from wtforms.validators import DataRequired, Optional, NumberRange


# Inclusion types per ASTM E45 / ISO 4967
INCLUSION_TYPES = [
    ('A', 'A - Sulfide'),
    ('B', 'B - Alumina'),
    ('C', 'C - Silicate'),
    ('D', 'D - Globular oxide'),
]


class SpecimenForm(FlaskForm):
    """Form for metallographic examination data entry."""

    # Test identification
    certificate_id = SelectField('Link to Certificate', coerce=int, validators=[Optional()])
    specimen_id = StringField('Specimen ID', validators=[DataRequired()])

    # Material / certificate fields
    material = StringField('Material', validators=[Optional()])
    customer_specimen_info = StringField('Customer Specimen Info', validators=[Optional()])
    requirement = StringField('Requirement', validators=[Optional()])
    location_orientation = StringField('Location / Orientation', validators=[Optional()],
                                       description='e.g. transverse, longitudinal, surface')
    test_date = DateField('Examination Date', validators=[Optional()])

    # ===== MICRO: inclusion content (ASTM E45 / ISO 4967) =====
    rating_method = SelectField(
        'Inclusion Rating Method',
        choices=[
            ('ASTM E45 Method A', 'ASTM E45 Method A (worst field)'),
            ('ASTM E45 Method D', 'ASTM E45 Method D (low inclusion)'),
            ('ISO 4967 Method A', 'ISO 4967 Method A (worst field)'),
            ('ISO 4967 Method B', 'ISO 4967 Method B (field by field)'),
            ('Other', 'Other'),
        ],
        default='ASTM E45 Method A',
        validators=[Optional()]
    )
    magnification = StringField('Magnification', validators=[Optional()], default='100x')
    micro_etchant = StringField('Preparation / Etchant (micro)', validators=[Optional()],
                                description='e.g. as-polished, Nital 2%')

    # Per-type inclusion severity (0-5 in 0.5 steps) + optional acceptance limit
    incl_A = FloatField('A - Sulfide severity', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_A_max = FloatField('A limit', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_B = FloatField('B - Alumina severity', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_B_max = FloatField('B limit', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_C = FloatField('C - Silicate severity', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_C_max = FloatField('C limit', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_D = FloatField('D - Globular oxide severity', validators=[Optional(), NumberRange(min=0, max=5)])
    incl_D_max = FloatField('D limit', validators=[Optional(), NumberRange(min=0, max=5)])

    micro_observations = TextAreaField('Micro Observations', validators=[Optional()],
                                       description='Microstructure / inclusion observations')

    # ===== MACRO: macroetch evaluation (ASTM E381 / ISO 4969) =====
    macro_etchant = StringField('Etchant (macro)', validators=[Optional()],
                                description='e.g. 1:1 HCl, 10% HNO3')
    macro_evaluation = TextAreaField('Macro Evaluation', validators=[Optional()],
                                     description='Macroetch condition: segregation, porosity, '
                                                 'flow lines, cracks (ASTM E381 / ISO 4969)')

    # ===== Photos (micrographs / macrographs) with captions =====
    photo_1 = FileField('Photo 1', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])
    photo_1_caption = StringField('Caption 1', validators=[Optional()])
    photo_2 = FileField('Photo 2', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])
    photo_2_caption = StringField('Caption 2', validators=[Optional()])
    photo_3 = FileField('Photo 3', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])
    photo_3_caption = StringField('Caption 3', validators=[Optional()])
    photo_4 = FileField('Photo 4', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])
    photo_4_caption = StringField('Caption 4', validators=[Optional()])
    photo_5 = FileField('Photo 5', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])
    photo_5_caption = StringField('Caption 5', validators=[Optional()])
    photo_6 = FileField('Photo 6', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])
    photo_6_caption = StringField('Caption 6', validators=[Optional()])

    notes = TextAreaField('Notes', validators=[Optional()])

    submit = SubmitField('Create Examination')


class ReportForm(FlaskForm):
    """Form for metallographic report generation options."""

    certificate_number = StringField('Certificate Number', validators=[Optional()])
    include_photos = SelectField(
        'Include Photos',
        choices=[('yes', 'Yes'), ('no', 'No')],
        default='yes'
    )
    submit = SubmitField('Generate Report')
