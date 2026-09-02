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
   Fallback results are marked `meta.complete: false` so the frontend can
   tell the result set may be incomplete.

Every reply carries `meta` saying how it was produced: which side answered,
whether the rows are fresh, whether the local side could answer the query
completely, and whether a dependency failure shaped the reply.

Searching never writes. When a reply should cause work — a stale row refreshed,
remote results persisted — that is reported under `_effects` for the task layer
to carry out; deferring work to a worker is the judgement of the layer that owns
the queue, not this one.
"""

import re
from typing import Any

from ..local.search import search as search_local
from ..remote.search import search_cache as search_remote_cache, paginated_results
from vndbserve.database import get as db_get, updatable, deleted_among
from vndbserve.errors import Rejected, Unavailable
from ..params import validate_params, local_only_params, sort_is_local_only
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


def _wants_refresh(resource_type: str, resource_id: str) -> bool:
    """Whether a stale row should be refreshed in the background.

    The `updatable` gate keeps concurrent stale hits from stacking duplicate
    fetches and refuses to touch manually edited rows. A database that cannot
    answer the question is answer enough: serve what we have and ask for
    nothing.
    """
    try:
        return updatable(resource_type, resource_id)
    except Unavailable:
        return False


def _ask_for(results: dict[str, Any], **effects) -> dict[str, Any]:
    """Record work for the task layer to carry out, and hand the reply back."""
    results.setdefault('_effects', {}).update(effects)
    return results


def _explain(results: dict[str, Any], source: str, fresh: bool = True,
             complete: bool = True, degraded: bool = False) -> dict[str, Any]:
    """Say how the answer was produced, on axes that vary independently.

    `fresh` is about the age of the rows served; `complete` is about whether
    the local side could answer this query at all. A row can be current in a
    result set that is missing others, and vice versa, so one field cannot
    carry both. `degraded` marks a reply shaped by a dependency failing rather
    than by policy — which is why it must not be cached.
    """
    results['meta'] = {'source': source, 'fresh': fresh,
                       'complete': complete, 'degraded': degraded}
    return results


def _serve_local(resource_type: str, params: dict[str, Any], response_size: str,
                 page: int = 1, limit: int = 100, sort: str = 'id', reverse: bool = False,
                 count: bool = True, fresh: bool = True, complete: bool = True,
                 degraded: bool = False) -> dict[str, Any]:
    results = search_local(resource_type, params, response_size, page, limit, sort, reverse, count)
    return _explain(results, 'local', fresh=fresh, complete=complete, degraded=degraded)


def _serve_remote(resource_type: str, params: dict[str, Any], response_size: str,
                  page: int, limit: int, sort: str, reverse: bool, count: bool) -> dict[str, Any]:
    results = search_remote_cache(resource_type, params, response_size, page, limit, sort, reverse, count)
    _explain(results, 'remote')
    if response_size == 'large' and results.get('results'):
        return _ask_for(results, persist=resource_type)
    return results


def search_by_id(resource_type: str, resource_id: str, response_size: str = 'small') -> dict[str, Any]:
    """Detail lookup with stale-while-revalidate."""
    row = db_get(resource_type, resource_id)

    if row is not None:
        if is_fresh(resource_type, row):
            return _serve_local(resource_type, {'id': resource_id}, response_size)
        if is_servable_stale(resource_type, row):
            results = _serve_local(resource_type, {'id': resource_id}, response_size, fresh=False)
            if _wants_refresh(resource_type, resource_id):
                return _ask_for(results, refresh=(resource_type, resource_id))
            return results

    # Missing locally, or too stale to show: block on remote.
    try:
        return _serve_remote(resource_type, {'id': resource_id}, response_size,
                             page=1, limit=1, sort='id', reverse=False, count=True)
    except Unavailable:
        if row is not None:
            # Remote is down — outdated data beats no data.
            return _serve_local(resource_type, {'id': resource_id}, response_size,
                                fresh=False, degraded=True)
        raise


def _search_embedded_list(resource_type: str, parent_type: str, parent_id: str, doc_field: str,
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

    # The document records what the API reported when the parent was crawled,
    # which is before any delete of ours. Serving it unfiltered would answer the
    # same question two ways: gone from the child table, still listed here.
    gone = deleted_among(resource_type, [item['id'] for item in items if 'id' in item])
    items = [item for item in items if item.get('id') not in gone]

    result = _explain(paginated_results({'results': list(items)}, sort, reverse, limit, page, count),
                      'local', fresh=fresh)
    if not fresh and _wants_refresh(parent_type, parent_id):
        return _ask_for(result, refresh=(parent_type, parent_id))
    return result


def search(resource_type: str, params: dict[str, Any], response_size: str = 'small',
           page: int = 1, limit: int = 100, sort: str = 'id', reverse: bool = False,
           count: bool = True) -> dict[str, Any]:
    """General entry point; dispatches to the per-query-class strategies."""

    # Up front, so that an unknown parameter is still refused when the remote
    # backend is unreachable and cannot be the one to refuse it.
    validate_params(resource_type, params)

    # A filter or an ordering only the mirror implements decides which backend
    # answers: the remote one would refuse it, so the query goes local
    # regardless of how fresh or complete the mirror is. It is not degraded —
    # nothing failed — but it is not complete either, since the mirror holds a
    # subset.
    if set(params) & local_only_params(resource_type) or sort_is_local_only(resource_type, sort):
        return _serve_local(resource_type, params, response_size,
                            page, limit, sort, reverse, count, complete=False)

    # 1. Pure by-id lookup (detail page).
    if set(params.keys()) == {'id'} and SINGLE_ID_PATTERN.match(str(params['id'])):
        return search_by_id(resource_type, params['id'], response_size)

    # 2. Parent-document-served small lists.
    if response_size == 'small' and len(params) == 1:
        (param_key, param_value), = params.items()
        source = EMBEDDED_LIST_SOURCES.get((resource_type, param_key))
        if source is not None:
            parent_type, doc_field = source
            result = _search_embedded_list(resource_type, parent_type, str(param_value), doc_field,
                                           page, limit, sort, reverse, count)
            if result is not None:
                return result

    # 3. Fully mirrored types: local-first.
    if resource_type in FULL_COVERAGE_TYPES:
        try:
            return _serve_local(resource_type, params, response_size,
                                page, limit, sort, reverse, count)
        except Unavailable:
            pass  # fall through to remote

    # 4. Default: remote-first, local fallback marked as potentially partial.
    try:
        return _serve_remote(resource_type, params, response_size,
                             page, limit, sort, reverse, count)
    except Unavailable as outage:
        try:
            return _serve_local(resource_type, params, response_size,
                                page, limit, sort, reverse, count,
                                complete=False, degraded=True)
        except Rejected:
            # The local backend cannot express every filter the API can. The
            # request itself was valid, so what the caller is told about is the
            # outage, not a fallback that has no way to answer it.
            raise outage from None
