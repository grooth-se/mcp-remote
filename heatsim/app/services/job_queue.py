"""Simple DB-backed simulation job queue.

A single daemon thread polls the database for queued jobs and executes
them one at a time.  No Celery, no Redis — just a thread + DB polling.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Optional, Tuple

from flask import Flask

from app.extensions import db
from app.models.simulation import Simulation, STATUS_QUEUED as SIM_QUEUED, STATUS_RUNNING as SIM_RUNNING, STATUS_FAILED as SIM_FAILED
from app.models.weld_project import WeldProject, STATUS_QUEUED as WELD_QUEUED, STATUS_RUNNING as WELD_RUNNING, STATUS_FAILED as WELD_FAILED

logger = logging.getLogger(__name__)

_worker_thread: Optional[threading.Thread] = None
_shutdown_event = threading.Event()

# Poll interval in seconds
POLL_INTERVAL = 2.0


def start_worker(app: Flask) -> None:
    """Start the background worker thread.

    Should be called once after the app and DB are initialized.
    Skipped automatically in testing mode.
    """
    global _worker_thread

    if app.config.get('TESTING'):
        return

    if _worker_thread is not None and _worker_thread.is_alive():
        return

    _shutdown_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(app,),
        name='job-queue-worker',
        daemon=True,
    )
    _worker_thread.start()
    app.logger.info("Job queue worker thread started")


def stop_worker() -> None:
    """Signal the worker thread to stop."""
    _shutdown_event.set()


def _worker_loop(app: Flask) -> None:
    """Main worker loop — polls DB for queued jobs every POLL_INTERVAL seconds."""
    while not _shutdown_event.is_set():
        try:
            with app.app_context():
                job = _claim_next_job()
                if job:
                    job_type, job_id = job
                    _execute_job(job_type, job_id)
        except Exception:
            logger.exception("Unexpected error in worker loop")

        _shutdown_event.wait(timeout=POLL_INTERVAL)


def _claim_next_job() -> Optional[Tuple[str, int]]:
    """Find and claim the oldest queued job.

    Returns (job_type, job_id) or None if no queued jobs.
    job_type is 'simulation' or 'weld'.
    """
    # Find oldest queued simulation
    sim = (Simulation.query
           .filter_by(status='queued')
           .order_by(Simulation.created_at.asc())
           .first())

    # Find oldest queued weld project
    weld = (WeldProject.query
            .filter_by(status='queued')
            .order_by(WeldProject.created_at.asc())
            .first())

    if sim is None and weld is None:
        return None

    # Pick the one that was queued first
    if sim and weld:
        # Compare by created_at (queued_at is approximated by created_at for ordering)
        # Both are queued — pick whichever was queued earlier
        # We use started_at as None for queued items, so fallback to id ordering
        if sim.id < weld.id:
            job_type, job_id = 'simulation', sim.id
        else:
            job_type, job_id = 'weld', weld.id
    elif sim:
        job_type, job_id = 'simulation', sim.id
    else:
        job_type, job_id = 'weld', weld.id

    return (job_type, job_id)


def _execute_job(job_type: str, job_id: int) -> None:
    """Dispatch a claimed job to the appropriate runner."""
    logger.info("Executing %s job #%d", job_type, job_id)

    try:
        if job_type == 'simulation':
            from app.services.simulation_runner import run_heat_treatment
            run_heat_treatment(job_id)
        elif job_type == 'weld':
            from app.services.weld_runner import run_weld_simulation
            run_weld_simulation(job_id)
        else:
            logger.error("Unknown job type: %s", job_type)
    except Exception:
        logger.exception("Job %s #%d failed with uncaught exception", job_type, job_id)
        _mark_failed(job_type, job_id)


def _mark_failed(job_type: str, job_id: int) -> None:
    """Safety net: mark a job as failed if an uncaught exception occurs."""
    try:
        if job_type == 'simulation':
            sim = db.session.get(Simulation, job_id)
            if sim and sim.status in ('queued', 'running'):
                sim.status = SIM_FAILED
                sim.error_message = 'Unexpected worker error'
                db.session.commit()
        elif job_type == 'weld':
            proj = db.session.get(WeldProject, job_id)
            if proj and proj.status in ('queued', 'running'):
                proj.status = WELD_FAILED
                proj.error_message = 'Unexpected worker error'
                db.session.commit()
    except Exception:
        logger.exception("Failed to mark job as failed: %s #%d", job_type, job_id)


def get_queue_status() -> dict:
    """Return current queue status for UI display.

    Returns dict with:
        running: {type, id, name} or None
        queued: [{type, id, name, position}, ...]
    """
    running_job = None
    queued_jobs = []

    # Check running
    running_sim = Simulation.query.filter_by(status='running').first()
    if running_sim:
        running_job = {'type': 'simulation', 'id': running_sim.id, 'name': running_sim.name}

    running_weld = WeldProject.query.filter_by(status='running').first()
    if running_weld:
        running_job = {'type': 'weld', 'id': running_weld.id, 'name': running_weld.name}

    # Collect queued items
    queued_sims = (Simulation.query
                   .filter_by(status='queued')
                   .order_by(Simulation.created_at.asc())
                   .all())
    queued_welds = (WeldProject.query
                    .filter_by(status='queued')
                    .order_by(WeldProject.created_at.asc())
                    .all())

    # Merge into single ordered list by id (FIFO approximation)
    all_queued = []
    for s in queued_sims:
        all_queued.append(('simulation', s.id, s.name, s.created_at))
    for w in queued_welds:
        all_queued.append(('weld', w.id, w.name, w.created_at))

    all_queued.sort(key=lambda x: (x[3], x[1]))  # Sort by created_at, then id

    for pos, (jtype, jid, jname, _) in enumerate(all_queued, 1):
        queued_jobs.append({
            'type': jtype,
            'id': jid,
            'name': jname,
            'position': pos,
        })

    return {
        'running': running_job,
        'queued': queued_jobs,
    }


def get_queue_position(job_type: str, job_id: int) -> Optional[int]:
    """Get the queue position for a specific job, or None if not queued."""
    status = get_queue_status()
    for item in status['queued']:
        if item['type'] == job_type and item['id'] == job_id:
            return item['position']
    return None
