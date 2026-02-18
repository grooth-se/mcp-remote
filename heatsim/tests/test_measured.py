"""Tests for measured data blueprint routes."""
import json
import pytest
from app.models import Simulation, MeasuredData


class TestMeasuredIndex:
    def test_renders(self, logged_in_client, sample_simulation):
        rv = logged_in_client.get('/measured/')
        assert rv.status_code == 200

    def test_search_filter(self, logged_in_client, sample_simulation, db):
        md = MeasuredData(
            simulation_id=sample_simulation.id,
            name='TC Run 1',
            filename='run1.csv',
            process_step='quenching',
            times_json=json.dumps([0, 1, 2]),
            channels_json=json.dumps({'TC1': [850, 500, 200]}),
        )
        db.session.add(md)
        db.session.commit()
        rv = logged_in_client.get('/measured/?q=TC+Run')
        assert rv.status_code == 200

    def test_step_filter(self, logged_in_client, sample_simulation, db):
        md = MeasuredData(
            simulation_id=sample_simulation.id,
            name='Quench Data',
            filename='quench.csv',
            process_step='quenching',
            times_json=json.dumps([0, 1]),
            channels_json=json.dumps({'TC1': [850, 200]}),
        )
        db.session.add(md)
        db.session.commit()
        rv = logged_in_client.get('/measured/?step=quenching')
        assert rv.status_code == 200

    def test_empty_state(self, logged_in_client):
        rv = logged_in_client.get('/measured/')
        assert rv.status_code == 200

    def test_requires_login(self, client, db):
        rv = client.get('/measured/')
        assert rv.status_code == 302


class TestMeasuredView:
    def _create_data(self, db, sim):
        md = MeasuredData(
            simulation_id=sim.id,
            name='View Test',
            filename='view.csv',
            process_step='full',
            times_json=json.dumps([0, 1, 2, 3]),
            channels_json=json.dumps({'TC1': [850, 700, 400, 200]}),
        )
        db.session.add(md)
        db.session.commit()
        return md

    def test_renders(self, logged_in_client, sample_simulation, db):
        md = self._create_data(db, sample_simulation)
        rv = logged_in_client.get(f'/measured/{md.id}')
        assert rv.status_code == 200

    def test_access_denied(self, logged_in_client, db, sample_steel_grade):
        """Other user's data is denied."""
        from app.models import User, Simulation, ROLE_ENGINEER
        other = User(username='other', role=ROLE_ENGINEER)
        other.set_password('pass')
        db.session.add(other)
        db.session.commit()
        sim = Simulation(
            name='Other Sim', steel_grade_id=sample_steel_grade.id,
            user_id=other.id, geometry_type='cylinder',
            process_type='quench_water', status='draft',
        )
        db.session.add(sim)
        db.session.commit()
        md = MeasuredData(
            simulation_id=sim.id, name='X', filename='x.csv',
            process_step='full',
            times_json='[0]', channels_json='{"TC1":[100]}',
        )
        db.session.add(md)
        db.session.commit()
        rv = logged_in_client.get(f'/measured/{md.id}', follow_redirects=True)
        assert rv.status_code == 200  # Redirects to index

    def test_404(self, logged_in_client):
        rv = logged_in_client.get('/measured/99999')
        assert rv.status_code == 404


class TestMeasuredDelete:
    def test_success(self, logged_in_client, sample_simulation, db):
        md = MeasuredData(
            simulation_id=sample_simulation.id,
            name='Delete Me',
            filename='del.csv',
            process_step='full',
            times_json='[0]', channels_json='{"TC1":[100]}',
        )
        db.session.add(md)
        db.session.commit()
        mid = md.id
        rv = logged_in_client.post(f'/measured/{mid}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(MeasuredData, mid) is None

    def test_access_denied(self, logged_in_client, db, sample_steel_grade):
        from app.models import User, Simulation, ROLE_ENGINEER
        other = User(username='other2', role=ROLE_ENGINEER)
        other.set_password('pass')
        db.session.add(other)
        db.session.commit()
        sim = Simulation(
            name='Other Sim2', steel_grade_id=sample_steel_grade.id,
            user_id=other.id, geometry_type='cylinder',
            process_type='quench_water', status='draft',
        )
        db.session.add(sim)
        db.session.commit()
        md = MeasuredData(
            simulation_id=sim.id, name='Y', filename='y.csv',
            process_step='full',
            times_json='[0]', channels_json='{"TC1":[100]}',
        )
        db.session.add(md)
        db.session.commit()
        mid = md.id
        rv = logged_in_client.post(f'/measured/{mid}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(MeasuredData, mid) is not None  # Not deleted

    def test_pagination(self, logged_in_client, sample_simulation, db):
        rv = logged_in_client.get('/measured/?page=1')
        assert rv.status_code == 200
