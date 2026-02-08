"""Add payment_verification_id to invoices

Revision ID: ac26edcef0e3
Revises: c4a864ca1942
Create Date: 2026-02-08 23:09:10.769487

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ac26edcef0e3'
down_revision = 'c4a864ca1942'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('customer_invoices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_verification_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_customer_invoice_payment_ver', 'verifications', ['payment_verification_id'], ['id'])

    with op.batch_alter_table('supplier_invoices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_verification_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('paid_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_supplier_invoice_payment_ver', 'verifications', ['payment_verification_id'], ['id'])


def downgrade():
    with op.batch_alter_table('supplier_invoices', schema=None) as batch_op:
        batch_op.drop_constraint('fk_supplier_invoice_payment_ver', type_='foreignkey')
        batch_op.drop_column('paid_at')
        batch_op.drop_column('payment_verification_id')

    with op.batch_alter_table('customer_invoices', schema=None) as batch_op:
        batch_op.drop_constraint('fk_customer_invoice_payment_ver', type_='foreignkey')
        batch_op.drop_column('payment_verification_id')
