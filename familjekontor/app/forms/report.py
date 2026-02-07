from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import Optional


class ReportFilterForm(FlaskForm):
    fiscal_year_id = SelectField('Räkenskapsår', coerce=int)
    account_number = StringField('Kontonummer', validators=[Optional()])
    submit = SubmitField('Visa rapport')
