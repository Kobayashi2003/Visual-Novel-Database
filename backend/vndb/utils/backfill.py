"""Populate one column across a whole table, for after a schema change.

A migration adds a column but leaves it empty on existing rows. This walks the
table in batches and fills that one column — from the local row where the value
can be derived, or from a fresh Kana API fetch where it cannot. Only the named
column is written: the rest of the row, including any hand-edit, is left alone.

Driven from POST /admin/backfill, which runs it on a background thread.
"""

import time
from enum import Enum, auto
from typing import Any, Callable

import httpx
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB as PgJSONB, ARRAY as PgARRAY

from vndb.database import update as db_update, get as db_get
from vndb.database.models import MODEL_MAP
from vndb.search.local.search import search as local_search
from vndb.search.remote.search import (
    search_vn, search_character, search_release,
    search_producer, search_staff, search_tag, search_trait,
)
from vndb.search.remote.filters import VNDBFilters, build_filters

# ─── Constants ────────────────────────────────────────────────────────────────

_DEFAULT_BATCH_SIZE     = 100
_DEFAULT_DELAY          = 2.0            # seconds between batch requests
_DEFAULT_OVERWRITE_NULL = False          # whether to write a null value obtained from a successful fetch
_RETRY_DELAYS           = [30, 60, 120]  # seconds to wait on successive 429 responses
TEST                    = False          # when True, log DB writes instead of executing them

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
    """Navigate nested dicts following a key path. Returns None if any step is missing."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _set_nested(obj: dict, path: list[str], value: Any) -> dict:
    """Return a shallow-merged copy of obj with the key path set to value."""
    if len(path) == 1:
        return {**obj, path[0]: value}
    return {**obj, path[0]: _set_nested(obj.get(path[0]) or {}, path[1:], value)}


def _col_kind(resource_type: str, column_name: str) -> _ColKind:
    """Resolve the _ColKind for a column, raising ValueError if it doesn't exist."""
    model = MODEL_MAP.get(resource_type)
    if model is None:
        raise ValueError(f"Unknown resource type: {resource_type!r}")
    try:
        col_type = sa_inspect(model).columns[column_name].type
    except KeyError:
        raise ValueError(f"'{resource_type}' has no column '{column_name}'")
    if isinstance(col_type, PgARRAY):
        return _ColKind.SCALAR
    if isinstance(col_type, PgJSONB):
        return _ColKind.JSONB
    return _ColKind.SCALAR


def _resolve_field(resource_type: str, field: str) -> tuple[str, str, _ColKind]:
    """
    Parse and validate a field path against the model.
    Returns (column_name, json_tail, kind).
    Raises ValueError for unknown columns or dotted paths on non-JSONB columns.
    """
    column, _, json_tail = field.partition(".")
    kind = _col_kind(resource_type, column)
    if json_tail and kind is not _ColKind.JSONB:
        raise ValueError(
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
    """Build the data dict for db_update, with type validation."""
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


def _with_retry(fn: Callable, **kwargs) -> dict:
    last_exc = None
    for wait in [0, *_RETRY_DELAYS]:
        if wait:
            time.sleep(wait)
        try:
            return fn(**kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429:
                raise
            last_exc = e
    raise last_exc


# ─── Public API ───────────────────────────────────────────────────────────────

def backfill_column(
    resource_type: str,
    field: str,
    extract: Callable[[dict], Any] | None = None,
    overwrite_null: bool = _DEFAULT_OVERWRITE_NULL,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    delay: float = _DEFAULT_DELAY,
) -> tuple[int, int]:
    """
    Re-fetch a field from the VNDB API for every active record and overwrite the local value.

    Parameters
    ----------
    resource_type   One of 'vn', 'release', 'character', 'producer', 'staff', 'tag', 'trait'.
    field           A single VNDBFields path string, e.g. ``VNDBFields.Staff.GENDER``
                    (``"gender"``) or ``VNDBFields.VN.IMAGE.SEXUAL`` (``"image.sexual"``).
                    Must refer to exactly one field — comma-separated lists are not allowed.
                    A plain name overwrites the column directly (scalar, ARRAY, or full JSONB).
                    A dotted path (only valid on JSONB columns) triggers a partial-merge write.
    extract         ``(remote_record) -> value``. Defaults to navigating the field path in
                    the remote record.
    overwrite_null  If True, write a null value returned by a successful fetch.
                    Records that failed to fetch are never written. Default False.
    batch_size      Records per API request (max 100).
    delay           Seconds to sleep between batch requests.

    Returns (updated, total).
    """
    if ',' in field:
        raise ValueError(f"'field' must be a single field name, not a comma-separated list: {field!r}")
    column, json_tail, kind = _resolve_field(resource_type, field)  # validates early

    # First local page also gives the total count
    first = local_search(resource_type=resource_type, params={}, response_size='small',
                         page=1, limit=batch_size, count=True)
    total = first.get('count', 0)
    if not total:
        print(f"[backfill] '{resource_type}.{field}' — no active records.")
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
            response = _with_retry(search_fn, filters=_id_filter(filter_set, ids),
                                   fields=req_fields, results=batch_size, count=False)
        except Exception as e:
            print(f"  fetch failed (batch {batch_num}/{num_batches}): {e}")
        else:
            for item in response.get('results', []):
                id_ = item['id']
                value = _extract(item)
                if value is None and not overwrite_null:
                    continue
                try:
                    write = _build_db_write(resource_type, id_, column, json_tail, kind, value)
                except TypeError as e:
                    print(f"  type error {resource_type}/{id_} '{field}': {e}")
                    continue
                if TEST:
                    print(f"  [TEST] {resource_type}/{id_} {field} = {value!r}")
                    updated += 1
                # source=None: a single-field maintenance write must not stamp
                # crawled_at — the rest of the row wasn't refreshed.
                elif db_update(resource_type, id_, write, source=None) is not None:
                    updated += 1

        print(f"[backfill] {resource_type}.{field} — batch {batch_num}/{num_batches}, {updated} updated so far.")

        if not local_page.get('more'):
            break
        local_page = local_search(
            resource_type=resource_type, params={}, response_size='small',
            page=batch_num + 1, limit=batch_size, count=False,
        )

    print(f"[backfill] Done — {updated}/{total} updated.")
    return updated, total
