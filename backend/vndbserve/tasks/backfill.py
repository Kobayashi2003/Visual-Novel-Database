"""Populate one column across a whole table, for after a schema change.

A migration adds a column but leaves it empty on existing rows. This walks the
table in batches and fills that one column — from the local row where the value
can be derived, or from a fresh Kana API fetch where it cannot. Only the named
column is written: the rest of the row, including any hand-edit, is left alone.

Driven from POST /admin/backfill, which runs it on a background thread.

Lives in the service layer, not in utils/: it reads through search and writes
through the data layer, which a general-purpose helper may not do.
"""

import time
from enum import Enum, auto
from typing import Any, Callable

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB as PgJSONB, ARRAY as PgARRAY

from vndbserve.database import update as db_update, get as db_get
from vndbserve.errors import Rejected
from vndbserve.database.models import MODEL_MAP
from vndbserve.logger import logger
from .common import task
from .envelope import format_results
from vndbserve.search.local.search import search as local_search
from vndbserve.search.remote.search import (
    search_vn, search_character, search_release,
    search_producer, search_staff, search_tag, search_trait,
)
from vndbserve.search.remote.filters import VNDBFilters, build_filters

# ─── Constants ────────────────────────────────────────────────────────────────

_DEFAULT_BATCH_SIZE     = 100
_DEFAULT_DELAY          = 2.0            # seconds between batch requests
_DEFAULT_OVERWRITE_NULL = False          # whether to write a null value obtained from a successful fetch
_TEST                   = False          # TEST: when True, log the writes instead of making them

_SEARCH_FUNCTIONS: dict[str, Callable] = {
    'vn':        search_vn,
    'character': search_character,
    'release':   search_release,
    'producer':  search_producer,
    'staff':     search_staff,
    'tag':       search_tag,
    'trait':     search_trait,
}

# ─── Private helpers ──────────────────────────────────────────────────────────

class _ColKind(Enum):
    SCALAR = auto()  # String, Integer, Float, Boolean, Text, ARRAY(String/Integer/…)
    JSONB  = auto()  # JSONB — holds a dict (supports dotted-path partial merge) or a list


