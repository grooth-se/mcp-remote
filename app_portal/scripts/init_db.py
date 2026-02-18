#!/usr/bin/env python3
"""Initialize the portal database and seed default applications."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.application import Application

DEFAULT_APPS = [
    {
        'app_code': 'accruedincome',
        'app_name': 'Accrued Income',
        'description': 'Project accrued income calculations',
        'internal_url': 'http://accruedincome:5001',
        'icon': 'bi-calculator',
        'display_order': 1,
    },
    {
        'app_code': 'heatsim',
        'app_name': 'HeatSim',
        'description': 'Materials simulation platform',
        'internal_url': 'http://heatsim:5002',
        'icon': 'bi-thermometer-half',
        'display_order': 2,
        'requires_gpu': True,
    },
    {
        'app_code': 'mpqpgenerator',
        'app_name': 'MPQP Generator',
        'description': 'Manufacturing document generator',
        'internal_url': 'http://mpqpgenerator:5003',
        'icon': 'bi-file-earmark-text',
        'display_order': 3,
        'requires_gpu': True,
    },
    {
        'app_code': 'mg5integration',
        'app_name': 'MG5 Integrator',
        'description': 'Monitor G5 data integration',
        'internal_url': 'http://mg5integration:5004',
        'icon': 'bi-plug',
        'display_order': 4,
    },
    {
        'app_code': 'durabler2',
        'app_name': 'Durabler2',
        'description': 'Material testing and certification',
        'internal_url': 'http://durabler2:5005',
        'icon': 'bi-clipboard2-data',
        'display_order': 5,
    },
    {
        'app_code': 'spinventory',
        'app_name': 'SPInventory',
        'description': 'Spare parts inventory management',
        'internal_url': 'http://spinventory:5006',
        'icon': 'bi-box-seam',
        'display_order': 6,
    },
    {
        'app_code': 'heattreattracker',
        'app_name': 'Heat Treatment Tracker',
        'description': 'Heat treatment process tracking',
        'internal_url': 'http://heattreattracker:5007',
        'icon': 'bi-fire',
        'display_order': 7,
    },
]


def init_db():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database tables created.")

        # Seed applications
        for app_data in DEFAULT_APPS:
            existing = Application.query.filter_by(app_code=app_data['app_code']).first()
            if not existing:
                application = Application(**app_data)
                db.session.add(application)
                print(f"  Added: {app_data['app_name']}")
            else:
                print(f"  Exists: {app_data['app_name']}")

        db.session.commit()
        print(f"\nDone. {Application.query.count()} applications in database.")


if __name__ == '__main__':
    init_db()
