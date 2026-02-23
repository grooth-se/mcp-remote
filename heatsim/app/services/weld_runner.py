"""Weld simulation runner for background job execution.

Extracted from app/welding/routes.py to run inside the worker thread
without a Flask request context.
"""
import logging

from flask import current_app

from app.extensions import db
from app.models.weld_project import WeldProject

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

    from app.services.comsol import COMSOLClient, COMSOLNotAvailableError
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
        except COMSOLNotAvailableError:
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
