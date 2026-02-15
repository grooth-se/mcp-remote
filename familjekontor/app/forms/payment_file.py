from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, StringField, SubmitField
from wtforms.validators import DataRequired


class PaymentBatchForm(FlaskForm):
    bank_account_id = SelectField('Bankkonto', coerce=int, validators=[DataRequired()])
    file_format = SelectField('Filformat', choices=[
        ('pain001', 'ISO 20022 pain.001 (SEB, Nordea)'),
        ('bankgirot', 'Bankgirot (Leverantörsbetalningar)'),
    ], validators=[DataRequired()])
    execution_date = DateField('Betalningsdatum', validators=[DataRequired()])
    invoice_ids = StringField('Valda fakturor')  # Hidden, comma-separated IDs
    submit = SubmitField('Skapa betalningsbatch')
