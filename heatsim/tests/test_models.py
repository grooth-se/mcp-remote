"""Tests for database models — validates fixtures and both DB binds."""
import json
import pytest
from app.models import (
    User, SteelGrade, SteelComposition, MaterialProperty, PhaseProperty,
    SystemSetting, AuditLog,
    ROLE_ENGINEER, ROLE_ADMIN, DATA_SOURCE_STANDARD, DATA_SOURCE_SUBSEATEC,
    PHASE_FERRITE, PHASE_AUSTENITE,
)


class TestUserModel:
    def test_set_and_check_password(self, db):
        u = User(username='u1', role=ROLE_ENGINEER)
        u.set_password('secret')
        db.session.add(u)
        db.session.commit()
        assert u.check_password('secret')
        assert not u.check_password('wrong')

    def test_is_admin_property(self, db):
        eng = User(username='eng', role=ROLE_ENGINEER)
        adm = User(username='adm', role=ROLE_ADMIN)
        assert not eng.is_admin
        assert adm.is_admin

    def test_role_label(self, db):
        u = User(username='x', role=ROLE_ENGINEER)
        assert u.role_label == 'Materials Engineer'
        u.role = ROLE_ADMIN
        assert u.role_label == 'Administrator'

    def test_update_last_login(self, db):
        u = User(username='ll', role=ROLE_ENGINEER)
        u.set_password('p')
        db.session.add(u)
        db.session.commit()
        assert u.last_login is None
        u.update_last_login()
        db.session.commit()
        assert u.last_login is not None


class TestSteelGradeModel:
    def test_display_name(self, sample_steel_grade):
        assert sample_steel_grade.display_name == 'AISI 4340 (Standard)'

    def test_is_standard(self, sample_steel_grade):
        assert sample_steel_grade.is_standard
        assert not sample_steel_grade.is_subseatec

    def test_subseatec_source(self, db):
        g = SteelGrade(designation='X', data_source=DATA_SOURCE_SUBSEATEC)
        db.session.add(g)
        db.session.commit()
        assert g.is_subseatec
        assert not g.is_standard

    def test_unique_constraint(self, db, sample_steel_grade):
        dup = SteelGrade(designation='AISI 4340', data_source=DATA_SOURCE_STANDARD)
        db.session.add(dup)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()


class TestSteelComposition:
    def _make(self, db, grade):
        comp = SteelComposition(
            steel_grade_id=grade.id,
            carbon=0.40, manganese=0.70, silicon=0.25,
            chromium=0.80, nickel=1.80, molybdenum=0.25,
        )
        db.session.add(comp)
        db.session.commit()
        return comp

    def test_carbon_equivalent_iiw(self, db, sample_steel_grade):
        comp = self._make(db, sample_steel_grade)
        ce = comp.carbon_equivalent_iiw
        expected = 0.40 + 0.70 / 6 + (0.80 + 0.25) / 5 + 1.80 / 15
        assert abs(ce - expected) < 1e-6

    def test_carbon_equivalent_pcm(self, db, sample_steel_grade):
        comp = self._make(db, sample_steel_grade)
        ce = comp.carbon_equivalent_pcm
        assert ce > 0

    def test_carbon_equivalent_cen(self, db, sample_steel_grade):
        comp = self._make(db, sample_steel_grade)
        ce = comp.carbon_equivalent_cen
        assert ce > 0

    def test_ideal_diameter(self, db, sample_steel_grade):
        comp = self._make(db, sample_steel_grade)
        di = comp.ideal_diameter_di
        assert di > 0

    def test_to_dict(self, db, sample_steel_grade):
        comp = self._make(db, sample_steel_grade)
        d = comp.to_dict()
        assert d['C'] == 0.40
        assert d['Mn'] == 0.70
        assert 'Si' in d


class TestMaterialProperty:
    def test_set_data_round_trip(self, db, sample_steel_grade):
        prop = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='thermal_conductivity',
            property_type='constant',
            data='{}',
        )
        test_data = {'value': 42.5, 'unit': 'W/(m·K)'}
        prop.set_data(test_data)
        db.session.add(prop)
        db.session.commit()
        assert prop.data_dict == test_data

    def test_display_name(self, db, sample_steel_grade):
        prop = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='thermal_conductivity',
            property_type='constant',
            data='{}',
        )
        assert prop.display_name == 'Thermal Conductivity'

    def test_is_temperature_dependent(self, db, sample_steel_grade):
        prop = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='specific_heat',
            property_type='curve',
            dependencies='temperature',
            data='{}',
        )
        assert prop.is_temperature_dependent
        prop2 = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='density',
            property_type='constant',
            dependencies='',
            data='{}',
        )
        assert not prop2.is_temperature_dependent


class TestSystemSetting:
    def test_get_set_string(self, app, db):
        with app.app_context():
            SystemSetting.set('site_name', 'HeatSim', value_type='string')
            assert SystemSetting.get('site_name') == 'HeatSim'

    def test_get_set_bool(self, app, db):
        with app.app_context():
            SystemSetting.set('maintenance_mode', 'true', value_type='bool')
            assert SystemSetting.get('maintenance_mode') is True
            SystemSetting.set('maintenance_mode', 'false', value_type='bool')
            assert SystemSetting.get('maintenance_mode') is False

    def test_get_set_int(self, app, db):
        with app.app_context():
            SystemSetting.set('max_upload', '50', value_type='int')
            assert SystemSetting.get('max_upload') == 50

    def test_get_default(self, app, db):
        with app.app_context():
            assert SystemSetting.get('nonexistent', 'default') == 'default'


class TestAuditLog:
    def test_log_creates_entry(self, app, db, engineer_user):
        with app.test_request_context():
            from flask_login import login_user
            login_user(engineer_user)
            entry = AuditLog.log('login')
            assert entry.id is not None
            assert entry.username == 'engineer1'
            assert entry.action == 'login'

    def test_action_label(self, db):
        entry = AuditLog(username='test', action='login')
        assert entry.action_label == 'Login'
        entry2 = AuditLog(username='test', action='unknown')
        assert entry2.action_label == 'unknown'