def _nested_get(obj: Any, path: list[str]) -> Any:
    """The value at a key path through nested dicts, or None if a step is
    missing or holds something other than a dict."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _set_nested(obj: dict, path: list[str], value: Any) -> dict:
    """A copy of `obj` with the key path set to `value`, merging rather than
    replacing at each level so the keys beside it survive."""
    if len(path) == 1:
        return {**obj, path[0]: value}
    return {**obj, path[0]: _set_nested(obj.get(path[0]) or {}, path[1:], value)}


def _col_kind(resource_type: str, column_name: str) -> _ColKind:
    """What kind of column this is, or `Rejected` when there is no such column.

    An ARRAY column counts as SCALAR: it is written whole, like the rest, and
    only a JSONB column supports writing one key inside it.
    """
    model = MODEL_MAP.get(resource_type)
    if model is None:
        raise Rejected('invalid_request', f"Unknown resource type: {resource_type!r}")
    try:
        col_type = sa_inspect(model).columns[column_name].type
    except KeyError:
        raise Rejected('invalid_request', f"'{resource_type}' has no column '{column_name}'")
    if isinstance(col_type, PgARRAY):
        return _ColKind.SCALAR
    if isinstance(col_type, PgJSONB):
        return _ColKind.JSONB
    return _ColKind.SCALAR


def _resolve_field(resource_type: str, field: str) -> tuple[str, str, _ColKind]:
    """A field path split into the column it names and the path inside it.

    Validated here rather than at the write, so a sweep over a whole table is
    refused before its first request instead of after its last.
    """
    column, _, json_tail = field.partition(".")
    kind = _col_kind(resource_type, column)
    if json_tail and kind is not _ColKind.JSONB:
        raise Rejected(
            'invalid_request',
            f"Dotted path '{field}' is invalid: '{column}' is {kind.name}, only JSONB supports sub-key writes"
        )
    return column, json_tail, kind


def _build_db_write(
    resource_type: str,
    id_: str,
    column: str,
    json_tail: str,
    kind: _ColKind,
    value: Any,
) -> dict[str, Any]:
    """The `db_update` payload for one row, or `TypeError` if the value does not
    fit the column.

    A write inside a JSONB column has to read the row first: the merge keeps the
    keys beside the one being written, which only the stored value knows.
    """
    if value is not None and not json_tail:
        if kind is _ColKind.JSONB and not isinstance(value, (dict, list)):
            raise TypeError(f"Expected dict or list for JSONB, got {type(value).__name__}")
    if not json_tail:
        return {column: value}
    current_record = db_get(resource_type, id_)
    current_jsonb  = (getattr(current_record, column, None) or {}) if current_record else {}
    if not isinstance(current_jsonb, dict):
        raise TypeError(f"Dotted path write requires a dict-valued JSONB column, '{column}' holds {type(current_jsonb).__name__}")
    return {column: _set_nested(current_jsonb, json_tail.split("."), value)}


def _id_filter(filter_set: Any, ids: list[str]) -> Any:
    if len(ids) == 1:
        return build_filters(filter_set, {"id": ids[0]})
    return build_filters(filter_set, {"or": [{"id": id_} for id_ in ids]})


# ─── Public API ───────────────────────────────────────────────────────────────

def backfill_column(
    resource_type: str,
    field: str,
    extract: Callable[[dict], Any] | None = None,
    overwrite_null: bool = _DEFAULT_OVERWRITE_NULL,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    delay: float = _DEFAULT_DELAY,
) -> tuple[int, int]:
    """Re-fetch one field for every active row and write it back. Returns
    (updated, total).

    `field` names exactly one field — `gender`, or `image.sexual` for a key
    inside a JSONB column, where the write merges rather than replaces. A
    comma-separated list is refused: the extract below navigates a single path,
    so a list would silently fill the column with the first one.

    `extract` reads the value out of a remote record, and defaults to following
    `field` through it. `overwrite_null` decides whether a fetch that succeeded
    and returned nothing clears the column; a fetch that failed never writes
    either way. `batch_size` is rows per API request (100 is the API's own
    ceiling) and `delay` the pause between them, which is what keeps a sweep
    from spending the whole rate limit.
    """
    if ',' in field:
        raise Rejected('invalid_request',
                       f"'field' must be a single field name, not a comma-separated list: {field!r}")
    column, json_tail, kind = _resolve_field(resource_type, field)  # validates early

    # First local page also gives the total count
    first = local_search(resource_type=resource_type, params={}, response_size='small',
                         page=1, limit=batch_size, count=True)
    total = first.get('count', 0)
    if not total:
        logger.info(f"[VNDB] backfill {resource_type}.{field}: no active rows")
        return 0, 0

    req_fields = ['id', field]
    _path = field.split(".")
    _extract = extract if extract is not None else (lambda r: _nested_get(r, _path))
    search_fn  = _SEARCH_FUNCTIONS[resource_type]
    filter_set = getattr(VNDBFilters, resource_type.upper())
    num_batches = (total + batch_size - 1) // batch_size

    updated = 0
    local_page = first
    for batch_num in range(1, num_batches + 1):
        ids = [r['id'] for r in local_page.get('results', [])]
        if not ids:
            break

        if batch_num > 1:
            time.sleep(delay)

        try:
            response = search_fn(filters=_id_filter(filter_set, ids),
                                 fields=req_fields, results=batch_size, count=False)
        except Exception as e:
            logger.warning(f"[VNDB] backfill {resource_type}.{field}: batch "
                           f"{batch_num}/{num_batches} could not be fetched: {e}")
        else:
            for item in response.get('results', []):
                id_ = item['id']
                value = _extract(item)
                if value is None and not overwrite_null:
                    continue
                try:
                    write = _build_db_write(resource_type, id_, column, json_tail, kind, value)
                except TypeError as e:
                    logger.warning(f"[VNDB] backfill skipped {resource_type} {id_}: {e}")
                    continue
                if _TEST:
                    logger.info(f"[VNDB] backfill would set {resource_type} {id_} "
                                f"{field} = {value!r}")
                    updated += 1
                # source=None: a single-field maintenance write must not stamp
                # crawled_at — the rest of the row wasn't refreshed.
                elif db_update(resource_type, id_, write, source=None) is not None:
                    updated += 1

        logger.info(f"[VNDB] backfill {resource_type}.{field}: batch "
                    f"{batch_num}/{num_batches}, {updated} updated so far")

        if not local_page.get('more'):
            break
        local_page = local_search(
            resource_type=resource_type, params={}, response_size='small',
            page=batch_num + 1, limit=batch_size, count=False,
        )

    logger.info(f"[VNDB] backfill {resource_type}.{field}: done, "
                f"{updated}/{total} updated")
    return updated, total


@task(invalidates='all')
def backfill_column_task(resource_type: str, field: str) -> dict[str, Any]:
    """Run a backfill on a worker.

    A sweep walks a whole table, so it belongs on the queue rather than in the
    request that asked for it; the task id is how the caller follows it.
    """
    updated, total = backfill_column(resource_type, field)
    return format_results({'updated': updated, 'total': total})
