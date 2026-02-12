"""Heat treatment template forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

from app.models.simulation import HeatTreatmentTemplate


class TemplateForm(FlaskForm):
    """Form for creating/editing heat treatment templates."""
    name = StringField(
        'Template Name',
        validators=[DataRequired(), Length(max=200)],
        render_kw={'placeholder': 'e.g., Standard Q&T for 4140'}
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000)],
        render_kw={'placeholder': 'Describe when to use this template...', 'rows': 3}
    )
    category = SelectField(
        'Category',
        choices=[
            (HeatTreatmentTemplate.CATEGORY_QUENCH_TEMPER, 'Quench & Temper'),
            (HeatTreatmentTemplate.CATEGORY_NORMALIZING, 'Normalizing'),
            (HeatTreatmentTemplate.CATEGORY_STRESS_RELIEF, 'Stress Relief'),
            (HeatTreatmentTemplate.CATEGORY_ANNEALING, 'Annealing'),
            (HeatTreatmentTemplate.CATEGORY_HARDENING, 'Hardening'),
            (HeatTreatmentTemplate.CATEGORY_CUSTOM, 'Custom'),
        ]
    )
    is_public = BooleanField('Share publicly with all users')
    submit = SubmitField('Save Template')


class SaveAsTemplateForm(FlaskForm):
    """Form for saving a simulation's config as a template."""
    name = StringField(
        'Template Name',
        validators=[DataRequired(), Length(max=200)],
        render_kw={'placeholder': 'e.g., My Custom Heat Treatment'}
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000)],
        render_kw={'placeholder': 'Optional description...', 'rows': 2}
    )
    category = SelectField(
        'Category',
        choices=[
            (HeatTreatmentTemplate.CATEGORY_QUENCH_TEMPER, 'Quench & Temper'),
            (HeatTreatmentTemplate.CATEGORY_NORMALIZING, 'Normalizing'),
            (HeatTreatmentTemplate.CATEGORY_STRESS_RELIEF, 'Stress Relief'),
            (HeatTreatmentTemplate.CATEGORY_ANNEALING, 'Annealing'),
            (HeatTreatmentTemplate.CATEGORY_HARDENING, 'Hardening'),
            (HeatTreatmentTemplate.CATEGORY_CUSTOM, 'Custom'),
        ]
    )
    include_geometry = BooleanField('Include geometry settings')
    include_solver = BooleanField('Include solver settings')
    is_public = BooleanField('Share publicly')
    submit = SubmitField('Save as Template')
