from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, DateField, DecimalField,
                     IntegerField, TextAreaField, BooleanField, SubmitField)
from wtforms.validators import DataRequired, Optional, Length, NumberRange

from app.models.governance import BOARD_ROLE_LABELS, MEETING_TYPE_LABELS, ACQUISITION_TYPE_LABELS


ROLE_CHOICES = [('', '-- Välj roll --')] + [
    (k, v) for k, v in BOARD_ROLE_LABELS.items()
]

MEETING_TYPE_CHOICES = [
    (k, v) for k, v in MEETING_TYPE_LABELS.items()
]

ACQUISITION_CHOICES = [
    (k, v) for k, v in ACQUISITION_TYPE_LABELS.items()
]


class BoardMemberForm(FlaskForm):
    name = StringField('Namn', validators=[DataRequired(), Length(max=200)])
    personal_number = StringField('Personnummer', validators=[Optional(), Length(max=13)])
    role = SelectField('Roll', choices=ROLE_CHOICES, validators=[DataRequired()])
    title = StringField('Titel', validators=[Optional(), Length(max=100)])
    appointed_date = DateField('Tillträdesdag', validators=[DataRequired()])
    end_date = DateField('Avgångsdag', validators=[Optional()])
    appointed_by = StringField('Utsedd av', validators=[Optional(), Length(max=100)])
    email = StringField('E-post', validators=[Optional(), Length(max=120)])
    phone = StringField('Telefon', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Spara')


class ShareClassForm(FlaskForm):
    name = StringField('Aktieslag', validators=[DataRequired(), Length(max=50)])
    votes_per_share = IntegerField('Röster per aktie', default=1,
                                    validators=[DataRequired(), NumberRange(min=1)])
    par_value = DecimalField('Kvotvärde (SEK)', places=2, validators=[Optional()])
    total_shares = IntegerField('Totalt antal aktier', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Spara')


class ShareholderForm(FlaskForm):
    name = StringField('Namn', validators=[DataRequired(), Length(max=200)])
    personal_or_org_number = StringField('Person-/Org.nummer', validators=[Optional(), Length(max=20)])
    address = StringField('Adress', validators=[Optional(), Length(max=300)])
    is_company = BooleanField('Är juridisk person')
    submit = SubmitField('Spara')


class HoldingForm(FlaskForm):
    share_class_id = SelectField('Aktieslag', coerce=int, validators=[DataRequired()])
    shares = IntegerField('Antal aktier', validators=[DataRequired(), NumberRange(min=1)])
    acquired_date = DateField('Förvärvsdatum', validators=[DataRequired()])
    acquisition_type = SelectField('Förvärvstyp', choices=ACQUISITION_CHOICES,
                                    validators=[DataRequired()])
    price_per_share = DecimalField('Pris per aktie (SEK)', places=2, validators=[Optional()])
    note = TextAreaField('Anteckning', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Lägg till')


class DividendForm(FlaskForm):
    fiscal_year_id = SelectField('Räkenskapsår', coerce=int, validators=[DataRequired()])
    decision_date = DateField('Beslutsdatum', validators=[DataRequired()])
    total_amount = DecimalField('Totalt belopp (SEK)', places=2, validators=[DataRequired()])
    amount_per_share = DecimalField('Belopp per aktie', places=4, validators=[Optional()])
    share_class_id = SelectField('Aktieslag', coerce=int, validators=[Optional()])
    record_date = DateField('Avstämningsdag', validators=[Optional()])
    payment_date = DateField('Utbetalningsdag', validators=[Optional()])
    submit = SubmitField('Spara')


class AGMForm(FlaskForm):
    meeting_date = DateField('Mötesdatum', validators=[DataRequired()])
    meeting_type = SelectField('Mötestyp', choices=MEETING_TYPE_CHOICES,
                                validators=[DataRequired()])
    fiscal_year_id = SelectField('Avser räkenskapsår', coerce=int, validators=[Optional()])
    chairman = StringField('Ordförande', validators=[Optional(), Length(max=200)])
    minutes_taker = StringField('Protokollförare', validators=[Optional(), Length(max=200)])
    attendees = TextAreaField('Närvarande', validators=[Optional()])
    resolutions = TextAreaField('Beslut', validators=[Optional()])
    submit = SubmitField('Spara')
