"""jsonb[] -> jsonb columns, GIN containment indexes, crawled_at/edited_at

- Converts every ARRAY(JSONB) column to plain JSONB (the same JSON arrays,
  via to_jsonb) so GIN jsonb_path_ops indexes can serve `@>` containment
  filters — jsonb[] columns cannot be GIN-indexed for key lookups at all.
- Adds GIN (jsonb_path_ops) indexes on the columns the local search filters
  with exact-id containment.
- Adds crawled_at (last write from the remote API; backfilled from
  updated_at) and edited_at (last manual edit; NULL) to all entity tables.

Revision ID: a7f3c9d2e8b1
Revises: c16c4dffd524
Create Date: 2026-06-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'a7f3c9d2e8b1'
down_revision = 'c16c4dffd524'
branch_labels = None
depends_on = None

ENTITY_TABLES = ['vns', 'releases', 'characters', 'producers', 'staff', 'tags', 'traits']

# Every ARRAY(JSONB) column, per table.
JSONB_ARRAY_COLUMNS = {
    'vns': ['titles', 'screenshots', 'relations', 'tags', 'developers', 'editions',
            'staff', 'va', 'extlinks', 'characters', 'releases', 'publishers'],
    'releases': ['languages', 'media', 'vns', 'producers', 'images', 'extlinks'],
    'characters': ['vns', 'traits', 'seiyuu'],
    'producers': ['extlinks'],
    'staff': ['extlinks', 'aliases'],
}

# Columns the local filters hit with `@>` exact-id containment.
GIN_INDEX_COLUMNS = {
    'vns': ['tags', 'characters', 'releases', 'staff', 'developers', 'relations'],
    'releases': ['vns', 'producers'],
    'characters': ['traits', 'vns', 'seiyuu'],
}

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_JSONB_ARRAY = postgresql.ARRAY(_JSONB)


def upgrade():
    for table, columns in JSONB_ARRAY_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column,
                existing_type=_JSONB_ARRAY,
                type_=_JSONB,
                postgresql_using=f'to_jsonb({column})',
            )

    for table, columns in GIN_INDEX_COLUMNS.items():
        for column in columns:
            op.create_index(
                f'ix_gin_{table}_{column}', table, [column],
                postgresql_using='gin',
                postgresql_ops={column: 'jsonb_path_ops'},
            )

    for table in ENTITY_TABLES:
        op.add_column(table, sa.Column('crawled_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True))
        # Until now every row was written exclusively by the crawler, so the
        # last write time is the last crawl time.
        op.execute(f'UPDATE {table} SET crawled_at = updated_at')


def downgrade():
    for table in ENTITY_TABLES:
        op.drop_column(table, 'edited_at')
        op.drop_column(table, 'crawled_at')

    for table, columns in GIN_INDEX_COLUMNS.items():
        for column in columns:
            op.drop_index(f'ix_gin_{table}_{column}', table_name=table)

    for table, columns in JSONB_ARRAY_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column,
                existing_type=_JSONB,
                type_=_JSONB_ARRAY,
                postgresql_using=(
                    f'CASE WHEN {column} IS NULL THEN NULL '
                    f'ELSE ARRAY(SELECT jsonb_array_elements({column})) END'
                ),
            )
