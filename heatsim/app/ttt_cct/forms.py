"""WTForms for TTT/CCT parameter management."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    FloatField, SelectField, TextAreaField, StringField,
    SubmitField, HiddenField
)
from wtforms.validators import DataRequired, Optional, NumberRange


class TTTParametersForm(FlaskForm):
    """Form for editing TTT transformation parameters."""
    ae1 = FloatField('Ae1 (deg C)', validators=[Optional(), NumberRange(400, 900)])
    ae3 = FloatField('Ae3 (deg C)', validators=[Optional(), NumberRange(600, 1100)])
    bs = FloatField('Bs (deg C)', validators=[Optional(), NumberRange(200, 700)])
    ms = FloatField('Ms (deg C)', validators=[Optional(), NumberRange(-50, 600)])
    mf = FloatField('Mf (deg C)', validators=[Optional(), NumberRange(-100, 400)])
    austenitizing_temperature = FloatField(
        'Austenitizing Temperature (deg C)',
        validators=[Optional(), NumberRange(700, 1300)],
        default=900.0
    )
    grain_size_astm = FloatField(
        'Grain Size (ASTM)',
        validators=[Optional(), NumberRange(1, 14)],
        default=8.0
    )
    data_source = SelectField('Data Source', choices=[
        ('empirical', 'Empirical (calculated)'),
        ('literature', 'Literature'),
        ('calibrated', 'Calibrated from test data'),
    ])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Parameters')


class JMAKParametersForm(FlaskForm):
    """Form for editing JMAK parameters for a single phase."""
    phase = HiddenField('Phase')
    n_value = FloatField('Avrami Exponent (n)', validators=[
        DataRequired(), NumberRange(0.1, 10)
    ])
    b_model_type = SelectField('b(T) Model', choices=[
        ('gaussian', 'Gaussian'),
        ('arrhenius', 'Arrhenius'),
        ('polynomial', 'Polynomial'),
    ])
    # Gaussian parameters
    b_max = FloatField('b_max', validators=[Optional(), NumberRange(0)])
    t_nose = FloatField('T_nose (deg C)', validators=[Optional()])
    sigma = FloatField('Sigma (deg C)', validators=[Optional(), NumberRange(1)])
    # Arrhenius parameters
    b0 = FloatField('b0 (pre-exponential)', validators=[Optional()])
    Q = FloatField('Q (activation energy, J/mol)', validators=[Optional()])

    nose_temperature = FloatField('Nose Temperature (deg C)', validators=[Optional()])
    nose_time = FloatField('Nose Time (s)', validators=[Optional(), NumberRange(0)])
    temp_range_min = FloatField('T min (deg C)', validators=[Optional()])
    temp_range_max = FloatField('T max (deg C)', validators=[Optional()])

    submit = SubmitField('Save JMAK Parameters')


class MartensiteForm(FlaskForm):
    """Form for martensite K-M parameters."""
    ms = FloatField('Ms (deg C)', validators=[DataRequired()])
    mf = FloatField('Mf (deg C)', validators=[Optional()])
    alpha_m = FloatField('Alpha (1/K)', validators=[
        DataRequired(), NumberRange(0.001, 0.1)
    ], default=0.011)
    submit = SubmitField('Save Martensite Parameters')


class CalibrationUploadForm(FlaskForm):
    """Form for uploading dilatometry calibration data."""
    csv_file = FileField('CSV File', validators=[
        DataRequired(),
        FileAllowed(['csv'], 'CSV files only')
    ])
    test_type = SelectField('Test Type', choices=[
        ('isothermal', 'Isothermal Dilatometry'),
        ('continuous_cooling', 'CCT Dilatometry'),
    ])
    phase = SelectField('Phase', choices=[
        ('ferrite', 'Ferrite'),
        ('pearlite', 'Pearlite'),
        ('bainite', 'Bainite'),
    ])
    submit = SubmitField('Upload & Calibrate')
