# `vndbserve/database`

The mirror of VNDB, and the only layer that opens a SQLAlchemy session.
`search`, `tasks`, `schedule` and `routes` reach the database through the names
exported here.

| Module | Contents |
| --- | --- |
| `models.py` | The tables, as ORM classes |
| `operations.py` | Every read and write against them |
| `common.py` | A row as a plain dict, for a JSON response |
| `logs.py` | The `logs` table, which is not a mirrored table |
| `commands.py` | `flask` CLI commands for the database as a whole |
| `__init__.py` | Re-exports; contains no logic |

---

## No foreign keys

No table declares one. `VN.tags`, `VN.characters`, `Character.traits` and the
rest store the JSON array the Kana API returned, and the database does not
constrain what those ids reference.

A foreign key requires the referenced row to exist. Storing one VN under that
requirement would mean fetching its characters, tags, releases, producers and
staff in the same operation, and the constraint would reject the write until all
of them were present. Each of those entities has relations of its own, so the
size of the fetch is not bounded by anything the caller states.

Storing relations as a JSON column removes the requirement. The array records
what the API reported at crawl time and asserts nothing about other tables.

For the same reason `convert_remote_to_local` drops `role`, `spoiler`, `rating`,
`lie` and `rtype` before a nested entity can become a row of its own: these
describe the relation rather than the entity, and a foreign key has no place for
them.

Two consequences:

* Only a `large` reply is persisted. A `small` reply is a narrower view of the
  same entity; storing it would replace a complete row with fewer fields.
* Embedded fidelity differs by direction — `VN.characters` includes images,
  `Character.vns` does not — so `search/both` serves the first direction from
  the parent document and the second from the remote API.

The same recursion appears at display time, where the answer is the `small`
response shape; see `docs/search/README.md`.

The column type is `JSONB` rather than `ARRAY(JSONB)`, so that a GIN
`jsonb_path_ops` index can serve `@>` containment, which is what every tag and
trait filter compiles to. `ARRAY(JSONB)` would require an `unnest` per row.

---

## `models.py`

Seven mirrored entity tables — `VN`, `Release`, `Character`, `Producer`,
`Staff`, `Tag`, `Trait` — and `LogEntry`.

`MODEL_MAP` maps a resource type (`'vn'`, `'tag'`, …) to its class; `ModelType`
is the union of the seven. Every operation below takes a `resource_type` string
rather than a class, so that only this layer resolves one to the other.

### Lifecycle columns

Five columns on every mirrored table. `operations.py` maintains them and
`PROTECTED_COLUMNS` prevents a caller from writing them.

| Column | Set on | Read by |
| --- | --- | --- |
| `created_at` | first write of the row | — |
| `updated_at` | any write | sorting |
| `crawled_at` | a write originating from VNDB | freshness, `updatable` |
| `edited_at` | a manual edit | `updatable`, which then refuses to overwrite |
| `deleted_at` | a soft delete | every read, which filters the row out |

`crawled_at` is separate from `updated_at` because an edit bumps `updated_at`.
Judging freshness by `updated_at` would make an edited row appear freshly
crawled and admit it to the next crawl.

`crawled_at` records when the content was true, not when the row was written. A
reply served from the response cache is as old as its fetch, so the caller
storing it passes that time in rather than letting it default to the present.

---

## `operations.py`

### Two functions per operation

Each operation is a private `_name` that performs the work and a public `name`
that wraps it.

The private functions call each other: `_create` clears the trash, `_update`
reads the row first, `updatable` reads the row. A wrapper on each would nest,
opening a transaction inside a transaction. On the public name it runs once
regardless of nesting depth.

The split also gives a rule that can be checked mechanically: nothing outside
this module imports a `_name`. The public names are the boundary.

### The two wrappers

**`@translates_db_errors` — on every read.** Converts driver exceptions into the
three kinds: `OperationalError` and `InterfaceError` become `Unavailable`, any
other `SQLAlchemyError` becomes `Failed`. It rolls the session back first,
because a failed statement leaves the session unusable for the next one.

It rolls back only for driver exceptions. Others pass through: a read has
nothing of its own to undo, and the caller may hold uncommitted work.

A read also never commits, for the same reason — a commit would end the
transaction the caller is in.

**`@commits` — on every write.** Opens a savepoint and commits on return. It
declares no exception handler.

Leaving the savepoint block by exception rolls back the savepoint alone, so the
caller's uncommitted work survives. A `session.rollback()` here would discard
it, so driver exceptions are left to `translates_db_errors`, where a full
rollback is correct.

