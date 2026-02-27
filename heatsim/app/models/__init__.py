"""Database models."""
from .user import (
    User,
    ROLE_ENGINEER, ROLE_ADMIN,
    ROLES, ROLE_LABELS,
    admin_required
)
from .material import (
    SteelGrade,
    MaterialProperty,
    PhaseDiagram,
    PhaseProperty,
    SteelComposition,
    PROPERTY_TYPE_CONSTANT, PROPERTY_TYPE_CURVE, PROPERTY_TYPE_TABLE,
    PROPERTY_TYPE_POLYNOMIAL, PROPERTY_TYPE_EQUATION, PROPERTY_TYPES,
    DATA_SOURCE_STANDARD, DATA_SOURCE_SUBSEATEC, DATA_SOURCES,
    DIAGRAM_TYPE_CCT, DIAGRAM_TYPE_TTT, DIAGRAM_TYPES,
    PHASE_FERRITE, PHASE_AUSTENITE, PHASE_MARTENSITE, PHASE_BAINITE,
    PHASE_PEARLITE, PHASE_CEMENTITE, PHASES, PHASE_LABELS,
)
from .simulation import (
    Simulation,
    SimulationResult,
    HeatTreatmentTemplate,
    STATUS_DRAFT, STATUS_READY, STATUS_QUEUED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED, STATUSES,
    GEOMETRY_CYLINDER, GEOMETRY_PLATE, GEOMETRY_RING, GEOMETRY_TYPES,
    PROCESS_TYPES, PROCESS_LABELS, DEFAULT_HTC,
)
from .weld_project import (
    WeldProject,
    WeldString,
    WeldResult,
    PROJECT_STATUSES,
    WELD_PROCESS_TYPES, WELD_PROCESS_LABELS,
    STRING_STATUSES, STRING_PENDING, STRING_RUNNING, STRING_COMPLETED, STRING_FAILED,
    TEMP_MODES, TEMP_MODE_CALCULATED, TEMP_MODE_MANUAL, TEMP_MODE_SOLIDIFICATION,
    RESULT_TYPES, RESULT_THERMAL_CYCLE, RESULT_TEMPERATURE_FIELD, RESULT_COOLING_RATE, RESULT_LINE_PROFILE,
)
from .measured_data import MeasuredData
from .snapshot import SimulationSnapshot
from .ttt_parameters import (
    TTTParameters,
    JMAKParameters,
    MartensiteParameters,
    TTTCalibrationData,
    TTTCurve,
    TTT_SOURCE_LITERATURE, TTT_SOURCE_CALIBRATED, TTT_SOURCE_EMPIRICAL, TTT_SOURCES,
    B_MODEL_GAUSSIAN, B_MODEL_ARRHENIUS, B_MODEL_POLYNOMIAL, B_MODEL_TYPES,
    CURVE_TYPE_TTT, CURVE_TYPE_CCT, CURVE_TYPES,
    CURVE_POS_START, CURVE_POS_FIFTY, CURVE_POS_FINISH, CURVE_POSITIONS,
)
from .material_changelog import MaterialChangeLog
from .system_setting import SystemSetting
from .application import Application
from .permission import UserPermission
from .session import UserSession
from .access_log import AccessLog
from .audit_log import (
    AuditLog,
    ACTION_LOGIN, ACTION_LOGOUT,
    ACTION_CREATE_USER, ACTION_DELETE_USER, ACTION_UPDATE_USER,
    ACTION_RUN_SIMULATION, ACTION_DELETE_SIMULATION, ACTION_CREATE_SIMULATION,
    ACTION_UPLOAD_DATA, ACTION_DELETE_DATA,
    ACTION_LABELS, ACTION_BADGES,
)

