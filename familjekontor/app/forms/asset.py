from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, DateField, DecimalField,
                     IntegerField, TextAreaField, SubmitField)
from wtforms.validators import DataRequired, Optional, Length, NumberRange

from app.models.asset import ASSET_CATEGORY_LABELS


CATEGORY_CHOICES = [('', '-- Välj kategori --')] + [
    (k, v) for k, v in ASSET_CATEGORY_LABELS.items()
]

METHOD_CHOICES = [
    ('straight_line', 'Linjär (rak)'),
    ('declining_balance', 'Degressiv (saldo)'),
]


class FixedAssetForm(FlaskForm):
    name = StringField('Namn', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Beskrivning', validators=[Optional(), Length(max=500)])
    asset_category = SelectField('Kategori', choices=CATEGORY_CHOICES,
                                 validators=[DataRequired()])
    purchase_date = DateField('Inköpsdatum', validators=[DataRequired()])
    purchase_amount = DecimalField('Inköpsbelopp', places=2, validators=[DataRequired()])
    supplier_name = StringField('Leverantör', validators=[Optional(), Length(max=200)])
    invoice_reference = StringField('Fakturareferens', validators=[Optional(), Length(max=100)])

    depreciation_method = SelectField('Avskrivningsmetod', choices=METHOD_CHOICES,
                                      validators=[DataRequired()])
    useful_life_months = IntegerField('Nyttjandeperiod (månader)',
                                      validators=[DataRequired(), NumberRange(min=1, max=1200)])
    residual_value = DecimalField('Restvärde', places=2, default=0,
                                  validators=[Optional()])
    depreciation_start = DateField('Avskrivningsstart', validators=[Optional()])

    asset_account = StringField('Tillgångskonto', validators=[Optional(), Length(max=10)])
    depreciation_account = StringField('Ack. avskrivningskonto',
                                       validators=[Optional(), Length(max=10)])
    expense_account = StringField('Avskrivningskostnad', validators=[Optional(), Length(max=10)])

    submit = SubmitField('Spara')


class DepreciationRunForm(FlaskForm):
    period_date = DateField('Period (slutdatum)', validators=[DataRequired()])
    submit = SubmitField('Generera avskrivningskörning')


class AssetDisposalForm(FlaskForm):
    disposal_date = DateField('Avyttringsdatum', validators=[DataRequired()])
    disposal_amount = DecimalField('Försäljningsbelopp', places=2, default=0,
                                   validators=[DataRequired()])
    submit = SubmitField('Avyttra tillgång')
