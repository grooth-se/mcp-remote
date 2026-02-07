from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import SelectField, SubmitField


class SIEImportForm(FlaskForm):
    file = FileField('SIE-fil', validators=[
        FileRequired('Välj en SIE-fil'),
    ])
    fiscal_year_id = SelectField('Räkenskapsår (valfritt)', coerce=int)
    submit = SubmitField('Importera')


class SIEExportForm(FlaskForm):
    fiscal_year_id = SelectField('Räkenskapsår', coerce=int)
    submit = SubmitField('Exportera SIE4')
