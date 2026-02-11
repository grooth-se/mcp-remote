"""Add steel compositions table and result_data column.

Revision ID: 002_compositions
Revises: 001_cad_geometry
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_compositions'
down_revision = '001_cad_geometry'
branch_labels = None
depends_on = None


def upgrade():
    """Add steel_compositions table and result_data column."""
    # Create steel_compositions table
    op.create_table(
        'steel_compositions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('steel_grade_id', sa.Integer(), sa.ForeignKey('steel_grades.id'), nullable=False, unique=True),
        # Primary elements (wt%)
        sa.Column('carbon', sa.Float(), nullable=False),
        sa.Column('manganese', sa.Float(), default=0.0),
        sa.Column('silicon', sa.Float(), default=0.0),
        # Secondary alloying elements
        sa.Column('chromium', sa.Float(), default=0.0),
        sa.Column('nickel', sa.Float(), default=0.0),
        sa.Column('molybdenum', sa.Float(), default=0.0),
        sa.Column('vanadium', sa.Float(), default=0.0),
        # Additional elements
        sa.Column('tungsten', sa.Float(), default=0.0),
        sa.Column('copper', sa.Float(), default=0.0),
        sa.Column('phosphorus', sa.Float(), default=0.0),
        sa.Column('sulfur', sa.Float(), default=0.0),
        sa.Column('nitrogen', sa.Float(), default=0.0),
        sa.Column('boron', sa.Float(), default=0.0),
        # Metadata
        sa.Column('source', sa.Text()),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_index('ix_steel_compositions_steel_grade', 'steel_compositions', ['steel_grade_id'])

    # Add result_data column to simulation_results
    with op.batch_alter_table('simulation_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('result_data', sa.Text(), nullable=True))


def downgrade():
    """Remove steel_compositions table and result_data column."""
    with op.batch_alter_table('simulation_results', schema=None) as batch_op:
        batch_op.drop_column('result_data')

    op.drop_index('ix_steel_compositions_steel_grade', table_name='steel_compositions')
    op.drop_table('steel_compositions')
