"""Forms for real estate management."""

from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, IntegerField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Optional, Length


class RealEstateForm(FlaskForm):
    property_name = StringField('Fastighetsnamn', validators=[DataRequired(), Length(max=200)])
    fastighetsbeteckning = StringField('Fastighetsbeteckning', validators=[Optional(), Length(max=100)])
    street_address = StringField('Gatuadress', validators=[Optional(), Length(max=200)])
    postal_code = StringField('Postnummer', validators=[Optional(), Length(max=10)])
    city = StringField('Ort', validators=[Optional(), Length(max=100)])
    taxeringsvarde = DecimalField('Taxeringsvärde (SEK)', validators=[Optional()], default=0)
    taxeringsvarde_year = IntegerField('Taxeringsår', validators=[Optional()])
    property_tax_rate = DecimalField('Fastighetsskattesats', validators=[Optional()], default=0.0075, places=4)
    monthly_rent_target = DecimalField('Månadshyra mål (SEK)', validators=[Optional()], default=0)
    rent_account = StringField('Hyresintäktskonto', validators=[Optional(), Length(max=10)], default='3910')
    asset_id = SelectField('Kopplad anläggningstillgång', coerce=int, validators=[Optional()])
    notes = TextAreaField('Anteckningar', validators=[Optional()])
