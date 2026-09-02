"""Tasks over soft-deleted rows: list, recover, or delete for good.

`cleanup` is the only path in the service that removes a row permanently.
"""

from typing import Any

from vndbserve.database import (
    exists,
    get_inactive, get_inactive_all,
    cleanup, cleanup_all,
    recover, recover_all,
    count_inactive_all
)
from .common import task
from .envelope import format_results, already_so, NOT_FOUND

@task(cache_for=600)
def get_inactive_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    result = get_inactive(resource_type, resource_id)
    return format_results(result)

@task(cache_for=600)
def get_inactive_resources_task(resource_type: str, page: int | None = None, limit: int | None = None, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:
    results = get_inactive_all(resource_type, page, limit, sort, reverse)
    if not results:
        return NOT_FOUND
    total = count_inactive_all(resource_type)
    more = (page * limit) < total if page and limit else False

    results = format_results(results)
    if count:
        results['count'] = total
    results['more'] = more
    return results

@task(invalidates='all')
def recover_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    result = recover(resource_type, resource_id)
    if result is not None:
        return format_results(result)
    # Nothing in the trash under that id. Already active is the state that was
    # asked for; never having existed is no answer at all.
    return already_so(resource_id) if exists(resource_type, resource_id) else NOT_FOUND

@task(invalidates='all')
def recover_resources_task(resource_type: str) -> dict[str, Any]:
    results = recover_all(resource_type)
    return format_results(results)

@task(invalidates='all')
def cleanup_resource_task(resource_type: str, resource_id: str) -> dict[str, Any]:
    result = cleanup(resource_type, resource_id)
    return format_results(result) if result is not None else already_so(resource_id)

@task(invalidates='all')
def cleanup_resources_task(resource_type: str) -> dict[str, Any]:
    results = cleanup_all(resource_type)
    return format_results(results)