from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, DateField, TextAreaField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired, Optional


class VerificationRowForm(FlaskForm):
    class Meta:
        csrf = False

    account_id = SelectField('Konto', coerce=int, validators=[DataRequired()])
    debit = DecimalField('Debet', places=2, default=0, validators=[Optional()])
    credit = DecimalField('Kredit', places=2, default=0, validators=[Optional()])
    description = StringField('Beskrivning', validators=[Optional()])


class VerificationForm(FlaskForm):
    verification_date = DateField('Datum', validators=[DataRequired()])
    description = TextAreaField('Beskrivning', validators=[DataRequired()])
    verification_type = SelectField('Typ', choices=[
        ('manual', 'Manuell'),
        ('supplier', 'Leverantör'),
        ('customer', 'Kund'),
        ('bank', 'Bank'),
        ('salary', 'Lön'),
    ])
    submit = SubmitField('Spara verifikation')