__all__ = [
    # User models
    'User',
    'ROLE_ENGINEER', 'ROLE_ADMIN',
    'ROLES', 'ROLE_LABELS',
    'admin_required',
    # Material models (PostgreSQL)
    'SteelGrade',
    'MaterialProperty',
    'PhaseDiagram',
    'PhaseProperty',
    'SteelComposition',
    'PROPERTY_TYPE_CONSTANT', 'PROPERTY_TYPE_CURVE', 'PROPERTY_TYPE_TABLE',
    'PROPERTY_TYPE_POLYNOMIAL', 'PROPERTY_TYPE_EQUATION', 'PROPERTY_TYPES',
    'DATA_SOURCE_STANDARD', 'DATA_SOURCE_SUBSEATEC', 'DATA_SOURCES',
    'DIAGRAM_TYPE_CCT', 'DIAGRAM_TYPE_TTT', 'DIAGRAM_TYPES',
    'PHASE_FERRITE', 'PHASE_AUSTENITE', 'PHASE_MARTENSITE', 'PHASE_BAINITE',
    'PHASE_PEARLITE', 'PHASE_CEMENTITE', 'PHASES', 'PHASE_LABELS',
    # Simulation models (PostgreSQL)
    'Simulation',
    'SimulationResult',
    'HeatTreatmentTemplate',
    'STATUS_DRAFT', 'STATUS_READY', 'STATUS_QUEUED', 'STATUS_RUNNING', 'STATUS_COMPLETED', 'STATUS_FAILED', 'STATUSES',
    'GEOMETRY_CYLINDER', 'GEOMETRY_PLATE', 'GEOMETRY_RING', 'GEOMETRY_TYPES',
    'PROCESS_TYPES', 'PROCESS_LABELS', 'DEFAULT_HTC',
    # Weld project models (PostgreSQL - Phase 4)
    'WeldProject',
    'WeldString',
    'WeldResult',
    'PROJECT_STATUSES',
    'WELD_PROCESS_TYPES', 'WELD_PROCESS_LABELS',
    'STRING_STATUSES', 'STRING_PENDING', 'STRING_RUNNING', 'STRING_COMPLETED', 'STRING_FAILED',
    'TEMP_MODES', 'TEMP_MODE_CALCULATED', 'TEMP_MODE_MANUAL', 'TEMP_MODE_SOLIDIFICATION',
    'RESULT_TYPES', 'RESULT_THERMAL_CYCLE', 'RESULT_TEMPERATURE_FIELD', 'RESULT_COOLING_RATE', 'RESULT_LINE_PROFILE',
    # Measured data models
    'MeasuredData',
    # Snapshot versioning
    'SimulationSnapshot',
    # TTT/CCT parameters (PostgreSQL)
    'TTTParameters',
    'JMAKParameters',
    'MartensiteParameters',
    'TTTCalibrationData',
    'TTTCurve',
    'TTT_SOURCE_LITERATURE', 'TTT_SOURCE_CALIBRATED', 'TTT_SOURCE_EMPIRICAL', 'TTT_SOURCES',
    'B_MODEL_GAUSSIAN', 'B_MODEL_ARRHENIUS', 'B_MODEL_POLYNOMIAL', 'B_MODEL_TYPES',
    'CURVE_TYPE_TTT', 'CURVE_TYPE_CCT', 'CURVE_TYPES',
    'CURVE_POS_START', 'CURVE_POS_FIFTY', 'CURVE_POS_FINISH', 'CURVE_POSITIONS',
    # Material change log
    'MaterialChangeLog',
    # System settings
    'SystemSetting',
    # Portal models
    'Application',
    'UserPermission',
    'UserSession',
    'AccessLog',
    # Audit log
    'AuditLog',
    'ACTION_LOGIN', 'ACTION_LOGOUT',
    'ACTION_CREATE_USER', 'ACTION_DELETE_USER', 'ACTION_UPDATE_USER',
    'ACTION_RUN_SIMULATION', 'ACTION_DELETE_SIMULATION', 'ACTION_CREATE_SIMULATION',
    'ACTION_UPLOAD_DATA', 'ACTION_DELETE_DATA',
    'ACTION_LABELS', 'ACTION_BADGES',
]
