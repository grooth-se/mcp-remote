"""Forms for welding simulation."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, FloatField, IntegerField,
    BooleanField, HiddenField, FieldList, FormField
)
from wtforms.validators import DataRequired, Optional, NumberRange, Length

from app.models.weld_project import (
    WELD_PROCESS_TYPES, WELD_PROCESS_LABELS, TEMP_MODES
)


class WeldProjectForm(FlaskForm):
    """Form for creating/editing weld projects."""

    name = StringField(
        'Project Name',
        validators=[DataRequired(), Length(min=1, max=100)],
        render_kw={'placeholder': 'e.g., Pipe Joint Weld A123'}
    )

    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000)],
        render_kw={'rows': 3, 'placeholder': 'Optional project notes'}
    )

    steel_grade_id = SelectField(
        'Steel Grade',
        coerce=int,
        validators=[DataRequired()]
    )

    process_type = SelectField(
        'Welding Process',
        choices=[(p, WELD_PROCESS_LABELS[p]) for p in WELD_PROCESS_TYPES],
        validators=[DataRequired()]
    )

    cad_file = FileField(
        'CAD Geometry File',
        validators=[Optional(), FileAllowed(['stp', 'step', 'igs', 'iges', 'stl'],
                                            'STEP, IGES, or STL files only')]
    )

    preheat_temperature = FloatField(
        'Preheat Temperature (°C)',
        validators=[DataRequired(), NumberRange(min=0, max=500)],
        default=20.0
    )

    interpass_temperature = FloatField(
        'Max Interpass Temperature (°C)',
        validators=[DataRequired(), NumberRange(min=50, max=400)],
        default=150.0
    )

    interpass_time_default = FloatField(
        'Default Interpass Time (s)',
        validators=[DataRequired(), NumberRange(min=0, max=3600)],
        default=60.0
    )

    default_heat_input = FloatField(
        'Default Heat Input (kJ/mm)',
        validators=[DataRequired(), NumberRange(min=0.1, max=10)],
        default=1.5
    )

    default_travel_speed = FloatField(
        'Default Travel Speed (mm/s)',
        validators=[DataRequired(), NumberRange(min=0.5, max=50)],
        default=5.0
    )

    default_solidification_temp = FloatField(
        'Solidification Temperature (°C)',
        validators=[DataRequired(), NumberRange(min=1400, max=1600)],
        default=1500.0
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate steel grade choices
        from app.models.material import SteelGrade
        grades = SteelGrade.query.order_by(SteelGrade.designation).all()
        self.steel_grade_id.choices = [(0, '-- Select Steel Grade --')] + \
            [(g.id, g.display_name) for g in grades]


class WeldStringForm(FlaskForm):
    """Form for editing a single weld string."""

    string_number = IntegerField(
        'Sequence Number',
        validators=[DataRequired(), NumberRange(min=1, max=100)]
    )

    name = StringField(
        'String Name',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., Root Pass'}
    )

    body_name = StringField(
        'CAD Body Name',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'CAD body identifier'}
    )

    layer = IntegerField(
        'Layer Number',
        validators=[DataRequired(), NumberRange(min=1, max=10)],
        default=1
    )

    position_in_layer = IntegerField(
        'Position in Layer',
        validators=[DataRequired(), NumberRange(min=1, max=20)],
        default=1
    )

    heat_input = FloatField(
        'Heat Input (kJ/mm)',
        validators=[Optional(), NumberRange(min=0.1, max=10)],
        render_kw={'placeholder': 'Leave blank for default'}
    )

    travel_speed = FloatField(
        'Travel Speed (mm/s)',
        validators=[Optional(), NumberRange(min=0.5, max=50)],
        render_kw={'placeholder': 'Leave blank for default'}
    )

    interpass_time = FloatField(
        'Interpass Time (s)',
        validators=[Optional(), NumberRange(min=0, max=3600)],
        render_kw={'placeholder': 'Leave blank for default'}
    )

    initial_temp_mode = SelectField(
        'Initial Temperature Mode',
        choices=[
            ('solidification', 'Solidification Temperature'),
            ('calculated', 'Calculated from Previous'),
            ('manual', 'Manual Entry'),
        ],
        default='solidification'
    )

    initial_temperature = FloatField(
        'Manual Initial Temperature (°C)',
        validators=[Optional(), NumberRange(min=0, max=2000)],
        render_kw={'placeholder': 'Only for manual mode'}
    )

    solidification_temp = FloatField(
        'Solidification Temperature (°C)',
        validators=[Optional(), NumberRange(min=1400, max=1600)],
        render_kw={'placeholder': 'Leave blank for default'}
    )

    simulation_duration = FloatField(
        'Simulation Duration (s)',
        validators=[DataRequired(), NumberRange(min=10, max=600)],
        default=120.0
    )


class StringSequenceForm(FlaskForm):
    """Form for configuring the string sequence."""

    # JSON encoded sequence data
    sequence_data = HiddenField('sequence_data')


class QuickAddStringsForm(FlaskForm):
    """Form for quickly adding multiple strings."""

    num_layers = IntegerField(
        'Number of Layers',
        validators=[DataRequired(), NumberRange(min=1, max=10)],
        default=1
    )

    strings_per_layer = IntegerField(
        'Strings per Layer',
        validators=[DataRequired(), NumberRange(min=1, max=20)],
        default=1
    )

    use_defaults = BooleanField(
        'Use project defaults for all parameters',
        default=True
    )


class HAZAnalysisForm(FlaskForm):
    """Form for HAZ analysis parameters."""

    max_distance_mm = FloatField(
        'Max Distance from Weld Center (mm)',
        validators=[DataRequired(), NumberRange(min=5, max=100)],
        default=20.0
    )

    n_points = IntegerField(
        'Number of Sample Points',
        validators=[DataRequired(), NumberRange(min=10, max=200)],
        default=50
    )

    depth_z_mm = FloatField(
        'Depth Below Surface (mm)',
        validators=[Optional(), NumberRange(min=0, max=50)],
        default=0.0
    )

    hardness_limit = FloatField(
        'Hardness Limit (HV)',
        validators=[DataRequired(), NumberRange(min=200, max=600)],
        default=350.0
    )


class PreheatForm(FlaskForm):
    """Form for preheat calculation parameters."""

    plate_thickness_mm = FloatField(
        'Plate Thickness (mm)',
        validators=[DataRequired(), NumberRange(min=3, max=200)],
        default=20.0
    )

    hydrogen_level = SelectField(
        'Hydrogen Level',
        choices=[
            ('A', 'A — Very Low (≤5 ml/100g)'),
            ('B', 'B — Low (≤10 ml/100g)'),
            ('C', 'C — Medium (≤15 ml/100g)'),
            ('D', 'D — High (≤20 ml/100g)'),
        ],
        default='B'
    )

    restraint = SelectField(
        'Restraint Level',
        choices=[
            ('low', 'Low — free joint'),
            ('medium', 'Medium — moderate restraint'),
            ('high', 'High — rigid structure'),
        ],
        default='medium'
    )


class RunSimulationForm(FlaskForm):
    """Form for starting simulation."""

    use_mock_solver = BooleanField(
        'Use Mock Solver (for testing)',
        default=False
    )

    save_intermediate = BooleanField(
        'Save intermediate results',
        default=True
    )
