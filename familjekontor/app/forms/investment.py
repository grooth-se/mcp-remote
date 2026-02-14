from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, SelectField, DateField, DecimalField,
                     TextAreaField, SubmitField)
from wtforms.validators import DataRequired, Optional, Length

from app.models.investment import (
    PORTFOLIO_TYPE_LABELS, INSTRUMENT_TYPE_LABELS, TRANSACTION_TYPE_LABELS,
)

PORTFOLIO_TYPE_CHOICES = [
    (k, v) for k, v in PORTFOLIO_TYPE_LABELS.items()
]

INSTRUMENT_TYPE_CHOICES = [('', '-- Välj --')] + [
    (k, v) for k, v in INSTRUMENT_TYPE_LABELS.items()
]

TRANSACTION_TYPE_CHOICES = [('', '-- Välj typ --')] + [
    (k, v) for k, v in TRANSACTION_TYPE_LABELS.items()
]


class PortfolioForm(FlaskForm):
    name = StringField('Namn', validators=[DataRequired(), Length(max=200)])
    portfolio_type = SelectField('Typ', choices=PORTFOLIO_TYPE_CHOICES,
                                  validators=[DataRequired()])
    broker = StringField('Mäklare', validators=[Optional(), Length(max=100)])
    account_number = StringField('Kontonummer', validators=[Optional(), Length(max=50)])
    currency = StringField('Valuta', default='SEK', validators=[Optional(), Length(max=3)])
    ledger_account = StringField('Bokföringskonto (BAS)', validators=[Optional(), Length(max=10)])
    submit = SubmitField('Spara')


class TransactionForm(FlaskForm):
    transaction_type = SelectField('Transaktionstyp', choices=TRANSACTION_TYPE_CHOICES,
                                    validators=[DataRequired()])
    transaction_date = DateField('Datum', validators=[DataRequired()])
    name = StringField('Värdepapper', validators=[Optional(), Length(max=200)])
    isin = StringField('ISIN', validators=[Optional(), Length(max=12)])
    ticker = StringField('Ticker', validators=[Optional(), Length(max=20)])
    instrument_type = SelectField('Instrumenttyp', choices=INSTRUMENT_TYPE_CHOICES,
                                   validators=[Optional()])
    quantity = DecimalField('Antal', places=4, validators=[Optional()])
    price_per_unit = DecimalField('Kurs', places=4, validators=[Optional()])
    amount = DecimalField('Belopp', places=2, validators=[DataRequired()])
    commission = DecimalField('Courtage', places=2, default=0, validators=[Optional()])
    currency = StringField('Valuta', default='SEK', validators=[Optional(), Length(max=3)])
    exchange_rate = DecimalField('Växelkurs', places=6, default=1, validators=[Optional()])
    note = TextAreaField('Anteckning', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Registrera')


class ImportForm(FlaskForm):
    csv_file = FileField('Nordnet CSV-fil', validators=[
        DataRequired(),
        FileAllowed(['csv', 'txt'], 'Bara CSV-filer'),
    ])
    submit = SubmitField('Importera')


class PriceUpdateForm(FlaskForm):
    current_price = DecimalField('Aktuellt pris', places=4, validators=[DataRequired()])
    price_date = DateField('Datum', validators=[Optional()])
    submit = SubmitField('Uppdatera')
