"""Add CAD geometry fields to simulations table.

Revision ID: 001_cad_geometry
Revises:
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_cad_geometry'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add CAD geometry columns to simulations table."""
    with op.batch_alter_table('simulations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cad_filename', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('cad_file_path', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('cad_analysis', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('cad_equivalent_type', sa.Text(), nullable=True))


def downgrade():
    """Remove CAD geometry columns from simulations table."""
    with op.batch_alter_table('simulations', schema=None) as batch_op:
        batch_op.drop_column('cad_equivalent_type')
        batch_op.drop_column('cad_analysis')
        batch_op.drop_column('cad_file_path')
        batch_op.drop_column('cad_filename')
