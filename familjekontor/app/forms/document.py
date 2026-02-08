from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, Length


DOCUMENT_TYPE_CHOICES = [
    ('faktura', 'Faktura'),
    ('avtal', 'Avtal'),
    ('intyg', 'Intyg'),
    ('certificate', 'Registreringsdokument'),
    ('arsredovisning', 'Årsredovisning'),
    ('kvitto', 'Kvitto'),
    ('ovrigt', 'Övrigt'),
]


class DocumentUploadForm(FlaskForm):
    file = FileField('Fil', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx',
                      'xls', 'xlsx', 'csv', 'txt'], 'Otillåten filtyp.')
    ])
    document_type = SelectField('Dokumenttyp', choices=DOCUMENT_TYPE_CHOICES,
                                validators=[DataRequired()])
    description = StringField('Beskrivning', validators=[Optional(), Length(max=500)])
    valid_from = DateField('Giltig från', validators=[Optional()])
    expiry_date = DateField('Giltig till', validators=[Optional()])
    submit = SubmitField('Ladda upp')


class DocumentFilterForm(FlaskForm):
    doc_type = SelectField('Typ', choices=[
        ('', 'Alla'),
        ('faktura', 'Faktura'),
        ('avtal', 'Avtal'),
        ('intyg', 'Intyg'),
        ('certificate', 'Registreringsdokument'),
        ('arsredovisning', 'Årsredovisning'),
        ('kvitto', 'Kvitto'),
        ('ovrigt', 'Övrigt'),
    ], validators=[Optional()])
    search = StringField('Sök', validators=[Optional()])
    submit = SubmitField('Filtrera')


class DocumentAttachForm(FlaskForm):
    document_id = SelectField('Dokument', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Bifoga')
