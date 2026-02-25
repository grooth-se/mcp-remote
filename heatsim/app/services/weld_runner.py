"""Weld simulation runner for background job execution.

Extracted from app/welding/routes.py to run inside the worker thread
without a Flask request context.
"""
import json
import logging
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.weld_project import (
    WeldProject, WeldResult,
    STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
)

logger = logging.getLogger(__name__)


def run_weld_simulation(project_id: int) -> None:
    """Execute a weld simulation.

    This function is called from the worker thread with an app context
    already pushed.  It must NOT use flash() or any request-context helpers.
    """
    project = db.session.get(WeldProject, project_id)
    if project is None:
        logger.error("Weld project %d not found", project_id)
        return

    # Check if this is a goldak multipass job
    if (project.progress_message or '').startswith('goldak:'):
        _run_goldak_multipass(project)
        return

    from app.services.comsol import COMSOLClient, COMSOLNotAvailableError, COMSOLError
    from app.services.comsol.client import MockCOMSOLClient
    from app.services.comsol.sequential_solver import SequentialSolver, MockSequentialSolver
    from app.services.comsol.model_builder import WeldModelBuilder

    results_folder = current_app.config.get('RESULTS_FOLDER', 'data/results')

    # Check if mock solver was requested (stored in progress_message by the route)
    use_mock = (project.progress_message or '').startswith('mock:')
    if use_mock:
        # Clear the mock flag from progress_message
        project.progress_message = 'Initializing...'
        db.session.commit()

    if use_mock:
        client = MockCOMSOLClient()
        builder = WeldModelBuilder(client)
        solver = MockSequentialSolver(client, builder, results_folder)
    else:
        try:
            client = COMSOLClient()
            client.connect()
            builder = WeldModelBuilder(client)
            solver = SequentialSolver(client, builder, results_folder)
        except (COMSOLNotAvailableError, COMSOLError):
            logger.warning("COMSOL not available, using mock solver")
            client = MockCOMSOLClient()
            builder = WeldModelBuilder(client)
            solver = MockSequentialSolver(client, builder, results_folder)

    try:
        solver.run_project(project, db_session=db.session)
    finally:
        if hasattr(client, 'disconnect'):
            try:
                client.disconnect()
            except Exception:
                pass


def _run_goldak_multipass(project: WeldProject) -> None:
    """Run Goldak multipass simulation in background."""
    from app.services.goldak_multipass import GoldakMultiPassSolver

    # Parse config from progress_message: 'goldak:preset:compare'
    parts = project.progress_message.split(':')
    preset = parts[1] if len(parts) > 1 else 'medium'
    compare = parts[2] == 'true' if len(parts) > 2 else True

    project.status = STATUS_RUNNING
    project.started_at = datetime.utcnow()
    project.progress_message = 'Initializing Goldak multi-pass...'
    project.progress_percent = 0.0
    db.session.commit()

    try:
        solver = GoldakMultiPassSolver.with_preset(
            project, preset=preset, compare=compare,
        )
        n_passes = project.total_strings or 1

        def progress_cb(fraction):
            current_pass = min(int(fraction * n_passes) + 1, n_passes)
            project.progress_percent = fraction * 100
            project.progress_message = f'Pass {current_pass}/{n_passes}'
            db.session.commit()

        result = solver.run(progress_callback=progress_cb)

        # Delete previous goldak_multipass results for this project
        WeldResult.query.filter_by(
            project_id=project.id, result_type='goldak_multipass',
        ).delete()

        # Store result as WeldResult with full JSON
        wr = WeldResult(project_id=project.id, result_type='goldak_multipass')
        wr.time_data = json.dumps(result.to_dict())
        db.session.add(wr)

        project.status = STATUS_COMPLETED
        project.completed_at = datetime.utcnow()
        project.progress_percent = 100.0
        project.progress_message = 'Goldak multi-pass complete'
        db.session.commit()
    except Exception as e:
        project.status = STATUS_FAILED
        project.error_message = str(e)
        project.progress_message = None
        db.session.commit()
        raise
