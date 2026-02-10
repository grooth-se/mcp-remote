"""Add recurring invoice templates and line items

Revision ID: e6a8b3c4d5f2
Revises: d5f7a2c3b4e1
Create Date: 2026-02-10 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6a8b3c4d5f2'
down_revision = 'd5f7a2c3b4e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'recurring_invoice_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('currency', sa.String(3), server_default='SEK'),
        sa.Column('vat_type', sa.String(20), server_default='standard'),
        sa.Column('interval', sa.String(20), nullable=False),
        sa.Column('payment_terms', sa.Integer(), server_default='30'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('next_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='1'),
        sa.Column('last_generated_at', sa.DateTime(), nullable=True),
        sa.Column('invoices_generated', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'recurring_line_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(),
                  sa.ForeignKey('recurring_invoice_templates.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 2), server_default='1'),
        sa.Column('unit', sa.String(20), server_default='st'),
        sa.Column('unit_price', sa.Numeric(15, 2), nullable=False),
        sa.Column('vat_rate', sa.Numeric(5, 2), server_default='25'),
    )


def downgrade():
    op.drop_table('recurring_line_items')
    op.drop_table('recurring_invoice_templates')
