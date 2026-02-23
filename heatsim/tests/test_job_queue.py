"""Tests for the background job queue service."""
import json
import pytest
from unittest.mock import patch, MagicMock

from app.models.simulation import Simulation, STATUS_QUEUED, STATUS_RUNNING, STATUS_FAILED, STATUS_READY
from app.models.weld_project import (
    WeldProject, WeldString,
    STATUS_QUEUED as WELD_QUEUED,
    STATUS_CONFIGURED,
    STATUS_RUNNING as WELD_RUNNING,
    STATUS_FAILED as WELD_FAILED,
)
from app.services.job_queue import (
    _claim_next_job, _mark_failed, get_queue_status, get_queue_position,
)


class TestClaimNextJob:
    """Test FIFO claim ordering."""

    def test_empty_queue(self, db):
        """No queued jobs returns None."""
        assert _claim_next_job() is None

    def test_single_queued_simulation(self, db, sample_simulation):
        """Single queued simulation is claimed."""
        sample_simulation.status = STATUS_QUEUED
        db.session.commit()

        result = _claim_next_job()
        assert result is not None
        assert result[0] == 'simulation'
        assert result[1] == sample_simulation.id

    def test_single_queued_weld(self, db, sample_weld_project):
        """Single queued weld project is claimed."""
        sample_weld_project.status = WELD_QUEUED
        sample_weld_project.total_strings = 1
        db.session.commit()

        result = _claim_next_job()
        assert result is not None
        assert result[0] == 'weld'
        assert result[1] == sample_weld_project.id

    def test_fifo_ordering(self, db, engineer_user, sample_steel_grade):
        """Earlier ID is picked first when both types are queued."""
        sim = Simulation(
            name='First', steel_grade_id=sample_steel_grade.id,
            user_id=engineer_user.id, geometry_type='cylinder',
            process_type='quench_water', status=STATUS_QUEUED,
        )
        db.session.add(sim)
        db.session.flush()
        sim_id = sim.id

        proj = WeldProject(
            name='Second', steel_grade_id=sample_steel_grade.id,
            user_id=engineer_user.id, process_type='gtaw',
            status=WELD_QUEUED, total_strings=1,
        )
        db.session.add(proj)
        db.session.commit()

        result = _claim_next_job()
        assert result is not None
        # The one with lower id gets picked first
        assert result[1] == sim_id

    def test_ignores_non_queued(self, db, sample_simulation):
        """Jobs that aren't queued are not picked up."""
        sample_simulation.status = STATUS_RUNNING
        db.session.commit()

        assert _claim_next_job() is None


class TestMarkFailed:
    """Test the safety-net failure handler."""

    def test_marks_queued_sim_as_failed(self, db, sample_simulation):
        sample_simulation.status = STATUS_QUEUED
        db.session.commit()

        _mark_failed('simulation', sample_simulation.id)

        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status == STATUS_FAILED
        assert sim.error_message == 'Unexpected worker error'

    def test_marks_running_sim_as_failed(self, db, sample_simulation):
        sample_simulation.status = STATUS_RUNNING
        db.session.commit()

        _mark_failed('simulation', sample_simulation.id)

        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status == STATUS_FAILED

    def test_marks_queued_weld_as_failed(self, db, sample_weld_project):
        sample_weld_project.status = WELD_QUEUED
        db.session.commit()

        _mark_failed('weld', sample_weld_project.id)

        proj = db.session.get(WeldProject, sample_weld_project.id)
        assert proj.status == WELD_FAILED

    def test_ignores_completed(self, db, sample_simulation):
        """Don't overwrite completed status."""
        sample_simulation.status = 'completed'
        db.session.commit()

        _mark_failed('simulation', sample_simulation.id)

        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status == 'completed'

    def test_nonexistent_id(self, db):
        """Non-existent ID doesn't raise."""
        _mark_failed('simulation', 99999)  # Should not raise


class TestGetQueueStatus:
    """Test queue status reporting."""

    def test_empty(self, db):
        status = get_queue_status()
        assert status['running'] is None
        assert status['queued'] == []

    def test_running_simulation(self, db, sample_simulation):
        sample_simulation.status = STATUS_RUNNING
        db.session.commit()

        status = get_queue_status()
        assert status['running'] is not None
        assert status['running']['type'] == 'simulation'
        assert status['running']['name'] == 'Test Sim'

    def test_queued_list(self, db, engineer_user, sample_steel_grade):
        sim1 = Simulation(
            name='Q1', steel_grade_id=sample_steel_grade.id,
            user_id=engineer_user.id, geometry_type='cylinder',
            process_type='quench_water', status=STATUS_QUEUED,
        )
        sim2 = Simulation(
            name='Q2', steel_grade_id=sample_steel_grade.id,
            user_id=engineer_user.id, geometry_type='cylinder',
            process_type='quench_water', status=STATUS_QUEUED,
        )
        db.session.add_all([sim1, sim2])
        db.session.commit()

        status = get_queue_status()
        assert len(status['queued']) == 2
        assert status['queued'][0]['position'] == 1
        assert status['queued'][1]['position'] == 2


