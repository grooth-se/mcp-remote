from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, DateField, SubmitField
from wtforms.validators import DataRequired
from app.utils.currency import SUPPORTED_CURRENCIES


def foreign_currency_choices():
    """Currency choices excluding SEK."""
    return [(code, f'{code} - {info["name"]}')
            for code, info in SUPPORTED_CURRENCIES.items() if code != 'SEK']


class ExchangeRateForm(FlaskForm):
    currency_code = SelectField('Valuta', validators=[DataRequired()])
    rate_date = DateField('Datum', validators=[DataRequired()])
    rate = DecimalField('Kurs (1 utl. = X SEK)', places=6, validators=[DataRequired()])
    submit = SubmitField('Spara kurs')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_code.choices = foreign_currency_choices()


class FetchRatesForm(FlaskForm):
    currency_code = SelectField('Valuta', validators=[DataRequired()])
    start_date = DateField('Från', validators=[DataRequired()])
    end_date = DateField('Till', validators=[DataRequired()])
    submit = SubmitField('Hämta kurser')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_code.choices = [('ALL', 'Alla valutor')] + foreign_currency_choices()
