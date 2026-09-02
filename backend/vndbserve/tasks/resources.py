"""One task per resource operation, sync or queued.

The route layer calls these directly when `?sync=true`, and hands them to Celery
otherwise; either way the return value is the same envelope.

The read tasks differ only in where they look: `get_*` local, `search_*` remote,
`query_*` freshness-aware (see search/both). The write tasks crawl upstream and
persist, and are what PUT and PATCH reach.
"""

from typing import Any
from datetime import datetime

from vndbserve.search import (
    search_remote, search_local, search_both,
    convert_remote_to_local
)
# Uncached: a refresh exists to replace stale data, so reading it through the
# hour-long response cache would rewrite the row with what it already held.
from vndbserve.search.remote.search import search as search_remote_live
from vndbserve.errors import Rejected
from vndbserve.logger import logger
from vndbserve.database import (
    get_all, create, update, updatable,
    delete, delete_all, exists
)
from .common import task
from .envelope import format_results, with_meta, already_so, NOT_FOUND


def _perform_search_effects(results: dict[str, Any]) -> dict[str, Any]:
    """Carry out the work a `both` search asked for.

    Search reports what should happen; deciding to defer it to a worker is this
    layer's own judgement. The request is stripped here, so it never reaches a
    client. Best-effort throughout: a read must not fail because the work it
    suggested could not be queued — but a broker that never accepts one leaves
    the mirror silently frozen, so it is logged.
    """
    if not isinstance(results, dict):
        return results
    effects = results.pop('_effects', None)
    if not effects:
        return results

    if target := effects.get('refresh'):
        resource_type, resource_id = target
        try:
            update_resource_task.delay(resource_type, resource_id)
            results['refreshing'] = True
        except Exception:
            logger.exception(f"Could not queue a refresh of {resource_type} {resource_id}")

    if resource_type := effects.get('persist'):
        try:
            synchronize_resources_task.delay(resource_type, results.get('results') or [],
                                             results.get('_fetched_at'))
        except Exception:
            logger.exception(f"Could not queue a {resource_type} sync")

    return results


