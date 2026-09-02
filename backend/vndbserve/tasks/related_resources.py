"""Tasks for the entities reachable from one entity.

`/vns/v17/characters` and its siblings. Which pairs exist is fixed per type: the
route for an unsupported one is never registered, so reaching here with one is a
defect rather than user input.
"""

from datetime import datetime
from typing import Any, Callable

from vndbserve.search import (
    search_resources_by_vnid_local,
    search_resources_by_charid_local,
    search_resources_by_release_id_local,
    search_vns_by_resource_id_local,
    search_characters_by_resource_id_local,
    search_releases_by_resource_id_local,
    search_resources_by_vnid_remote,
    search_resources_by_charid_remote,
    search_resources_by_release_id_remote,
    search_vns_by_resource_id_remote,
    search_characters_by_resource_id_remote,
    search_releases_by_resource_id_remote,
    convert_remote_to_local
)
from vndbserve.database import (
    exists, create, update, delete,
)
from vndbserve.logger import logger
from vndbserve.errors import Failed
from vndbserve.search.remote.search import PAGE_CAP
from .common import task
from .envelope import format_results, with_meta, NOT_FOUND

# Every supported pair, and the search each side reaches for. A table rather
# than a chain of conditions: overlapping conditions made the branch order
# decide which search ran, so a listed combination could name one search and
# reach another.
#
# There are two ways to answer the same question. The searches in
# _BY_PARENT_DOCUMENT read the ids out of the parent row's own relation column;
# the rest filter the result table by the other side. Both match by id exactly,
# and they differ only when the parent row is absent: the first reports
# `not_found`, the second an empty result.
_RELATED: dict[tuple[str, str], tuple[Callable | None, Callable | None]] = {
    ('vn',        'vn'):        (search_resources_by_vnid_local,        search_resources_by_vnid_remote),
    ('vn',        'tag'):       (search_resources_by_vnid_local,        search_resources_by_vnid_remote),
    ('vn',        'producer'):  (search_resources_by_vnid_local,        search_resources_by_vnid_remote),
    ('vn',        'staff'):     (search_resources_by_vnid_local,        search_resources_by_vnid_remote),
    ('vn',        'character'): (search_characters_by_resource_id_local, search_characters_by_resource_id_remote),
    ('vn',        'release'):   (search_releases_by_resource_id_local,  search_releases_by_resource_id_remote),
    ('character', 'vn'):        (search_vns_by_resource_id_local,       search_vns_by_resource_id_remote),
    ('character', 'trait'):     (search_resources_by_charid_local,      search_resources_by_charid_remote),
    # The one pair whose two sides disagree: local reads the release's own vns
    # column, remote asks the API for the VNs that carry this release.
    ('release',   'vn'):        (search_resources_by_release_id_local,  search_vns_by_resource_id_remote),
    ('release',   'producer'):  (search_resources_by_release_id_local,  search_resources_by_release_id_remote),
    ('producer',  'vn'):        (search_vns_by_resource_id_local,       search_vns_by_resource_id_remote),
    ('producer',  'release'):   (search_releases_by_resource_id_local,  search_releases_by_resource_id_remote),
    ('staff',     'vn'):        (search_vns_by_resource_id_local,       search_vns_by_resource_id_remote),
    ('tag',       'vn'):        (search_vns_by_resource_id_local,       search_vns_by_resource_id_remote),
    ('trait',     'character'): (search_characters_by_resource_id_local, search_characters_by_resource_id_remote),
    # Derived tags and traits exist only on the API side, so there is no local
    # search and no route; they are reachable by calling the task directly.
    ('dtag',      'vn'):        (None,                                  search_vns_by_resource_id_remote),
    ('dtrait',    'character'): (None,                                  search_characters_by_resource_id_remote),
}

# These take the parent's own id and the type wanted from it; the rest take the
# type and id of the other side.
_BY_PARENT_DOCUMENT = {
    search_resources_by_vnid_local,       search_resources_by_vnid_remote,
    search_resources_by_charid_local,     search_resources_by_charid_remote,
    search_resources_by_release_id_local, search_resources_by_release_id_remote,
}


def _search_related(resource_type: str, resource_id: str, related_resource_type: str,
                    source: str, **kwargs) -> dict[str, Any]:
    """Run the search this pair uses on `source`, in whichever shape it takes."""
    pair = _RELATED.get((resource_type, related_resource_type))
    search = pair[0 if source == 'local' else 1] if pair else None
    if search is None:
        # Both types are closed over at route registration, so a pair that is
        # not in the table cannot come from a request: the table and the routes
        # have drifted apart, and that is worth a traceback.
        raise Failed('internal_error',
                     f"No search registered for {resource_type} -> {related_resource_type}",
                     {'resource_type': resource_type,
                      'related_resource_type': related_resource_type})

    if search in _BY_PARENT_DOCUMENT:
        return search(resource_id, related_resource_type, **kwargs)
    return search(resource_type, resource_id, **kwargs)


