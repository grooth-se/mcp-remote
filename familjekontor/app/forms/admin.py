from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, Length


class UserForm(FlaskForm):
    username = StringField('Användarnamn', validators=[DataRequired(), Length(max=80)])
    email = StringField('E-post', validators=[DataRequired(), Email()])
    password = PasswordField('Lösenord', validators=[Optional(), Length(min=6)])
    role = SelectField('Roll', choices=[
        ('user', 'Användare'), ('admin', 'Administratör'), ('readonly', 'Läsbehörighet'),
    ])
    submit = SubmitField('Spara')
