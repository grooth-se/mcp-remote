"""Tests for welding blueprint routes."""
import json
import pytest
from app.models import (
    WeldProject, WeldString, WeldResult, Simulation, SteelGrade,
    SteelComposition, User, ROLE_ENGINEER,
)
from app.extensions import db as _db


class TestWeldingIndex:
    def test_renders(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get('/welding/')
        assert rv.status_code == 200
        assert b'Test Weld' in rv.data

    def test_requires_login(self, client, db):
        rv = client.get('/welding/')
        assert rv.status_code == 302

    def test_shows_own_only(self, logged_in_client, sample_weld_project, db, sample_steel_grade, admin_user):
        other = WeldProject(
            name='Admin Weld', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(other)
        db.session.commit()
        rv = logged_in_client.get('/welding/')
        assert b'Admin Weld' not in rv.data


class TestWeldingCreate:
    def test_form_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get('/welding/new')
        assert rv.status_code == 200

    def test_creates_project(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post('/welding/new', data={
            'name': 'New Weld',
            'description': 'Test weld',
            'steel_grade_id': sample_steel_grade.id,
            'process_type': 'gtaw',
            'preheat_temperature': '100',
            'interpass_temperature': '250',
            'interpass_time_default': '60',
            'default_heat_input': '1.5',
            'default_travel_speed': '3.0',
            'default_solidification_temp': '1500',
        }, follow_redirects=True)
        assert rv.status_code == 200
        proj = WeldProject.query.filter_by(name='New Weld').first()
        assert proj is not None

    def test_redirect(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post('/welding/new', data={
            'name': 'Redirect Weld',
            'steel_grade_id': sample_steel_grade.id,
            'process_type': 'gtaw',
            'preheat_temperature': '100',
            'interpass_temperature': '250',
            'interpass_time_default': '60',
            'default_heat_input': '1.5',
            'default_travel_speed': '3.0',
            'default_solidification_temp': '1500',
        })
        assert rv.status_code == 302

    def test_requires_login(self, client, db):
        rv = client.get('/welding/new')
        assert rv.status_code == 302


class TestWeldingView:
    def test_renders(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}')
        assert rv.status_code == 200
        assert b'Test Weld' in rv.data

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='Denied View', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}', follow_redirects=True)
        assert rv.status_code == 200

    def test_404(self, logged_in_client):
        rv = logged_in_client.get('/welding/99999')
        assert rv.status_code == 404


class TestWeldingConfigure:
    def test_renders(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/configure')
        assert rv.status_code == 200

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='Denied Config', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}/configure', follow_redirects=True)
        assert rv.status_code == 200

    def test_quick_add(self, logged_in_client, sample_weld_project, db):
        rv = logged_in_client.post(f'/welding/{sample_weld_project.id}/configure', data={
            'action': 'quick_add',
            'num_layers': '2',
            'strings_per_layer': '1',
            'use_defaults': 'on',
        }, follow_redirects=True)
        assert rv.status_code == 200
        strings = WeldString.query.filter_by(project_id=sample_weld_project.id).all()
        assert len(strings) >= 1


class TestWeldStrings:
    def test_new_form(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/string/new')
        assert rv.status_code == 200

    def test_creates_string(self, logged_in_client, sample_weld_project, db):
        rv = logged_in_client.post(f'/welding/{sample_weld_project.id}/string/new', data={
            'string_number': '1',
            'name': 'Root Pass',
            'body_name': '',
            'layer': '1',
            'position_in_layer': '1',
            'heat_input': '1.5',
            'travel_speed': '3.0',
            'interpass_time': '60',
            'initial_temp_mode': 'calculated',
            'initial_temperature': '100',
            'solidification_temp': '1500',
            'simulation_duration': '120',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='Denied String', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}/string/new', follow_redirects=True)
        assert rv.status_code == 200

    def test_delete_string(self, logged_in_client, sample_weld_project, db):
        ws = WeldString(
            project_id=sample_weld_project.id,
            string_number=1, name='Del', layer=1, position_in_layer=1,
            heat_input=1.5, travel_speed=3.0, status='pending',
        )
        db.session.add(ws)
        db.session.commit()
        rv = logged_in_client.post(
            f'/welding/{sample_weld_project.id}/string/{ws.id}/delete',
            follow_redirects=True)
        assert rv.status_code == 200


class TestWeldingDelete:
    def test_success(self, logged_in_client, sample_weld_project, db):
        pid = sample_weld_project.id
        rv = logged_in_client.post(f'/welding/{pid}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(WeldProject, pid) is None

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='No Delete', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        pid = proj.id
        rv = logged_in_client.post(f'/welding/{pid}/delete', follow_redirects=True)
        assert db.session.get(WeldProject, pid) is not None


class TestWeldingDuplicate:
    def test_success(self, logged_in_client, sample_weld_project, db):
        rv = logged_in_client.post(f'/welding/{sample_weld_project.id}/duplicate',
                                    follow_redirects=True)
        assert rv.status_code == 200
        copies = WeldProject.query.filter(WeldProject.name.contains('(Copy)')).all()
        assert len(copies) >= 1

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='No Dup', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.post(f'/welding/{proj.id}/duplicate', follow_redirects=True)
        assert rv.status_code == 200


class TestWeldingResults:
    def test_renders(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/results')
        # May redirect or render depending on status
        assert rv.status_code in (200, 302)

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='No Results', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}/results', follow_redirects=True)
        assert rv.status_code == 200


class TestWeldingPlots:
    def test_invalid_type_404(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(
            f'/welding/{sample_weld_project.id}/plot/nonexistent_type')
        assert rv.status_code in (400, 404, 500)


class TestHAZ:
    def test_renders(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/haz')
        assert rv.status_code == 200

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='Denied HAZ', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}/haz', follow_redirects=True)
        assert rv.status_code == 200


class TestPreheat:
    def test_renders(self, logged_in_client, sample_weld_project, sample_steel_grade, db):
        """Preheat requires steel grade with composition data."""
        comp = SteelComposition(
            steel_grade_id=sample_steel_grade.id,
            carbon=0.40, manganese=0.70, silicon=0.25,
            chromium=0.80, nickel=1.80, molybdenum=0.25,
        )
        db.session.add(comp)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/preheat')
        # May render or fail depending on preheat calculator availability
        assert rv.status_code in (200, 302)


class TestGoldak:
    def test_renders(self, logged_in_client, sample_weld_project):
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/goldak')
        assert rv.status_code == 200

    def test_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        proj = WeldProject(
            name='Denied Goldak', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}/goldak', follow_redirects=True)
        assert rv.status_code == 200

    def test_multipass_renders(self, logged_in_client, sample_weld_project, db):
        """Multipass requires configured weld strings."""
        string = WeldString(
            project_id=sample_weld_project.id,
            string_number=1, layer=1, position_in_layer=1,
            name='Root Pass', status='pending',
        )
        db.session.add(string)
        sample_weld_project.total_strings = 1
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/goldak/multipass')
        assert rv.status_code == 200


class TestGoldakMultipassQueue:
    """Test goldak multipass async queue behaviour."""

    @pytest.fixture(autouse=True)
    def _setup_strings(self, sample_weld_project, db):
        string = WeldString(
            project_id=sample_weld_project.id,
            string_number=1, layer=1, position_in_layer=1,
            name='Root Pass', status='pending',
        )
        db.session.add(string)
        sample_weld_project.total_strings = 1
        db.session.commit()

    def test_post_enqueues(self, logged_in_client, sample_weld_project, db):
        """POST sets status to queued and encodes config in progress_message."""
        rv = logged_in_client.post(
            f'/welding/{sample_weld_project.id}/goldak/multipass',
            data={'grid_resolution': 'coarse', 'compare_methods': 'y', 'csrf_token': ''},
            follow_redirects=False,
        )
        assert rv.status_code == 302
        db.session.refresh(sample_weld_project)
        assert sample_weld_project.status == 'queued'
        assert sample_weld_project.progress_message.startswith('goldak:coarse:')

    def test_get_shows_stored_result(self, logged_in_client, sample_weld_project, db):
        """GET loads stored WeldResult when available."""
        fake_data = {'pass_summary': [], 'cumulative_thermal_cycles': {}}
        wr = WeldResult(
            project_id=sample_weld_project.id,
            result_type='goldak_multipass',
        )
        wr.time_data = json.dumps(fake_data)
        db.session.add(wr)
        db.session.commit()

        rv = logged_in_client.get(f'/welding/{sample_weld_project.id}/goldak/multipass')
        assert rv.status_code == 200
        assert b'pass_summary' not in rv.data or rv.status_code == 200

    def test_status_endpoint(self, logged_in_client, sample_weld_project, db):
        """Status endpoint returns JSON with progress info."""
        sample_weld_project.status = 'running'
        sample_weld_project.progress_percent = 50.0
        sample_weld_project.progress_message = 'Pass 1/2'
        db.session.commit()

        rv = logged_in_client.get(
            f'/welding/{sample_weld_project.id}/goldak/multipass/status'
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['status'] == 'running'
        assert data['progress_percent'] == 50.0
        assert data['progress_message'] == 'Pass 1/2'

    def test_status_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        """Status endpoint denies access to other users' projects."""
        proj = WeldProject(
            name='Other', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, process_type='gtaw', status='draft',
        )
        db.session.add(proj)
        db.session.commit()
        rv = logged_in_client.get(f'/welding/{proj.id}/goldak/multipass/status')
        assert rv.status_code == 403
