from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class ConsolidationGroupForm(FlaskForm):
    name = StringField('Gruppnamn', validators=[DataRequired(), Length(max=200)])
    parent_company_id = SelectField('Moderforetag', coerce=int, validators=[DataRequired()])
    description = TextAreaField('Beskrivning', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Spara')


class AddMemberForm(FlaskForm):
    company_id = SelectField('Foretag', coerce=int, validators=[DataRequired()])
    ownership_pct = DecimalField('Agarandel %', default=100, places=2,
                                 validators=[DataRequired(), NumberRange(min=0, max=100)])
    submit = SubmitField('Lagg till')


class ConsolidationReportForm(FlaskForm):
    fiscal_year_year = SelectField('Rakenskapsar', coerce=int, validators=[DataRequired()])
    report_type = SelectField('Rapporttyp', choices=[
        ('pnl', 'Resultatrakning'),
        ('balance', 'Balansrakning'),
    ], validators=[DataRequired()])
    submit = SubmitField('Generera rapport')


class EliminationForm(FlaskForm):
    from_company_id = SelectField('Fran foretag', coerce=int, validators=[DataRequired()])
    to_company_id = SelectField('Till foretag', coerce=int, validators=[DataRequired()])
    account_number = StringField('Kontonummer', validators=[DataRequired()])
    amount = DecimalField('Belopp', places=2, validators=[DataRequired()])
    description = StringField('Beskrivning', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Skapa eliminering')
