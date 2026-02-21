"""add_learned_mappings_to_suppliers

Revision ID: c96b9d3419fb
Revises: b808cfac48fb
Create Date: 2026-02-21 09:36:00.873910

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c96b9d3419fb'
down_revision = 'b808cfac48fb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('learned_mappings', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_column('learned_mappings')
