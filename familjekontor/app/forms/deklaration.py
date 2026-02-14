"""Forms for Deklaration (yearly tax return)."""

from flask_wtf import FlaskForm
from wtforms import (
    SelectField, DecimalField, TextAreaField, SubmitField, StringField,
)
from wtforms.validators import DataRequired, Optional, NumberRange


class TaxReturnCreateForm(FlaskForm):
    """Form to create a new tax return for a fiscal year."""
    fiscal_year_id = SelectField('Räkenskapsår', coerce=int,
                                 validators=[DataRequired()])
    submit = SubmitField('Skapa deklaration')


class TaxReturnAdjustmentsForm(FlaskForm):
    """Form to edit manual adjustments on a tax return."""
    non_deductible_expenses = DecimalField('Ej avdragsgilla kostnader',
                                           default=0, validators=[Optional()])
    non_taxable_income = DecimalField('Ej skattepliktiga intäkter',
                                      default=0, validators=[Optional()])
    depreciation_tax_diff = DecimalField('Skillnad avskrivning (bokförd vs skattemässig)',
                                         default=0, validators=[Optional()])
    previous_deficit = DecimalField('Underskott föregående år',
                                    default=0, validators=[Optional()])
    notes = TextAreaField('Anteckningar', validators=[Optional()])
    submit = SubmitField('Spara justeringar')


class AdjustmentLineForm(FlaskForm):
    """Form to add a custom adjustment line item."""
    adjustment_type = SelectField('Typ', choices=[
        ('add', 'Tillkommer'),
        ('deduct', 'Avgår'),
    ], validators=[DataRequired()])
    description = StringField('Beskrivning', validators=[DataRequired()])
    amount = DecimalField('Belopp', validators=[DataRequired(),
                          NumberRange(min=0.01, message='Belopp måste vara > 0')])
    sru_code = StringField('SRU-kod', validators=[Optional()])
    submit = SubmitField('Lägg till justering')
