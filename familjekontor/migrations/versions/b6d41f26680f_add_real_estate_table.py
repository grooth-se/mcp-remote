"""add_real_estate_table

Revision ID: b6d41f26680f
Revises: 97bb2f9e101d
Create Date: 2026-02-21 09:51:14.785250

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6d41f26680f'
down_revision = '97bb2f9e101d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('real_estates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=True),
    sa.Column('property_name', sa.String(length=200), nullable=False),
    sa.Column('fastighetsbeteckning', sa.String(length=100), nullable=True),
    sa.Column('street_address', sa.String(length=200), nullable=True),
    sa.Column('postal_code', sa.String(length=10), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('taxeringsvarde', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('taxeringsvarde_year', sa.Integer(), nullable=True),
    sa.Column('property_tax_rate', sa.Numeric(precision=6, scale=4), nullable=True),
    sa.Column('monthly_rent_target', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('rent_account', sa.String(length=10), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['asset_id'], ['fixed_assets.id'], ),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('real_estates')
