"""Forms for heat treatment simulation setup."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, FloatField,
    IntegerField, BooleanField, SubmitField
)
from wtforms.validators import DataRequired, Optional, NumberRange, Length

from app.models.simulation import (
    GEOMETRY_TYPES,
    QUENCH_MEDIA, QUENCH_MEDIA_LABELS,
    AGITATION_LEVELS, AGITATION_LABELS,
    FURNACE_ATMOSPHERES, FURNACE_ATMOSPHERE_LABELS,
)


class SimulationForm(FlaskForm):
    """Form for creating a new simulation."""
    name = StringField(
        'Simulation Name',
        validators=[DataRequired(), Length(max=100)],
        render_kw={'placeholder': 'e.g., Shaft Quench Study'}
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)],
        render_kw={'rows': 3, 'placeholder': 'Optional description'}
    )
    steel_grade_id = SelectField(
        'Steel Grade',
        coerce=int,
        validators=[DataRequired()]
    )
    geometry_type = SelectField(
        'Geometry',
        choices=[
            ('cylinder', 'Cylinder (solid)'),
            ('hollow_cylinder', 'Hollow Cylinder (OD/ID)'),
            ('plate', 'Plate'),
            ('ring', 'Ring (Ri/Ro)'),
            ('cad', 'Import from CAD (STEP file)')
        ],
        default='cylinder'
    )

    # CAD geometry fields
    cad_file = FileField(
        'STEP File',
        validators=[FileAllowed(['step', 'stp'], 'Only STEP files (.step, .stp) are allowed')]
    )
    cad_equivalent_type = SelectField(
        'Equivalent Geometry',
        choices=[
            ('auto', 'Auto-detect'),
            ('cylinder', 'Cylinder (radial heat transfer)'),
            ('plate', 'Plate (through-thickness heat transfer)')
        ],
        default='auto'
    )

    submit = SubmitField('Create Simulation')


class GeometryForm(FlaskForm):
    """Form for geometry configuration."""
    # Cylinder - supports up to 1200mm diameter (600mm radius)
    radius = FloatField(
        'Radius (mm)',
        validators=[Optional(), NumberRange(min=1, max=1500)],
        default=50
    )
    # Plate
    thickness = FloatField(
        'Thickness (mm)',
        validators=[Optional(), NumberRange(min=1, max=1500)],
        default=20
    )
    # Common
    length = FloatField(
        'Length (mm)',
        validators=[Optional(), NumberRange(min=1, max=5000)],
        default=100
    )
    width = FloatField(
        'Width (mm)',
        validators=[Optional(), NumberRange(min=1, max=5000)],
        default=100
    )
    # Ring - supports large rings up to 1200mm outer diameter
    inner_radius = FloatField(
        'Inner Radius (mm)',
        validators=[Optional(), NumberRange(min=1, max=1500)],
        default=20
    )
    outer_radius = FloatField(
        'Outer Radius (mm)',
        validators=[Optional(), NumberRange(min=1, max=1500)],
        default=50
    )
    # Hollow Cylinder - OD/ID notation (more common in engineering)
    outer_diameter = FloatField(
        'Outer Diameter OD (mm)',
        validators=[Optional(), NumberRange(min=2, max=3000)],
        default=100
    )
    inner_diameter = FloatField(
        'Inner Diameter ID (mm)',
        validators=[Optional(), NumberRange(min=1, max=2990)],
        default=40
    )


class HeatingPhaseForm(FlaskForm):
    """Form for heating (austenitizing) phase configuration."""
    enabled = BooleanField('Enable Heating Phase', default=True)

    initial_temperature = FloatField(
        'Initial Temperature (°C)',
        validators=[Optional(), NumberRange(min=-50, max=500)],
        default=25.0,
        render_kw={'placeholder': 'Starting temperature'}
    )

    target_temperature = FloatField(
        'Austenitizing Temperature (°C)',
        validators=[Optional(), NumberRange(min=500, max=1200)],
        default=850.0,
        render_kw={'placeholder': 'Target furnace temperature'}
    )

    hold_time = FloatField(
        'Hold Time at Temperature (min)',
        validators=[Optional(), NumberRange(min=0, max=1440)],
        default=60.0,
        render_kw={'placeholder': 'Soak time at target temp'}
    )

    furnace_atmosphere = SelectField(
        'Furnace Atmosphere',
        choices=[(a, FURNACE_ATMOSPHERE_LABELS[a]) for a in FURNACE_ATMOSPHERES],
        default='air'
    )

    # Furnace ramp settings
    cold_furnace = BooleanField('Cold Furnace Start', default=False)

    furnace_start_temperature = FloatField(
        'Furnace Start Temperature (°C)',
        validators=[Optional(), NumberRange(min=-50, max=500)],
        default=25.0,
        render_kw={'placeholder': 'Initial furnace temperature'}
    )

    furnace_ramp_rate = FloatField(
        'Furnace Ramp Rate (°C/min)',
        validators=[Optional(), NumberRange(min=0, max=50)],
        default=5.0,
        render_kw={'placeholder': 'Furnace heating rate'}
    )

    # End condition settings
    end_condition = SelectField(
        'End Condition',
        choices=[
            ('equilibrium', 'Equilibrium (center within 5°C)'),
            ('rate_threshold', 'Surface Rate Threshold'),
            ('center_offset', 'Center Temperature Offset'),
        ],
        default='equilibrium'
    )

    rate_threshold = FloatField(
        'Surface Rate Threshold (°C/hr)',
        validators=[Optional(), NumberRange(min=0.1, max=10)],
        default=1.0,
        render_kw={'placeholder': 'Trigger when dT/dt < this'}
    )

    hold_time_after_trigger = FloatField(
        'Hold After Trigger (min)',
        validators=[Optional(), NumberRange(min=0, max=1440)],
        default=30.0,
        render_kw={'placeholder': 'Additional hold time after trigger'}
    )

    center_offset = FloatField(
        'Center Offset (°C)',
        validators=[Optional(), NumberRange(min=0, max=100)],
        default=3.0,
        render_kw={'placeholder': 'End when center = target - offset'}
    )

    # Heat transfer parameters
    furnace_htc = FloatField(
        'Furnace HTC (W/m²K)',
        validators=[Optional(), NumberRange(min=1, max=500)],
        default=25.0,
        render_kw={'placeholder': 'Convection coefficient in furnace'}
    )

    furnace_emissivity = FloatField(
        'Surface Emissivity',
        validators=[Optional(), NumberRange(min=0, max=1)],
        default=0.85
    )

    use_radiation = BooleanField('Include Radiation Heat Transfer', default=True)


class TransferPhaseForm(FlaskForm):
    """Form for transfer phase (furnace to quench) configuration."""
    enabled = BooleanField('Enable Transfer Phase', default=True)

    duration = FloatField(
        'Transfer Time (s)',
        validators=[Optional(), NumberRange(min=0, max=600)],
        default=10.0,
        render_kw={'placeholder': 'Time from furnace to quench (up to 10 min for large parts)'}
    )

    ambient_temperature = FloatField(
        'Ambient Temperature (°C)',
        validators=[Optional(), NumberRange(min=-50, max=100)],
        default=25.0
    )

    htc = FloatField(
        'Air HTC (W/m²K)',
        validators=[Optional(), NumberRange(min=1, max=100)],
        default=10.0,
        render_kw={'placeholder': 'Natural convection in air'}
    )

    emissivity = FloatField(
        'Surface Emissivity',
        validators=[Optional(), NumberRange(min=0, max=1)],
        default=0.85
    )

    use_radiation = BooleanField('Include Radiation (significant at high temp)', default=True)


class QuenchingPhaseForm(FlaskForm):
    """Form for quenching phase configuration."""
    media = SelectField(
        'Quench Media',
        choices=[(m, QUENCH_MEDIA_LABELS[m]) for m in QUENCH_MEDIA],
        default='water'
    )

    media_temperature = FloatField(
        'Media Temperature (°C)',
        validators=[Optional(), NumberRange(min=0, max=200)],
        default=25.0,
        render_kw={'placeholder': 'Quench bath temperature'}
    )

    agitation = SelectField(
        'Agitation Level',
        choices=[(a, AGITATION_LABELS[a]) for a in AGITATION_LEVELS],
        default='moderate'
    )

    htc_override = FloatField(
        'Custom HTC (W/m²K)',
        validators=[Optional(), NumberRange(min=10, max=50000)],
        render_kw={'placeholder': 'Leave blank to calculate from media/agitation'}
    )

    duration = FloatField(
        'Quench Duration (s)',
        validators=[Optional(), NumberRange(min=10, max=14400)],
        default=300.0,
        render_kw={'placeholder': 'Time in quench tank (up to 4 hours for large parts)'}
    )

    emissivity = FloatField(
        'Surface Emissivity',
        validators=[Optional(), NumberRange(min=0, max=1)],
        default=0.3,
        render_kw={'placeholder': 'Lower due to steam/oil film'}
    )

    use_radiation = BooleanField('Include Radiation (usually negligible in liquid)', default=False)


class TemperingPhaseForm(FlaskForm):
    """Form for tempering phase configuration."""
    enabled = BooleanField('Enable Tempering Phase', default=False)

    temperature = FloatField(
        'Tempering Temperature (°C)',
        validators=[Optional(), NumberRange(min=100, max=750)],
        default=550.0,
        render_kw={'placeholder': 'Tempering furnace temperature'}
    )

    hold_time = FloatField(
        'Hold Time (min)',
        validators=[Optional(), NumberRange(min=1, max=1440)],
        default=120.0,
        render_kw={'placeholder': 'Time at tempering temperature'}
    )

    # Furnace ramp settings (cold furnace start)
    cold_furnace = BooleanField('Cold Furnace Start', default=False)

    furnace_start_temperature = FloatField(
        'Furnace Start Temperature (°C)',
        validators=[Optional(), NumberRange(min=-50, max=500)],
        default=25.0,
        render_kw={'placeholder': 'Initial furnace temperature'}
    )

    furnace_ramp_rate = FloatField(
        'Furnace Ramp Rate (°C/min)',
        validators=[Optional(), NumberRange(min=0, max=50)],
        default=5.0,
        render_kw={'placeholder': 'Furnace heating rate'}
    )

    # End condition settings (same as heating phase)
    end_condition = SelectField(
        'End Condition',
        choices=[
            ('equilibrium', 'Equilibrium (center within 5°C)'),
            ('rate_threshold', 'Surface Rate Threshold'),
            ('center_offset', 'Center Temperature Offset'),
        ],
        default='equilibrium'
    )

    rate_threshold = FloatField(
        'Surface Rate Threshold (°C/hr)',
        validators=[Optional(), NumberRange(min=0.1, max=100)],
        default=1.0,
        render_kw={'placeholder': 'Trigger when dT/dt < this'}
    )

    hold_time_after_trigger = FloatField(
        'Hold After Trigger (min)',
        validators=[Optional(), NumberRange(min=0, max=1440)],
        default=30.0,
        render_kw={'placeholder': 'Additional hold time after trigger'}
    )

    center_offset = FloatField(
        'Center Offset (°C)',
        validators=[Optional(), NumberRange(min=0, max=100)],
        default=3.0,
        render_kw={'placeholder': 'End when center = target - offset'}
    )

    cooling_method = SelectField(
        'Cooling After Tempering',
        choices=[
            ('air', 'Air Cool'),
            ('furnace', 'Furnace Cool'),
        ],
        default='air'
    )

    htc = FloatField(
        'Cooling HTC (W/m²K)',
        validators=[Optional(), NumberRange(min=1, max=500)],
        default=25.0
    )

    emissivity = FloatField(
        'Surface Emissivity',
        validators=[Optional(), NumberRange(min=0, max=1)],
        default=0.85
    )


class SolverForm(FlaskForm):
    """Form for solver configuration."""
    n_nodes = IntegerField(
        'Number of Nodes',
        validators=[DataRequired(), NumberRange(min=11, max=201)],
        default=51
    )
    dt = FloatField(
        'Time Step (s)',
        validators=[Optional(), NumberRange(min=0.001, max=60)],
        default=0.1
    )
    auto_dt = BooleanField(
        'Auto-calculate time step',
        default=True,
        description='Calculate dt to limit simulation to ~20,000 time steps'
    )
    max_time = FloatField(
        'Maximum Simulation Time (s)',
        validators=[DataRequired(), NumberRange(min=10, max=180000)],
        default=1800,
        render_kw={'placeholder': 'Total simulation time limit (up to 50 hours)'}
    )
    submit = SubmitField('Save Configuration')


class HeatTreatmentSetupForm(FlaskForm):
    """Combined form for full heat treatment setup."""
    # This is used for the combined setup page
    submit = SubmitField('Save Heat Treatment Configuration')
