from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, SelectField, IntegerField, DateField, SubmitField
from wtforms.validators import DataRequired, Length, Optional
from app.utils.currency import currency_choices


class CompanyForm(FlaskForm):
    name = StringField('Företagsnamn', validators=[DataRequired(), Length(max=200)])
    org_number = StringField('Org.nummer', validators=[DataRequired(), Length(min=10, max=13)])
    company_type = SelectField('Bolagsform', choices=[('AB', 'Aktiebolag'), ('HB', 'Handelsbolag')])
    accounting_standard = SelectField('Redovisningsstandard', choices=[('K2', 'K2'), ('K3', 'K3')])
    fiscal_year_start = SelectField('Räkenskapsår startar', coerce=int, choices=[
        (1, 'Januari'), (2, 'Februari'), (3, 'Mars'), (4, 'April'),
        (5, 'Maj'), (6, 'Juni'), (7, 'Juli'), (8, 'Augusti'),
        (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'December'),
    ])
    vat_period = SelectField('Momsperiod', choices=[
        ('monthly', 'Månadsvis'), ('quarterly', 'Kvartalsvis'), ('annual', 'Årsvis'),
    ])
    base_currency = SelectField('Basvaluta')
    street_address = StringField('Gatuadress', validators=[Optional(), Length(max=300)])
    postal_code = StringField('Postnummer', validators=[Optional(), Length(max=10)])
    city = StringField('Ort', validators=[Optional(), Length(max=100)])
    country = StringField('Land', validators=[Optional(), Length(max=100)], default='Sverige')
    logo = FileField('Logotyp', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'svg'], 'Endast bildfiler.'),
    ])
    theme_color = StringField('Färgtema', validators=[Optional(), Length(max=7)])
    submit = SubmitField('Spara')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_currency.choices = currency_choices()


class FiscalYearForm(FlaskForm):
    year = IntegerField('År', validators=[DataRequired()])
    start_date = StringField('Startdatum (YYYY-MM-DD)', validators=[DataRequired()])
    end_date = StringField('Slutdatum (YYYY-MM-DD)', validators=[DataRequired()])
    submit = SubmitField('Skapa räkenskapsår')


class CertificateUploadForm(FlaskForm):
    file = FileField('Fil', validators=[FileRequired('Välj en fil.')])
    description = StringField('Beskrivning', validators=[Optional(), Length(max=500)])
    expiry_date = DateField('Utgångsdatum', validators=[Optional()])
    submit = SubmitField('Ladda upp')
