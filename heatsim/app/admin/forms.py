"""Admin forms for user management."""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError

from app.models import User, ROLES, ROLE_LABELS


class CreateUserForm(FlaskForm):
    """Form for creating a new user."""
    username = StringField('Username', validators=[DataRequired(), Length(3, 80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(6, 128)])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match')
    ])
    role = SelectField('Role', choices=[(r, ROLE_LABELS[r]) for r in ROLES])
    submit = SubmitField('Create User')

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already exists.')


class EditUserForm(FlaskForm):
    """Form for editing a user (role, optional password reset)."""
    role = SelectField('Role', choices=[(r, ROLE_LABELS[r]) for r in ROLES])
    new_password = PasswordField('New Password (leave empty to keep current)', validators=[
        Optional(), Length(6, 128)
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Save Changes')
