"""One task per resource operation, sync or queued.

The route layer calls these directly when `?sync=true`, and hands them to Celery
otherwise; either way the return value is the same envelope.

The read tasks differ only in where they look: `get_*` local, `search_*` remote,
`query_*` freshness-aware (see search/both). The write tasks crawl upstream and
persist, and are what PUT and PATCH reach.
"""

from typing import Any

from vndb.search import (
    search_remote, search_local, search_both,
    convert_remote_to_local
)
from vndb.database import (
    get_all, create, update, updatable,
    delete, delete_all, exists
)
from .common import (
    task_with_memoize, task_with_cache_clear, task_basic,
    format_results, NOT_FOUND
)


@task_with_memoize(timeout=600)
def query_resources_task(resource_type: str, params: dict[str, Any], response_size: str = 'small',
                         page: int = 1, limit: int = 20, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    """Freshness-aware `both` mode: local when fresh, remote when not (see
    vndb/search/both). The result's `source`/`refreshing` fields survive
    format_results, so the frontend can tell where the data came from."""
    results = search_both(resource_type, params, response_size, page, limit, sort, reverse, count)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    return format_results(results)

@task_with_memoize(timeout=600)
def get_resource_task(resource_type: str, resource_id: str, response_size: str = 'small') -> dict[str, Any]:
    results = search_local(resource_type, {'id': resource_id}, response_size)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    results = format_results(results)
    results['source'] = 'local'
    return results

@task_with_memoize(timeout=600)
def get_resources_task(resource_type: str, args: dict[str, Any], response_size: str = 'small',
                       page: int = 1, limit: int = 20, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    results = search_local(resource_type, args, response_size, page, limit, sort, reverse, count)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    results = format_results(results)
    results['source'] = 'local'
    return results

@task_with_memoize(timeout=600)
def search_resource_task(resource_type: str, resource_id: str, response_size: str = 'small') -> dict[str, Any]:
    results = search_remote(resource_type, {'id': resource_id}, response_size)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    if response_size == 'large':
        synchronize_resources_task.delay(resource_type, results['results'])

    results = format_results(results)
    results['source'] = 'remote'
    return results

@task_with_memoize(timeout=600)
def search_resources_task(resource_type: str, params: dict[str, Any], response_size: str = 'small',
                           page: int = 1, limit: int = 20, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    results = search_remote(resource_type, params, response_size, page, limit, sort, reverse, count)
    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    if response_size == 'large':
        synchronize_resources_task.delay(resource_type, results['results'])

    results = format_results(results)
    results['source'] = 'remote'
    return results

def _update_resource(resource_type: str, resource_id: str) -> dict[str, Any]:
    remote_result = search_remote(resource_type, {'id':resource_id}, 'large')
    if not remote_result or not remote_result.get('results'):
        return NOT_FOUND

    update_data = convert_remote_to_local(resource_type, remote_result['results'][0])

    if exists(resource_type, resource_id):
        data = update(resource_type, resource_id, update_data, source='refresh')
    else:
        data = create(resource_type, resource_id, update_data)

    return format_results(data)

@task_with_cache_clear
def update_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    return _update_resource(resource_type, resource_id)

@task_with_cache_clear
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

@task_with_cache_clear
def delete_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    result = delete(resource_type, resource_id)
    return format_results(result)

@task_with_cache_clear
def delete_resources_task(resource_type: str) -> dict[str, Any]:
    deleted_count = delete_all(resource_type)
    return format_results(deleted_count)

def _edit_resource(resource_type: str, resource_id: str, update_data: dict[str, Any]) -> dict[str, Any]:
    result = update(resource_type, resource_id, update_data, source='edit')
    return format_results(result)

@task_with_cache_clear
def edit_resource_task(resource_type: str, resource_id: str, update_data: dict[str, Any]) -> dict[str, Any]:
    return _edit_resource(resource_type, resource_id, update_data)

@task_with_cache_clear
def edit_resources_task(resource_type: str, update_datas: list[dict[str, Any]]) -> dict[str, Any]:
    update_results = {}

    for update_data in update_datas:
        resource_id = update_data.pop('id', None)
        if not resource_id:
            continue
        result = _edit_resource(resource_type, resource_id, update_data)
        update_results[resource_id] = result['status'] == 'SUCCESS'

    return format_results(update_results)


@task_basic
def synchronize_resources_task(resource_type: str, results: list[dict[str, Any]]) -> dict[str, dict[str, bool]]:
    created = {}
    updated = {}
    for result in results:
        id = result['id']
        data = convert_remote_to_local(resource_type, result)
        if not exists(resource_type, id):
            created[id] = (create(resource_type, id, data) is not None)
        elif updatable(resource_type, id):
            updated[id] = (update(resource_type, id, data) is not None)
    return {'created': created, 'updated': updated}
