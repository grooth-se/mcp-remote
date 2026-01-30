"""Admin forms for user management."""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, EqualTo, ValidationError

from app.models import User, ROLES, ROLE_LABELS


class UserCreateForm(FlaskForm):
    """Form for creating a new user."""
    username = StringField('Username', validators=[
        DataRequired(),
        Length(3, 80, message='Username must be 3-80 characters')
    ])
    full_name = StringField('Full Name', validators=[
        DataRequired(),
        Length(2, 120, message='Full name must be 2-120 characters')
    ])
    email = StringField('Email', validators=[
        Optional(),
        Email(message='Invalid email address')
    ])
    role = SelectField('Role', choices=[
        (role, ROLE_LABELS[role]) for role in ROLES
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(6, 128, message='Password must be at least 6 characters')
    ])
    password2 = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Create User')

    def validate_username(self, field):
        """Check if username already exists."""
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already in use.')


class UserEditForm(FlaskForm):
    """Form for editing an existing user."""
    username = StringField('Username', validators=[
        DataRequired(),
        Length(3, 80, message='Username must be 3-80 characters')
    ])
    full_name = StringField('Full Name', validators=[
        DataRequired(),
        Length(2, 120, message='Full name must be 2-120 characters')
    ])
    email = StringField('Email', validators=[
        Optional(),
        Email(message='Invalid email address')
    ])
    role = SelectField('Role', choices=[
        (role, ROLE_LABELS[role]) for role in ROLES
    ])
    is_active = BooleanField('Active')
    submit = SubmitField('Save Changes')

    def __init__(self, original_username=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, field):
        """Check if username already exists (excluding current user)."""
        if field.data != self.original_username:
            if User.query.filter_by(username=field.data).first():
                raise ValidationError('Username already in use.')


class PasswordChangeForm(FlaskForm):
    """Form for changing a user's password."""
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(6, 128, message='Password must be at least 6 characters')
    ])
    password2 = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Change Password')