@task(cache_for=600)
def query_resources_task(resource_type: str, params: dict[str, Any], response_size: str = 'small',
                         page: int = 1, limit: int = 20, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    """Freshness-aware `both` mode: local when fresh, remote when not (see
    vndbserve/search/both). The search reports any follow-up work it wants; this
    is where that work is queued and where `meta` survives format_results, so a
    client can tell how the answer was produced."""
    results = _perform_search_effects(
        search_both(resource_type, params, response_size, page, limit, sort, reverse, count))
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    return format_results(results)

@task(cache_for=600)
def get_resource_task(resource_type: str, resource_id: str, response_size: str = 'small') -> dict[str, Any]:
    results = search_local(resource_type, {'id': resource_id}, response_size)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    return with_meta(format_results(results), source='local')

@task(cache_for=600)
def get_resources_task(resource_type: str, params: dict[str, Any], response_size: str = 'small',
                       page: int = 1, limit: int = 20, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    results = search_local(resource_type, params, response_size, page, limit, sort, reverse, count)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    return with_meta(format_results(results), source='local')

@task(cache_for=600)
def search_resource_task(resource_type: str, resource_id: str, response_size: str = 'small') -> dict[str, Any]:
    results = search_remote(resource_type, {'id': resource_id}, response_size)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    if response_size == 'large':
        # Dated from the payload: `search_remote` is memoized, so these results
        # may be an hour old and must not be stored as freshly crawled.
        synchronize_resources_task.delay(resource_type, results['results'],
                                         results.get('_fetched_at'))

    return with_meta(format_results(results), source='remote')

@task(cache_for=600)
def search_resources_task(resource_type: str, params: dict[str, Any], response_size: str = 'small',
                           page: int = 1, limit: int = 20, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    results = search_remote(resource_type, params, response_size, page, limit, sort, reverse, count)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    if response_size == 'large':
        # Dated from the payload: `search_remote` is memoized, so these results
        # may be an hour old and must not be stored as freshly crawled.
        synchronize_resources_task.delay(resource_type, results['results'],
                                         results.get('_fetched_at'))

    return with_meta(format_results(results), source='remote')

def _update_resource(resource_type: str, resource_id: str) -> dict[str, Any]:
    remote_result = search_remote_live(resource_type, {'id': resource_id}, 'large')
    if not remote_result or not remote_result.get('results'):
        return NOT_FOUND

    update_data = convert_remote_to_local(resource_type, remote_result['results'][0])

    if exists(resource_type, resource_id):
        data = update(resource_type, resource_id, update_data, source='refresh')
    else:
        data = create(resource_type, resource_id, update_data)

    return format_results(data)

@task(retry=True, invalidates='entity')
def update_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    return _update_resource(resource_type, resource_id)

@task(invalidates='all')
def update_resources_task(resource_type: str) -> dict[str, Any]:
    update_results = {}

    resources = get_all(resource_type)
    for resource in resources:
        # Bulk refresh is indiscriminate, so it must not clobber rows the user
        # edited by hand; those are only refreshed one-by-one (explicitly).
        if resource.edited_at is not None:
            update_results[resource.id] = 'SKIPPED_EDITED'
            continue
        result = _update_resource(resource_type, resource.id)
        update_results[resource.id] = result['status'] == 'SUCCESS'

    return format_results(update_results)

@task(invalidates='entity')
def delete_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    result = delete(resource_type, resource_id)
    return format_results(result) if result is not None else already_so(resource_id)

@task(invalidates='all')
def delete_resources_task(resource_type: str) -> dict[str, Any]:
    deleted_count = delete_all(resource_type)
    return format_results(deleted_count)

def _edit_resource(resource_type: str, resource_id: str, update_data: dict[str, Any]) -> dict[str, Any]:
    result = update(resource_type, resource_id, update_data, source='edit')
    return format_results(result)

@task(invalidates='entity')
def edit_resource_task(resource_type: str, resource_id: str, update_data: dict[str, Any]) -> dict[str, Any]:
    return _edit_resource(resource_type, resource_id, update_data)

@task(invalidates='all')
def edit_resources_task(resource_type: str, update_datas: list[dict[str, Any]]) -> dict[str, Any]:
    """Edit many rows, each entry naming its own by `id`.

    The batch is checked before any of it is applied: an entry with no `id`
    names no row, and there is no key to report it under afterwards. Dropping it
    silently would answer with a result for every entry that had one and no sign
    that the rest were ignored.
    """
    nameless = [index for index, data in enumerate(update_datas) if not data.get('id')]
    if nameless:
        raise Rejected('invalid_request',
                       f"Every entry must carry an 'id'; entries at "
                       f"{', '.join(str(index) for index in nameless)} do not.")

    update_results = {}
    for update_data in update_datas:
        data = {key: value for key, value in update_data.items() if key != 'id'}
        result = _edit_resource(resource_type, update_data['id'], data)
        update_results[update_data['id']] = result['status'] == 'SUCCESS'

    return format_results(update_results)


@task(retry=True)
def synchronize_resources_task(resource_type: str, results: list[dict[str, Any]],
                               fetched_at: str | None = None) -> dict[str, Any]:
    """Persist remote results into the mirror.

    `fetched_at` dates the payload. It matters because these results may have
    come through the response cache: stamping them with the clock at write time
    would present hour-old data as freshly crawled.

    Nothing is invalidated afterwards. This runs behind every large remote
    read, so dropping the task cache here would empty it under ordinary traffic.
    What that costs is bounded: a cached local reply made before this write does
    not show the rows it added, until it expires ten minutes later.
    """
    crawled_at = datetime.fromisoformat(fetched_at) if fetched_at else None
    created = {}
    updated = {}
    skipped = []
    for result in results:
        id = result['id']
        data = convert_remote_to_local(resource_type, result)
        if not exists(resource_type, id):
            created[id] = (create(resource_type, id, data, crawled_at=crawled_at) is not None)
        elif updatable(resource_type, id):
            updated[id] = (update(resource_type, id, data, crawled_at=crawled_at) is not None)
        else:
            # Held back by `updatable`: a hand-edited row, or one crawled inside
            # AUTO_CRAWL_INTERVAL. Reported rather than dropped, so a caller
            # counting what it sent can see why the mirror did not move.
            skipped.append(id)
    return format_results({'created': created, 'updated': updated, 'skipped': skipped})
