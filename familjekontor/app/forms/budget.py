from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired


class BudgetFilterForm(FlaskForm):
    fiscal_year_id = SelectField('Rakenskapsar', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Visa')


class BudgetCopyForm(FlaskForm):
    source_fiscal_year_id = SelectField('Kopiera fran', coerce=int, validators=[DataRequired()])
    target_fiscal_year_id = SelectField('Kopiera till', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Kopiera budget')
