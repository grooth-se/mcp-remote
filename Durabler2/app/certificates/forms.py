"""Certificate register forms."""
from flask_wtf import FlaskForm
from wtforms import (StringField, IntegerField, DateField, TextAreaField,
                     BooleanField, SelectField, SubmitField)
from wtforms.validators import DataRequired, Optional, NumberRange


class CertificateForm(FlaskForm):
    """Form for creating/editing certificates."""
    # Certificate identification
    year = IntegerField('Year', validators=[
        DataRequired(),
        NumberRange(min=2000, max=2100, message='Year must be between 2000 and 2100')
    ])
    cert_id = IntegerField('Certificate ID', validators=[
        DataRequired(),
        NumberRange(min=1001, max=9999, message='ID must be between 1001 and 9999')
    ])
    revision = IntegerField('Revision', default=1, validators=[
        DataRequired(),
        NumberRange(min=1, max=99)
    ])
    cert_date = DateField('Date', validators=[Optional()])

    # Test information
    test_project = StringField('Test Project', validators=[Optional()])
    project_name = StringField('Project Name', validators=[Optional()])
    test_standard = SelectField('Test Standard', choices=[
        ('', '-- Select --'),
        ('ASTM E8/E8M', 'ASTM E8/E8M - Tensile'),
        ('ISO 6892-1', 'ISO 6892-1 - Tensile'),
        ('ASTM E1875', 'ASTM E1875 - Sonic Resonance'),
        ('ASTM E647', 'ASTM E647 - FCGR'),
        ('ASTM E1820', 'ASTM E1820 - CTOD/J-Integral'),
        ('ASTM E1290', 'ASTM E1290 - CTOD'),
        ('ASTM E399', 'ASTM E399 - KIC'),
        ('ISO 6507-1', 'ISO 6507-1 - Vickers'),
        ('ASTM E92', 'ASTM E92 - Vickers'),
        ('Other', 'Other')
    ], validators=[Optional()])

    # Customer information
    customer = StringField('Customer', validators=[Optional()])
    customer_order = StringField('Customer Order', validators=[Optional()])

    # Product/Specimen information
    product = StringField('Product', validators=[Optional()])
    product_sn = StringField('Product S/N', validators=[Optional()])
    material = StringField('Material', validators=[Optional()])
    specimen_id = StringField('Specimen ID', validators=[Optional()])
    location_orientation = StringField('Location/Orientation', validators=[Optional()])
    temperature = StringField('Temperature', validators=[Optional()])

    # Comment
    comment = TextAreaField('Comment', validators=[Optional()])

    # Status
    reported = BooleanField('Reported')
    invoiced = BooleanField('Invoiced')

    submit = SubmitField('Save Certificate')


class CertificateSearchForm(FlaskForm):
    """Form for searching certificates."""
    search = StringField('Search', validators=[Optional()])
    year = SelectField('Year', choices=[], validators=[Optional()])
    submit = SubmitField('Search')


class CertificateLookupForm(FlaskForm):
    """Form for looking up certificate by number."""
    certificate_number = StringField('Certificate Number',
                                     validators=[DataRequired()],
                                     render_kw={'placeholder': 'DUR-2026-1001'})
    submit = SubmitField('Lookup')
