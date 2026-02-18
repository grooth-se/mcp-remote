"""Shared test fixtures for Flask integration tests."""
import json
import pytest

from app import create_app
from app.extensions import db as _db
from app.models import (
    User, SteelGrade, Simulation, WeldProject, HeatTreatmentTemplate,
    ROLE_ENGINEER, ROLE_ADMIN,
    STATUS_DRAFT, DATA_SOURCE_STANDARD,
    GEOMETRY_CYLINDER,
)
from app.models.simulation import PROCESS_QUENCH_WATER


@pytest.fixture(scope='session')
def app():
    """Create application for the test session."""
    app = create_app('testing')
    # Override binds to ensure in-memory SQLite for materials
    app.config['SQLALCHEMY_BINDS'] = {'materials': 'sqlite://'}
    yield app


@pytest.fixture()
def db(app):
    """Per-test database — create tables, yield, then clean up."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture()
def client(app, db):
    """Flask test client (anonymous)."""
    return app.test_client()


@pytest.fixture()
def engineer_user(db):
    """User with engineer role."""
    user = User(username='engineer1', role=ROLE_ENGINEER)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def admin_user(db):
    """User with admin role."""
    user = User(username='admin1', role=ROLE_ADMIN)
    user.set_password('adminpass')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def logged_in_client(client, engineer_user):
    """Test client logged in as engineer."""
    client.post('/auth/login', data={
        'username': 'engineer1',
        'password': 'password123',
    })
    return client


@pytest.fixture()
def admin_client(client, admin_user):
    """Test client logged in as admin."""
    client.post('/auth/login', data={
        'username': 'admin1',
        'password': 'adminpass',
    })
    return client


@pytest.fixture()
def sample_steel_grade(db):
    """A standard steel grade."""
    grade = SteelGrade(designation='AISI 4340', data_source=DATA_SOURCE_STANDARD)
    db.session.add(grade)
    db.session.commit()
    return grade


@pytest.fixture()
def sample_simulation(db, engineer_user, sample_steel_grade):
    """A draft simulation owned by engineer_user."""
    sim = Simulation(
        name='Test Sim',
        description='A test simulation',
        steel_grade_id=sample_steel_grade.id,
        user_id=engineer_user.id,
        geometry_type=GEOMETRY_CYLINDER,
        process_type=PROCESS_QUENCH_WATER,
        status=STATUS_DRAFT,
    )
    sim.set_geometry({'radius': 0.05, 'length': 0.1})
    sim.set_solver_config({'n_nodes': 21, 'dt': 0.5, 'max_time': 60})
    sim.set_ht_config(sim.create_default_ht_config())
    db.session.add(sim)
    db.session.commit()
    return sim


@pytest.fixture()
def sample_weld_project(db, engineer_user, sample_steel_grade):
    """A draft weld project owned by engineer_user."""
    proj = WeldProject(
        name='Test Weld',
        description='A test weld project',
        steel_grade_id=sample_steel_grade.id,
        user_id=engineer_user.id,
        process_type='gtaw',
        status='draft',
    )
    db.session.add(proj)
    db.session.commit()
    return proj


@pytest.fixture()
def sample_template(db, engineer_user):
    """A public heat treatment template owned by engineer_user."""
    tmpl = HeatTreatmentTemplate(
        name='Standard Q&T',
        description='Standard quench and temper',
        user_id=engineer_user.id,
        category='quench_temper',
        is_public=True,
        heat_treatment_config=json.dumps({
            'heating': {'enabled': True, 'target_temperature': 850.0, 'hold_time': 60.0},
            'transfer': {'enabled': True, 'duration': 10.0},
            'quenching': {'enabled': True, 'media': 'water', 'duration': 300.0},
            'tempering': {'enabled': False},
        }),
    )
    db.session.add(tmpl)
    db.session.commit()
    return tmpl
