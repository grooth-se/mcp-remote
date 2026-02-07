from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, Length


class DocumentUploadForm(FlaskForm):
    file = FileField('Fil', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx',
                      'xls', 'xlsx', 'csv', 'txt'], 'Otillaten filtyp.')
    ])
    document_type = SelectField('Dokumenttyp', choices=[
        ('faktura', 'Faktura'),
        ('avtal', 'Avtal'),
        ('intyg', 'Intyg'),
        ('arsredovisning', 'Arsredovisning'),
        ('kvitto', 'Kvitto'),
        ('ovrigt', 'Ovrigt'),
    ], validators=[DataRequired()])
    description = StringField('Beskrivning', validators=[Optional(), Length(max=500)])
    expiry_date = DateField('Utgar', validators=[Optional()])
    submit = SubmitField('Ladda upp')


class DocumentFilterForm(FlaskForm):
    doc_type = SelectField('Typ', choices=[
        ('', 'Alla'),
        ('faktura', 'Faktura'),
        ('avtal', 'Avtal'),
        ('intyg', 'Intyg'),
        ('arsredovisning', 'Arsredovisning'),
        ('kvitto', 'Kvitto'),
        ('ovrigt', 'Ovrigt'),
    ], validators=[Optional()])
    search = StringField('Sok', validators=[Optional()])
    submit = SubmitField('Filtrera')


class DocumentAttachForm(FlaskForm):
    document_id = SelectField('Dokument', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Bifoga')