class TestGetQueuePosition:
    """Test queue position lookup."""

    def test_queued_job_has_position(self, db, sample_simulation):
        sample_simulation.status = STATUS_QUEUED
        db.session.commit()

        pos = get_queue_position('simulation', sample_simulation.id)
        assert pos == 1

    def test_non_queued_returns_none(self, db, sample_simulation):
        sample_simulation.status = STATUS_READY
        db.session.commit()

        pos = get_queue_position('simulation', sample_simulation.id)
        assert pos is None

    def test_nonexistent_returns_none(self, db):
        pos = get_queue_position('simulation', 99999)
        assert pos is None


class TestSimulationQueueRoutes:
    """Test the simulation enqueue, progress, and cancel routes."""

    def test_run_sets_queued(self, logged_in_client, sample_simulation, db):
        """POST to run sets status to queued and redirects to progress."""
        sample_simulation.status = STATUS_READY
        db.session.commit()

        rv = logged_in_client.post(
            f'/simulation/{sample_simulation.id}/run',
            follow_redirects=False)
        assert rv.status_code == 302
        assert '/progress' in rv.headers.get('Location', '')

        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status == STATUS_QUEUED

    def test_run_draft_blocked(self, logged_in_client, sample_simulation, db):
        """Draft simulation cannot be queued."""
        rv = logged_in_client.post(
            f'/simulation/{sample_simulation.id}/run',
            follow_redirects=True)
        assert rv.status_code == 200
        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status != STATUS_QUEUED

    def test_progress_renders(self, logged_in_client, sample_simulation, db):
        """Progress page renders for queued simulation."""
        sample_simulation.status = STATUS_QUEUED
        db.session.commit()

        rv = logged_in_client.get(f'/simulation/{sample_simulation.id}/progress')
        assert rv.status_code == 200
        assert b'Queued' in rv.data

    def test_progress_status_json(self, logged_in_client, sample_simulation, db):
        """Progress status endpoint returns JSON."""
        sample_simulation.status = STATUS_QUEUED
        db.session.commit()

        rv = logged_in_client.get(
            f'/simulation/{sample_simulation.id}/progress/status')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['status'] == 'queued'
        assert data['queue_position'] == 1

    def test_cancel_queued(self, logged_in_client, sample_simulation, db):
        """Cancelling a queued simulation returns it to ready."""
        sample_simulation.status = STATUS_QUEUED
        db.session.commit()

        rv = logged_in_client.post(
            f'/simulation/{sample_simulation.id}/cancel',
            follow_redirects=False)
        assert rv.status_code == 302

        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status == STATUS_READY

    def test_cancel_non_queued_blocked(self, logged_in_client, sample_simulation, db):
        """Cannot cancel a simulation that is not queued."""
        sample_simulation.status = STATUS_RUNNING
        db.session.commit()

        rv = logged_in_client.post(
            f'/simulation/{sample_simulation.id}/cancel',
            follow_redirects=True)
        assert rv.status_code == 200
        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.status == STATUS_RUNNING

    def test_progress_access_denied(self, logged_in_client, db, sample_steel_grade, admin_user):
        """Cannot view another user's progress page."""
        sim = Simulation(
            name='Other', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, geometry_type='cylinder',
            process_type='quench_water', status=STATUS_QUEUED,
        )
        db.session.add(sim)
        db.session.commit()

        rv = logged_in_client.get(f'/simulation/{sim.id}/progress',
                                   follow_redirects=False)
        assert rv.status_code == 302


class TestWeldQueueRoutes:
    """Test that weld project run enqueues instead of running sync."""

    def test_run_sets_queued(self, logged_in_client, sample_weld_project, db):
        """POST to run sets status to queued."""
        # Make project runnable
        ws = WeldString(
            project_id=sample_weld_project.id,
            string_number=1, layer=1, position_in_layer=1,
            name='Root', status='pending',
        )
        db.session.add(ws)
        sample_weld_project.status = STATUS_CONFIGURED
        sample_weld_project.total_strings = 1
        db.session.commit()

        rv = logged_in_client.post(
            f'/welding/{sample_weld_project.id}/run',
            data={'use_mock_solver': True},
            follow_redirects=False)
        assert rv.status_code == 302
        assert '/progress' in rv.headers.get('Location', '')

        proj = db.session.get(WeldProject, sample_weld_project.id)
        assert proj.status == WELD_QUEUED

    def test_progress_status_includes_queue_position(self, logged_in_client, sample_weld_project, db):
        """Progress status JSON includes queue_position."""
        sample_weld_project.status = WELD_QUEUED
        sample_weld_project.total_strings = 1
        db.session.commit()

        rv = logged_in_client.get(
            f'/welding/{sample_weld_project.id}/progress/status')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'queue_position' in data
