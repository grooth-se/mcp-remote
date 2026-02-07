from datetime import date
from flask_wtf import FlaskForm
from wtforms import (
    SelectField, IntegerField, DecimalField, StringField,
    TextAreaField, DateField, SubmitField,
)
from wtforms.validators import DataRequired, Optional, NumberRange


class VATGenerateForm(FlaskForm):
    """Select a period to generate a VAT report."""
    period = SelectField('Period', validators=[DataRequired()])
    submit = SubmitField('Beräkna moms')


class VATFinalizeForm(FlaskForm):
    """Confirm filing of a VAT report."""
    submit = SubmitField('Markera som inlämnad')


class DeadlineForm(FlaskForm):
    """Create a manual deadline."""
    deadline_type = SelectField('Typ', choices=[
        ('vat', 'Moms'),
        ('employer_tax', 'Arbetsgivaravgifter'),
        ('corporate_tax', 'Bolagsskatt'),
        ('annual_report', 'Årsredovisning'),
        ('tax_return', 'Inkomstdeklaration'),
    ], validators=[DataRequired()])
    description = StringField('Beskrivning', validators=[DataRequired()])
    due_date = DateField('Förfallodatum', validators=[DataRequired()])
    reminder_date = DateField('Påminnelsedatum', validators=[Optional()])
    period_label = StringField('Period', validators=[Optional()])
    notes = TextAreaField('Anteckningar', validators=[Optional()])
    submit = SubmitField('Spara')


class DeadlineSeedForm(FlaskForm):
    """Auto-generate deadlines for a year."""
    year = IntegerField('År', validators=[
        DataRequired(),
        NumberRange(min=2020, max=2050),
    ], default=date.today().year)
    submit = SubmitField('Generera deadlines')


class TaxPaymentForm(FlaskForm):
    """Record a tax payment."""
    payment_type = SelectField('Typ', choices=[
        ('vat', 'Moms'),
        ('employer_tax', 'Arbetsgivaravgifter'),
        ('corporate_tax', 'Bolagsskatt'),
        ('preliminary_tax', 'Preliminär skatt'),
    ], validators=[DataRequired()])
    amount = DecimalField('Belopp (SEK)', places=2, validators=[DataRequired()])
    payment_date = DateField('Betalningsdatum', validators=[DataRequired()])
    reference = StringField('Referens/OCR', validators=[Optional()])
    deadline_id = SelectField('Kopplad deadline', coerce=int, validators=[Optional()])
    notes = TextAreaField('Anteckningar', validators=[Optional()])
    submit = SubmitField('Spara betalning')

    def __init__(self, *args, deadline_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if deadline_choices:
            self.deadline_id.choices = [(0, '-- Ingen --')] + deadline_choices
        else:
            self.deadline_id.choices = [(0, '-- Ingen --')]


class EmployerTaxPeriodForm(FlaskForm):
    """Select period for employer tax summary."""
    year = IntegerField('År', default=date.today().year)
    submit = SubmitField('Visa')
