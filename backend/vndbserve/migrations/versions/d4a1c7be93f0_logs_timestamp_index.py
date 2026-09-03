"""index logs.timestamp

Every read of the `logs` table is by time: logserve lists newest-first and
filters on a range, and the nightly retention job selects the rows past their
window. Without the index each of those is a sequential scan, which is what the
table had grown to 608,000 rows and 515 MB of.

Revision ID: d4a1c7be93f0
Revises: a7f3c9d2e8b1
Create Date: 2026-09-03
"""
from alembic import op

revision = 'd4a1c7be93f0'
down_revision = 'a7f3c9d2e8b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_logs_timestamp', 'logs', ['timestamp'], if_not_exists=True)


def downgrade():
    op.drop_index('ix_logs_timestamp', table_name='logs', if_exists=True)
