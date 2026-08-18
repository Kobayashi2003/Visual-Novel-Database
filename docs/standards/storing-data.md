# Storing data

## 1. Freshness

| Column | Moved by |
| --- | --- |
| `updated_at` | every write |
| `crawled_at` | `source='crawl'`, and `source='refresh'` |
| `edited_at` | `source='edit'`; cleared by `source='refresh'` |

While `edited_at` is set the row is frozen and automatic writes must leave it
alone. `updatable()` enforces that, and also refuses a row crawled within the
last ten minutes; an explicit refresh bypasses it. Age is measured from
`crawled_at`, never from `updated_at`.

- Declare the `source` of every write, put an automatic write through
  `updatable()` first, and let the write set these columns rather than the caller.

## 2. Soft delete

- Delete by setting `deleted_at`, filter it out of every ordinary read, and purge
  the deleted row carrying an id before creating that id again.

## 3. Relation columns

- Query a JSONB relation column with `@>` containment, so its GIN
  `jsonb_path_ops` index serves the query.

## 4. Writes

- Let every exported write commit before it returns; never leave that to the
  caller.
