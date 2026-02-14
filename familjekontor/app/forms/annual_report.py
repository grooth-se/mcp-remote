from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, DateField, SubmitField
from wtforms.validators import Optional, Length


class AnnualReportForm(FlaskForm):
    # Förvaltningsberättelse
    verksamhet = TextAreaField('Verksamheten', validators=[Optional(), Length(max=5000)])
    vasentliga_handelser = TextAreaField(
        'Väsentliga händelser under räkenskapsåret',
        validators=[Optional(), Length(max=5000)])
    handelser_efter_fy = TextAreaField(
        'Väsentliga händelser efter räkenskapsårets slut',
        validators=[Optional(), Length(max=3000)])
    framtida_utveckling = TextAreaField(
        'Förväntad framtida utveckling',
        validators=[Optional(), Length(max=3000)])
    resultatdisposition = TextAreaField(
        'Resultatdisposition',
        validators=[Optional(), Length(max=3000)])

    # Noter
    redovisningsprinciper = TextAreaField(
        'Not 1: Redovisningsprinciper',
        validators=[Optional(), Length(max=5000)])
    extra_noter = TextAreaField(
        'Övriga noter',
        validators=[Optional(), Length(max=10000)])

    # Underskrifter
    board_members = TextAreaField(
        'Styrelseledamöter (en per rad)',
        validators=[Optional(), Length(max=2000)])
    signing_location = StringField('Ort', validators=[Optional(), Length(max=200)])
    signing_date = DateField('Datum för underskrift', validators=[Optional()])

    submit = SubmitField('Spara utkast')
