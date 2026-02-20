"""Add hollomon_jaffe_c column to steel_compositions.

Revision ID: 003_hollomon_jaffe
Revises: 002_compositions
Create Date: 2026-02-18

This migration targets the 'materials' bind database where
steel_compositions lives. It uses get_bind_engine() to connect
to the correct database.
"""
from alembic import op
import sqlalchemy as sa
from flask import current_app


# revision identifiers, used by Alembic.
revision = '003_hollomon_jaffe'
down_revision = '002_compositions'
branch_labels = None
depends_on = None


def _get_materials_engine():
    """Get SQLAlchemy engine for the materials bind."""
    db = current_app.extensions['migrate'].db
    # Flask-SQLAlchemy >=3
    return db.engines['materials']


def upgrade():
    """Add hollomon_jaffe_c column to steel_compositions in materials DB."""
    engine = _get_materials_engine()
    with engine.connect() as conn:
        # Check if column already exists (idempotent)
        inspector = sa.inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('steel_compositions')]
        if 'hollomon_jaffe_c' not in columns:
            conn.execute(sa.text(
                'ALTER TABLE steel_compositions ADD COLUMN hollomon_jaffe_c FLOAT DEFAULT 20.0'
            ))
            conn.commit()


def downgrade():
    """Remove hollomon_jaffe_c column from steel_compositions in materials DB."""
    engine = _get_materials_engine()
    with engine.connect() as conn:
        # SQLite doesn't support DROP COLUMN before 3.35.0
        # Use a safe approach: ignore if it fails
        try:
            conn.execute(sa.text(
                'ALTER TABLE steel_compositions DROP COLUMN hollomon_jaffe_c'
            ))
            conn.commit()
        except Exception:
            pass
