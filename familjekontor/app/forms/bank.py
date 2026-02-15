from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from app.utils.currency import currency_choices


class BankAccountForm(FlaskForm):
    bank_name = SelectField('Bank', choices=[
        ('SEB', 'SEB'),
        ('Swedbank', 'Swedbank'),
        ('Handelsbanken', 'Handelsbanken'),
        ('Nordea', 'Nordea'),
        ('Danske Bank', 'Danske Bank'),
        ('Annan', 'Annan'),
    ], validators=[DataRequired()])
    account_number = StringField('Kontonummer', validators=[DataRequired(), Length(max=30)])
    clearing_number = StringField('Clearingnummer', validators=[Optional(), Length(max=10)])
    iban = StringField('IBAN', validators=[Optional(), Length(max=34)])
    bic = StringField('BIC/SWIFT', validators=[Optional(), Length(max=11)])
    currency = SelectField('Valuta')
    ledger_account = StringField('Bokföringskonto', default='1930', validators=[Optional()])
    submit = SubmitField('Spara')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency.choices = currency_choices()


class BankImportForm(FlaskForm):
    bank_account_id = SelectField('Bankkonto', coerce=int, validators=[DataRequired()])
    bank_format = SelectField('Bankformat', choices=[
        ('generic', 'Generiskt (CSV)'),
        ('seb', 'SEB'),
        ('swedbank', 'Swedbank'),
    ], validators=[DataRequired()])
    file = FileField('CSV-fil', validators=[FileRequired(), FileAllowed(['csv', 'txt'], 'Bara CSV-filer.')])
    submit = SubmitField('Importera')


class ManualMatchForm(FlaskForm):
    verification_id = SelectField('Verifikation', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Matcha')
