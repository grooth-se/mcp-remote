from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, DateField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
from app.utils.currency import currency_choices


class RecurringInvoiceTemplateForm(FlaskForm):
    customer_id = SelectField('Kund', coerce=int, validators=[DataRequired()])
    name = StringField('Mallnamn', validators=[DataRequired(), Length(max=200)])
    currency = SelectField('Valuta')
    vat_type = SelectField('Momstyp', choices=[
        ('standard', 'Standard 25%'),
        ('reverse_charge', 'Omvänd skattskyldighet'),
        ('export', 'Export (momsfri)'),
    ])
    interval = SelectField('Intervall', choices=[
        ('monthly', 'Månad'),
        ('quarterly', 'Kvartal'),
        ('yearly', 'År'),
    ], validators=[DataRequired()])
    payment_terms = IntegerField('Betalningsvillkor (dagar)', default=30,
                                 validators=[DataRequired(), NumberRange(min=0, max=365)])
    start_date = DateField('Startdatum', validators=[DataRequired()])
    end_date = DateField('Slutdatum (valfritt)', validators=[Optional()])
    submit = SubmitField('Spara')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency.choices = currency_choices()


class RecurringLineItemForm(FlaskForm):
    description = StringField('Beskrivning', validators=[DataRequired(), Length(max=500)])
    quantity = DecimalField('Antal', places=2, default=1,
                            validators=[DataRequired(), NumberRange(min=0)])
    unit = SelectField('Enhet', choices=[
        ('st', 'st'),
        ('tim', 'tim'),
        ('m', 'm'),
        ('kg', 'kg'),
        ('l', 'l'),
    ], default='st')
    unit_price = DecimalField('À-pris', places=2,
                              validators=[DataRequired(), NumberRange(min=0)])
    vat_rate = SelectField('Moms %', choices=[
        ('25', '25%'),
        ('12', '12%'),
        ('6', '6%'),
        ('0', '0%'),
    ], default='25')
    submit = SubmitField('Lägg till rad')
