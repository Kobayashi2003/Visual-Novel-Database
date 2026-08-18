"""staff.aid: string -> integer

Revision ID: c16c4dffd524
Revises: bed0ff691e6a
Create Date: 2026-05-24 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c16c4dffd524'
down_revision = 'bed0ff691e6a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('staff', schema=None) as batch_op:
        batch_op.alter_column(
            'aid',
            existing_type=sa.VARCHAR(),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using='aid::integer',
        )


def downgrade():
    with op.batch_alter_table('staff', schema=None) as batch_op:
        batch_op.alter_column(
            'aid',
            existing_type=sa.Integer(),
            type_=sa.VARCHAR(),
            existing_nullable=True,
        )