def unpaginated_search(task: Callable, **kwargs) -> tuple[list[dict[str, Any]], str | None]:
    """Every page of `task`, as one list, with the time the pages were fetched.

    Takes a task rather than a search function: it reads `status` to tell a page
    that returned nothing from one that failed, and only the task layer puts
    that in the reply.

    The reply may have come from a cache, so the caller cannot date what it
    stores by its own clock. The oldest `_fetched_at` across the pages is
    returned for that, and is `None` when no page carried one.
    """
    results = []
    fetched_at = None
    page = 1
    more = True
    while more and page <= PAGE_CAP:
        response = task(**kwargs, page=page)
        if 'status' not in response:
            raise Failed('internal_error',
                         "unpaginated_search was given something other than a task.",
                         {'callable': getattr(task, '__name__', repr(task))})
        if response['status'] != 'SUCCESS':
            break
        results.extend(response.get('results', []))
        if stamp := response.get('_fetched_at'):
            fetched_at = min(fetched_at, stamp) if fetched_at else stamp
        more = response.get('more', False)
        page += 1
    if more:
        logger.warning(f"Stopped paging {getattr(task, '__name__', task)} "
                       f"at {PAGE_CAP} pages with more still reported")

    return results, fetched_at

@task(cache_for=600)
def get_related_resources_task(resource_type: str, resource_id: str, related_resource_type: str, response_size: str = 'small',
                                page: int = 1, limit: int = 100, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:

    results = _search_related(resource_type, resource_id, related_resource_type, 'local',
                              response_size=response_size, page=page, limit=limit,
                              sort=sort, reverse=reverse, count=count)

    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    return with_meta(format_results(results), source='local')

@task(cache_for=600)
def search_related_resources_task(resource_type: str, resource_id: str, related_resource_type: str, response_size: str = 'small',
                                   page: int = 1, limit: int = 100, sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:

    results = _search_related(resource_type, resource_id, related_resource_type, 'remote',
                              response_size=response_size, page=page, limit=limit,
                              sort=sort, reverse=reverse, count=count)

    if not results or not isinstance(results, dict) or not results.get('results'):
        return NOT_FOUND

    return with_meta(format_results(results), source='remote')

@task(invalidates='all')
def update_related_resources_task(resource_type: str, resource_id: str, related_resource_type: str) -> dict[str, Any]:

    related_data, fetched_at = unpaginated_search(
        search_related_resources_task,
        resource_type=resource_type, resource_id=resource_id,
        related_resource_type=related_resource_type, response_size='large'
    )
    # Dated from the payload: these pages may have come through the response
    # cache, and the clock at write time would call hour-old data freshly
    # crawled.
    crawled_at = datetime.fromisoformat(fetched_at) if fetched_at else None

    update_results = {}

    for item in related_data:
        id = item['id']
        try:
            update_data = convert_remote_to_local(related_resource_type, item)
            if exists(related_resource_type, id):
                data = update(related_resource_type, id, update_data, crawled_at=crawled_at)
            else:
                data = create(related_resource_type, id, update_data, crawled_at=crawled_at)
            if not data:
                update_results[id] = False
            else:
                update_results[id] = True

        except Exception:
            # One item failing is a per-item outcome, not a failed batch — but a
            # silent one would hide a defect behind a row of False.
            logger.exception(f"{related_resource_type} {id} failed")
            update_results[id] = False

    return format_results(update_results)

@task(invalidates='all')
def delete_related_resources_task(resource_type: str, resource_id: str, related_resource_type: str) -> dict[str, Any]:

    related_data, _ = unpaginated_search(
        get_related_resources_task,
        resource_type=resource_type, resource_id=resource_id,
        related_resource_type=related_resource_type, response_size='large'
    )

    delete_results = {}

    for item in related_data:
        id = item['id']
        try:
            data = delete(related_resource_type, id)
            if not data:
                delete_results[id] = False
            else:
                delete_results[id] = True

        except Exception:
            # One item failing is a per-item outcome, not a failed batch — but a
            # silent one would hide a defect behind a row of False.
            logger.exception(f"{related_resource_type} {id} failed")
            delete_results[id] = False

    return format_results(delete_results)