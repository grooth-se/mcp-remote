"""add_cost_centers_table

Revision ID: 97bb2f9e101d
Revises: c96b9d3419fb
Create Date: 2026-02-21 09:47:47.990718

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '97bb2f9e101d'
down_revision = 'c96b9d3419fb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cost_centers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id', 'code', name='uq_cost_center_company_code')
    )


def downgrade():
    op.drop_table('cost_centers')
