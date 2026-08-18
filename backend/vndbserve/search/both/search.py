"""The `both` search backend: freshness-aware composition of local and remote.

Strategy by query class (see policy.py for the freshness/coverage rationale):

1. Lookup by id (detail pages) — local-first with stale-while-revalidate:
   fresh local row → serve it; stale-but-tolerable → serve it AND kick off a
   background refresh; missing or hopelessly stale → block on remote (large
   results are synced into the local DB asynchronously, as the remote mode
   already does).

2. Parent-scoped small lists (releases / characters of one VN) — the parent
   VN document embeds the complete related list (it was captured by a full
   unpaginated crawl), so completeness is inherited from the parent: if the
   parent row is fresh enough, serve straight from its JSONB snapshot.

3. Free-form searches over fully-mirrored types (tag, trait) — local-first;
   the local tables are complete copies, so coverage is guaranteed.

4. Everything else — remote-first with local fallback (the local DB cannot
   prove completeness for arbitrary filters over partially-crawled types).
   Fallback results are marked `source: local-partial` so the frontend can
   tell the result set may be incomplete.

Responses carry `source` ('local' | 'remote' | 'local-stale' | 'local-partial')
and, when a background refresh was started, `refreshing: true`.

Tasks (celery) are imported lazily inside functions: the tasks layer imports
vndbserve.search at module load, so a module-level import here would be circular.
"""

import re
from typing import Any

from ..local.search import search as search_local
from ..remote.search import search_cache as search_remote_cache, paginated_results
from vndbserve.database.operations import get as db_get, updatable
from .policy import is_fresh, is_servable_stale

SINGLE_ID_PATTERN = re.compile(r'^[vrcpsgi]\d+$')

# Fully mirrored locally → free-form searches are complete and can go local-first.
FULL_COVERAGE_TYPES = ('tag', 'trait')

# (resource_type, sole query param) → (parent type, parent JSONB column) for
# small lists that a fresh parent document answers completely. Only columns
# whose embedded objects are a superset of the type's small response shape
# qualify (e.g. VN.characters embeds images, but Character.vns does not embed
# VN images — so the reverse direction stays remote-first).
EMBEDDED_LIST_SOURCES = {
    ('release', 'vn_id'): ('vn', 'releases'),
    ('character', 'vn_id'): ('vn', 'characters'),
}


def _trigger_refresh(resource_type: str, resource_id: str) -> bool:
    """Best-effort background refresh of one entity. The updatable() gate
    keeps concurrent stale hits from stacking duplicate fetches and refuses
    to touch manually edited rows."""
    from vndbserve.tasks.resources import update_resource_task
    try:
        if updatable(resource_type, resource_id):
            update_resource_task.delay(resource_type, resource_id)
            return True
    except Exception:
        pass
    return False


def _sync_remote_results(resource_type: str, results: list[dict[str, Any]]) -> None:
    """Asynchronously persist remote large results into the local DB."""
    from vndbserve.tasks.resources import synchronize_resources_task
    try:
        synchronize_resources_task.delay(resource_type, results)
    except Exception:
        pass


def _serve_local(resource_type: str, params: dict[str, Any], response_size: str,
                 page: int = 1, limit: int = 100, sort: str = 'id', reverse: bool = False,
                 count: bool = True, source: str = 'local', refreshing: bool = False) -> dict[str, Any]:
    results = search_local(resource_type, params, response_size, page, limit, sort, reverse, count)
    results['source'] = source
    if refreshing:
        results['refreshing'] = True
    return results


def _serve_remote(resource_type: str, params: dict[str, Any], response_size: str,
                  page: int, limit: int, sort: str, reverse: bool, count: bool) -> dict[str, Any]:
    results = search_remote_cache(resource_type, params, response_size, page, limit, sort, reverse, count)
    if response_size == 'large' and results.get('results'):
        _sync_remote_results(resource_type, results['results'])
    results['source'] = 'remote'
    return results


def search_by_id(resource_type: str, resource_id: str, response_size: str = 'small') -> dict[str, Any]:
    """Detail lookup with stale-while-revalidate."""
    row = db_get(resource_type, resource_id)

    if row is not None:
        if is_fresh(resource_type, row):
            return _serve_local(resource_type, {'id': resource_id}, response_size)
        if is_servable_stale(resource_type, row):
            refreshing = _trigger_refresh(resource_type, resource_id)
            return _serve_local(resource_type, {'id': resource_id}, response_size,
                                refreshing=refreshing)

    # Missing locally, or too stale to show: block on remote.
    try:
        return _serve_remote(resource_type, {'id': resource_id}, response_size,
                             page=1, limit=1, sort='id', reverse=False, count=True)
    except Exception:
        if row is not None:
            # Remote is down — outdated data beats no data.
            return _serve_local(resource_type, {'id': resource_id}, response_size,
                                source='local-stale')
        raise


def _search_embedded_list(parent_type: str, parent_id: str, doc_field: str,
                          page: int, limit: int, sort: str, reverse: bool, count: bool) -> dict[str, Any] | None:
    """Serve a related list from the parent document's JSONB snapshot, gated
    on the *parent's* freshness (the snapshot is exactly as fresh as the row
    it lives in). Returns None when the parent can't answer, so the caller
    falls through to remote-first."""
    parent = db_get(parent_type, parent_id)
    if parent is None:
        return None

    fresh = is_fresh(parent_type, parent)
    if not fresh and not is_servable_stale(parent_type, parent):
        return None

    items = getattr(parent, doc_field, None)
    if items is None:
        return None  # parent predates this field; let remote answer

    refreshing = False if fresh else _trigger_refresh(parent_type, parent_id)
    result = paginated_results({'results': list(items)}, sort, reverse, limit, page, count)
    result['source'] = 'local'
    if refreshing:
        result['refreshing'] = True
    return result


def search(resource_type: str, params: dict[str, Any], response_size: str = 'small',
           page: int = 1, limit: int = 100, sort: str = 'id', reverse: bool = False,
           count: bool = True) -> dict[str, Any]:
    """General entry point; dispatches to the per-query-class strategies."""

    # 1. Pure by-id lookup (detail page).
    if set(params.keys()) == {'id'} and SINGLE_ID_PATTERN.match(str(params['id'])):
        return search_by_id(resource_type, params['id'], response_size)

    # 2. Parent-document-served small lists.
    if response_size == 'small' and len(params) == 1:
        (param_key, param_value), = params.items()
        source = EMBEDDED_LIST_SOURCES.get((resource_type, param_key))
        if source is not None:
            parent_type, doc_field = source
            result = _search_embedded_list(parent_type, str(param_value), doc_field,
                                           page, limit, sort, reverse, count)
            if result is not None:
                return result

    # 3. Fully mirrored types: local-first.
    if resource_type in FULL_COVERAGE_TYPES:
        try:
            return _serve_local(resource_type, params, response_size,
                                page, limit, sort, reverse, count)
        except Exception:
            pass  # fall through to remote

    # 4. Default: remote-first, local fallback marked as potentially partial.
    try:
        return _serve_remote(resource_type, params, response_size,
                             page, limit, sort, reverse, count)
    except Exception:
        results = _serve_local(resource_type, params, response_size,
                               page, limit, sort, reverse, count,
                               source='local-partial')
        return results
