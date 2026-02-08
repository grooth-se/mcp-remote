"""Add valid_from column to documents

Revision ID: c4a864ca1942
Revises: 8685c5a6667f
Create Date: 2026-02-08 11:43:40.009117

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a864ca1942'
down_revision = '8685c5a6667f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('valid_from', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('valid_from')
