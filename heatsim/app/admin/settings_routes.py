"""System settings admin routes."""
from flask import render_template, redirect, url_for, flash, request

from . import admin_bp
from app.models import SystemSetting, admin_required


# Default settings with metadata
SETTINGS_SCHEMA = [
    {
        'group': 'COMSOL Configuration',
        'icon': 'bi-cpu',
        'settings': [
            {'key': 'comsol_path', 'label': 'COMSOL Installation Path',
             'type': 'string', 'default': '/usr/local/comsol',
             'description': 'Path to COMSOL Multiphysics installation directory'},
        ]
    },
    {
        'group': 'Limits',
        'icon': 'bi-speedometer2',
        'settings': [
            {'key': 'max_upload_size_mb', 'label': 'Max Upload Size (MB)',
             'type': 'int', 'default': '50',
             'description': 'Maximum file upload size in megabytes'},
            {'key': 'simulation_timeout_seconds', 'label': 'Simulation Timeout (seconds)',
             'type': 'int', 'default': '3600',
             'description': 'Maximum simulation run time before timeout'},
        ]
    },
    {
        'group': 'Maintenance Mode',
        'icon': 'bi-cone-striped',
        'settings': [
            {'key': 'maintenance_mode', 'label': 'Enable Maintenance Mode',
             'type': 'bool', 'default': 'false',
             'description': 'When enabled, non-admin users see a maintenance page'},
            {'key': 'maintenance_message', 'label': 'Maintenance Message',
             'type': 'string', 'default': 'The system is currently under maintenance. Please try again later.',
             'description': 'Message displayed to users during maintenance'},
        ]
    },
]


@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """View and edit system settings."""
    if request.method == 'POST':
        for group in SETTINGS_SCHEMA:
            for s in group['settings']:
                key = s['key']
                if s['type'] == 'bool':
                    value = 'true' if request.form.get(key) else 'false'
                else:
                    value = request.form.get(key, s['default'])
                SystemSetting.set(key, value, value_type=s['type'],
                                  description=s['description'])

        flash('Settings saved.', 'success')
        return redirect(url_for('admin.settings'))

    # Load current values
    for group in SETTINGS_SCHEMA:
        for s in group['settings']:
            s['value'] = SystemSetting.get(s['key'], s['default'])

    return render_template('admin/settings.html', groups=SETTINGS_SCHEMA)