Committing before returning is required by `docs/standards/storing-data.md` §4.

### Reads

| Name | Returns |
| --- | --- |
| `get(resource_type, id)` | one live row, or `None` |
| `get_all(resource_type, page, limit, sort, reverse)` | live rows |
| `get_inactive(resource_type, id)` | one row from the trash, or `None` |
| `get_inactive_all(...)` | rows from the trash |
| `exists(resource_type, id)` | whether a live row holds that id |
| `count_all` / `count_inactive_all` | how many live / trashed rows |
| `updatable(resource_type, id)` | whether an automatic crawl may write the row |

`updatable` protects manual edits. A row that does not exist, or has never been
crawled, may be written; a row with `edited_at` set may not, since an automatic
sync would overwrite the edit without reporting it. `AUTO_CRAWL_INTERVAL`
(10 minutes) additionally prevents concurrent stale reads from queueing
duplicate fetches of the same row.

The listing reads return at most `MAX_ROWS` (100). This is a ceiling rather than
a page size — callers state the page size — so that an incorrect `limit` cannot
load a whole table into memory.

### Writes

| Name | Effect | Returns |
| --- | --- | --- |
| `create(resource_type, id, data, source, crawled_at)` | insert | the row, or `None` if the id is taken |
| `update(resource_type, id, data, source, crawled_at)` | overwrite the given columns | the row, or `None` if there is no such row |
| `delete(resource_type, id)` | soft delete: sets `deleted_at`, the row remains | the row, or `None` |
| `delete_all(resource_type)` | soft delete every live row | how many |
| `recover(resource_type, id)` | restore one row from the trash | the row, or `None` |
| `recover_all(resource_type)` | restore all | how many |
| `cleanup(resource_type, id)` | delete one row from the trash permanently | the row, or `None` |
| `cleanup_all(resource_type)` | empty the trash | how many |

`cleanup` is the only path in the service that deletes a row permanently.

`update` writes only the keys it is given, so a caller holding part of a row —
a dump that fills some columns and not others — leaves the rest unchanged.

### `source`

| Value | Meaning | Stamps |
| --- | --- | --- |
| `'crawl'` (default) | fetched from the remote API | `crawled_at`, from the `crawled_at` argument when given |
| `'edit'` | a manual user edit | `edited_at`, which excludes the row from automatic sync |
| `'refresh'` | an explicit re-crawl of one row | `crawled_at`, and clears `edited_at` |
| `None` | a maintenance write, such as a backfill | neither |

`'refresh'` clears `edited_at`, which returns an edited row to the automatic
cycle: requesting a refresh discards the edit.

### `None` is an answer, not a failure

A read returns `None` when the value is absent. A write returns `None` when the
requested state already holds: `create` finds the id taken, `update` and
`delete` find no such row.

A failure raises. Whether an absence becomes a `404` is decided by the layer
that knows the request's intent, which is why deleting an already-absent row is
reported as success and reading one is not.

---

## `common.py`

`convert_model_to_dict(model)` returns a row as a plain dict for a JSON
response; `convert_value` converts one value.

It walks columns only: with no foreign keys there are no relationships to
follow. Datetimes become ISO strings. JSONB and array columns need no case of
their own, as their values arrive as dicts and lists.

---

## `logs.py`

`add_log_entry(level, message, details)` writes one row to the `logs` table,
which logserve reads.

It runs on a session of its own, which is why it is separate from
`operations.py`:

* the `logs` table is neither mirrored nor part of a request's own work;
* a write made while observing must not determine when the observed work is
  committed. Sharing the request's session would commit whatever the caller had
  pending, and a failure here would leave that session unusable.

---

## `commands.py`

`flask` CLI commands, registered by `register_commands(app)`:

| Command | Effect |
| --- | --- |
| `init-db` | create the tables; `--drop` recreates them |
| `drop-db` | drop every table |
| `clean-db` | empty tables, all or those named with `-t` |
| `inspect-db` | print the schema: columns and foreign keys |
| `backup-db` | `pg_dump` to a file |
| `restore-db` | restore from a file |

These are operator tools and are not reached by a request. `clean-db`,
`backup-db` and `restore-db` report failures per item and continue; the rest let
the exception reach the CLI.

---

## Adding to this layer

* A new operation has two functions: `_name` for the work and `name` for the
  boundary, wrapped by whichever wrapper matches its direction.
* Nothing outside this module imports a `_name`. If something needs to, the
  boundary is in the wrong place.
* A new column requires a migration (`vndbserve/migrations/`, Alembic). A
  lifecycle column is added to `PROTECTED_COLUMNS`.
