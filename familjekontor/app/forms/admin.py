from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, Length, ValidationError


def strong_password(form, field):
    if not field.data:
        return
    if field.data.isdigit():
        raise ValidationError('Lösenordet får inte bestå av enbart siffror.')
    if field.data.isalpha():
        raise ValidationError('Lösenordet måste innehålla minst en siffra.')


class UserForm(FlaskForm):
    username = StringField('Användarnamn', validators=[DataRequired(), Length(max=80)])
    email = StringField('E-post', validators=[DataRequired(), Email()])
    password = PasswordField('Lösenord', validators=[Optional(), Length(min=8), strong_password])
    role = SelectField('Roll', choices=[
        ('user', 'Användare'), ('admin', 'Administratör'), ('readonly', 'Läsbehörighet'),
    ])
    submit = SubmitField('Spara')
