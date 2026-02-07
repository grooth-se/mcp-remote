from datetime import date
from flask_wtf import FlaskForm
from wtforms import (
    StringField, IntegerField, DecimalField, SelectField,
    DateField, TextAreaField, BooleanField, SubmitField,
)
from wtforms.validators import DataRequired, Optional, NumberRange, Email, Length


class EmployeeForm(FlaskForm):
    """Create/edit an employee."""
    personal_number = StringField('Personnummer', validators=[
        DataRequired(), Length(min=10, max=20),
    ])
    first_name = StringField('Förnamn', validators=[DataRequired(), Length(max=100)])
    last_name = StringField('Efternamn', validators=[DataRequired(), Length(max=100)])
    email = StringField('E-post', validators=[Optional(), Email()])
    employment_start = DateField('Anställningsdatum', validators=[DataRequired()])
    employment_end = DateField('Slutdatum', validators=[Optional()])
    monthly_salary = DecimalField('Månadslön (SEK)', places=2, validators=[
        DataRequired(), NumberRange(min=0),
    ])
    tax_table = StringField('Skattetabell', validators=[
        DataRequired(), Length(max=10),
    ], default='33')
    tax_column = IntegerField('Skattekolumn', validators=[
        DataRequired(), NumberRange(min=1, max=6),
    ], default=1)
    pension_plan = SelectField('Pensionsplan', choices=[
        ('ITP1', 'ITP1'),
        ('ITP2', 'ITP2'),
        ('none', 'Ingen'),
    ], validators=[DataRequired()])
    bank_clearing = StringField('Clearingnummer', validators=[Optional(), Length(max=10)])
    bank_account = StringField('Kontonummer', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Spara')


class SalaryRunForm(FlaskForm):
    """Create a new salary run."""
    period_year = IntegerField('År', validators=[
        DataRequired(), NumberRange(min=2020, max=2050),
    ], default=date.today().year)
    period_month = SelectField('Månad', coerce=int, choices=[
        (1, 'Januari'), (2, 'Februari'), (3, 'Mars'),
        (4, 'April'), (5, 'Maj'), (6, 'Juni'),
        (7, 'Juli'), (8, 'Augusti'), (9, 'September'),
        (10, 'Oktober'), (11, 'November'), (12, 'December'),
    ], validators=[DataRequired()])
    submit = SubmitField('Skapa löneköring')


class SalaryEntryEditForm(FlaskForm):
    """Override individual salary entry values."""
    gross_salary = DecimalField('Bruttolön (SEK)', places=2, validators=[
        DataRequired(), NumberRange(min=0),
    ])
    tax_deduction = DecimalField('Skatteavdrag (SEK)', places=2, validators=[
        DataRequired(), NumberRange(min=0),
    ])
    other_deductions = DecimalField('Övriga avdrag (SEK)', places=2, validators=[
        Optional(),
    ], default=0)
    other_additions = DecimalField('Övriga tillägg (SEK)', places=2, validators=[
        Optional(),
    ], default=0)
    notes = TextAreaField('Anteckningar', validators=[Optional()])
    submit = SubmitField('Spara')


class SalaryPayForm(FlaskForm):
    """Mark a salary run as paid."""
    paid_date = DateField('Betalningsdatum', validators=[DataRequired()],
                          default=date.today)
    submit = SubmitField('Markera som betald')


class CollectumPeriodForm(FlaskForm):
    """Select period for Collectum pension report."""
    period_year = IntegerField('År', validators=[
        DataRequired(), NumberRange(min=2020, max=2050),
    ], default=date.today().year)
    period_month = SelectField('Månad', coerce=int, choices=[
        (1, 'Januari'), (2, 'Februari'), (3, 'Mars'),
        (4, 'April'), (5, 'Maj'), (6, 'Juni'),
        (7, 'Juli'), (8, 'Augusti'), (9, 'September'),
        (10, 'Oktober'), (11, 'November'), (12, 'December'),
    ], validators=[DataRequired()])
    submit = SubmitField('Visa rapport')
