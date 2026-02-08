from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField, DecimalField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from app.utils.currency import currency_choices


class SupplierForm(FlaskForm):
    name = StringField('Namn', validators=[DataRequired(), Length(max=200)])
    org_number = StringField('Org.nummer', validators=[Optional()])
    default_account = StringField('Standardkonto', validators=[Optional()])
    payment_terms = StringField('Betalningsvillkor (dagar)', default='30')
    bankgiro = StringField('Bankgiro', validators=[Optional()])
    plusgiro = StringField('PlusGiro', validators=[Optional()])
    iban = StringField('IBAN', validators=[Optional()])
    bic = StringField('BIC', validators=[Optional()])
    submit = SubmitField('Spara')


class SupplierInvoiceForm(FlaskForm):
    supplier_id = SelectField('Leverantör', coerce=int, validators=[DataRequired()])
    invoice_pdf = FileField('Faktura-PDF', validators=[
        Optional(), FileAllowed(['pdf'], 'Endast PDF-filer.')
    ])
    invoice_number = StringField('Fakturanummer', validators=[DataRequired()])
    invoice_date = DateField('Fakturadatum', validators=[DataRequired()])
    due_date = DateField('Förfallodatum', validators=[DataRequired()])
    amount_excl_vat = DecimalField('Belopp exkl. moms', places=2, validators=[DataRequired()])
    vat_amount = DecimalField('Moms', places=2, default=0, validators=[Optional()])
    total_amount = DecimalField('Totalbelopp', places=2, validators=[DataRequired()])
    currency = SelectField('Valuta')
    submit = SubmitField('Spara')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency.choices = currency_choices()


class CustomerForm(FlaskForm):
    name = StringField('Namn', validators=[DataRequired(), Length(max=200)])
    org_number = StringField('Org.nummer', validators=[Optional()])
    country = SelectField('Land', choices=[
        ('SE', 'Sverige'), ('NO', 'Norge'), ('DK', 'Danmark'), ('FI', 'Finland'),
        ('DE', 'Tyskland'), ('GB', 'Storbritannien'), ('US', 'USA'),
    ])
    vat_number = StringField('Momsreg.nr', validators=[Optional()])
    address = StringField('Adress', validators=[Optional()])
    postal_code = StringField('Postnummer', validators=[Optional()])
    city = StringField('Ort', validators=[Optional()])
    email = StringField('E-post', validators=[Optional()])
    payment_terms = StringField('Betalningsvillkor (dagar)', default='30')
    default_currency = SelectField('Standardvaluta')
    submit = SubmitField('Spara')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_currency.choices = currency_choices()


class CustomerInvoiceForm(FlaskForm):
    customer_id = SelectField('Kund', coerce=int, validators=[DataRequired()])
    invoice_number = StringField('Fakturanummer', validators=[DataRequired()])
    invoice_date = DateField('Fakturadatum', validators=[DataRequired()])
    due_date = DateField('Förfallodatum', validators=[DataRequired()])
    currency = SelectField('Valuta')
    amount_excl_vat = DecimalField('Belopp exkl. moms', places=2, validators=[DataRequired()])
    vat_amount = DecimalField('Moms', places=2, default=0, validators=[Optional()])
    total_amount = DecimalField('Totalbelopp', places=2, validators=[DataRequired()])
    vat_type = SelectField('Momstyp', choices=[
        ('standard', 'Standard 25%'),
        ('reverse_charge', 'Omvänd skattskyldighet'),
        ('export', 'Export (momsfri)'),
    ])
    submit = SubmitField('Spara')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency.choices = currency_choices()


class InvoiceLineItemForm(FlaskForm):
    description = StringField('Beskrivning', validators=[DataRequired(), Length(max=500)])
    quantity = DecimalField('Antal', places=2, default=1, validators=[DataRequired()])
    unit = SelectField('Enhet', choices=[
        ('st', 'st'),
        ('tim', 'tim'),
        ('m', 'm'),
        ('kg', 'kg'),
        ('l', 'l'),
    ], default='st')
    unit_price = DecimalField('À-pris', places=2, validators=[DataRequired()])
    vat_rate = SelectField('Moms %', choices=[
        ('25', '25%'),
        ('12', '12%'),
        ('6', '6%'),
        ('0', '0%'),
    ], default='25')
    submit = SubmitField('Lägg till rad')
