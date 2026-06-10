"""Smoke tests for Heatsim.

These are intentionally minimal: they prove the app boots, both database
binds are wired up, all blueprints are registered, and basic routes
respond. They are not a substitute for the full feature suite — their job
is to give the Claude Code Stop gate something real to verify, so broken
imports or fatal configuration errors get caught before Claude declares a
task complete.

Run with: pytest tests/test_smoke.py -x --tb=short
"""

import os

# Force testing config + offscreen rendering before importing the app.
os.environ.setdefault("FLASK_CONFIG", "testing")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from app import create_app

EXPECTED_BLUEPRINTS = (
    "main",
    "auth",
    "materials",
    "simulation",
    "welding",
    "ht_templates",
    "measured",
    "admin",
    "api",
    "ttt_cct",
)


def test_app_factory_returns_app():
    """create_app() returns a Flask instance for each known config."""
    for config_name in ("development", "testing", "default"):
        instance = create_app(config_name)
        assert instance is not None
        assert instance.name


def test_app_has_expected_blueprints(app):
    """All known blueprints are registered."""
    for bp in EXPECTED_BLUEPRINTS:
        assert bp in app.blueprints, f"missing blueprint: {bp}"


def test_app_has_materials_bind(app):
    """SQLAlchemy is configured with the materials read/write bind."""
    binds = app.config.get("SQLALCHEMY_BINDS") or {}
    assert isinstance(binds, dict)
    assert "materials" in binds, "materials bind missing from SQLALCHEMY_BINDS"


def test_models_import_cleanly():
    """All Heatsim models import without errors.

    Catches the kind of breakage refactors could introduce — circular
    imports, missing columns, broken relationships.
    """
    from app.models import (  # noqa: F401
        HeatTreatmentTemplate,
        Simulation,
        SteelGrade,
        User,
        WeldProject,
    )


def test_services_import_cleanly():
    """Key service modules import without errors."""
    from app.services import job_queue  # noqa: F401


def test_root_responds(client):
    """The root URL returns something sensible (200/302/401/404)."""
    response = client.get("/")
    assert response.status_code in (200, 302, 401, 404), (
        f"Root returned unexpected status {response.status_code}"
    )


def test_app_does_not_500_on_unknown_route(client):
    """Unknown routes return 404, not 500."""
    response = client.get("/this-route-does-not-exist-12345")
    assert response.status_code == 404
