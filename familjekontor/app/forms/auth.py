from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    username = StringField('Användarnamn', validators=[DataRequired()])
    password = PasswordField('Lösenord', validators=[DataRequired()])
    submit = SubmitField('Logga in')
