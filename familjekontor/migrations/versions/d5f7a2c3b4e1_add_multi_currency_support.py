"""Add multi-currency support

Revision ID: d5f7a2c3b4e1
Revises: ac26edcef0e3
Create Date: 2026-02-10 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5f7a2c3b4e1'
down_revision = 'ac26edcef0e3'
branch_labels = None
depends_on = None


def upgrade():
    # Create exchange_rates table
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('rate', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('inverse_rate', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('currency_code', 'rate_date', name='uq_currency_rate_date'),
    )

    # Add columns to supplier_invoices
    with op.batch_alter_table('supplier_invoices') as batch_op:
        batch_op.add_column(sa.Column('exchange_rate', sa.Numeric(precision=10, scale=6), server_default='1.0'))
        batch_op.add_column(sa.Column('amount_sek', sa.Numeric(precision=15, scale=2), nullable=True))

    # Add amount_sek to customer_invoices
    with op.batch_alter_table('customer_invoices') as batch_op:
        batch_op.add_column(sa.Column('amount_sek', sa.Numeric(precision=15, scale=2), nullable=True))

    # Add currency metadata to verification_rows
    with op.batch_alter_table('verification_rows') as batch_op:
        batch_op.add_column(sa.Column('currency', sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column('foreign_amount_debit', sa.Numeric(precision=15, scale=2), nullable=True))
        batch_op.add_column(sa.Column('foreign_amount_credit', sa.Numeric(precision=15, scale=2), nullable=True))
        batch_op.add_column(sa.Column('exchange_rate', sa.Numeric(precision=10, scale=6), nullable=True))

    # Add currency to bank_accounts
    with op.batch_alter_table('bank_accounts') as batch_op:
        batch_op.add_column(sa.Column('currency', sa.String(length=3), server_default='SEK'))

    # Add default_currency to suppliers
    with op.batch_alter_table('suppliers') as batch_op:
        batch_op.add_column(sa.Column('default_currency', sa.String(length=3), server_default='SEK'))


def downgrade():
    with op.batch_alter_table('suppliers') as batch_op:
        batch_op.drop_column('default_currency')

    with op.batch_alter_table('bank_accounts') as batch_op:
        batch_op.drop_column('currency')

    with op.batch_alter_table('verification_rows') as batch_op:
        batch_op.drop_column('exchange_rate')
        batch_op.drop_column('foreign_amount_credit')
        batch_op.drop_column('foreign_amount_debit')
        batch_op.drop_column('currency')

    with op.batch_alter_table('customer_invoices') as batch_op:
        batch_op.drop_column('amount_sek')

    with op.batch_alter_table('supplier_invoices') as batch_op:
        batch_op.drop_column('amount_sek')
        batch_op.drop_column('exchange_rate')

    op.drop_table('exchange_rates')
