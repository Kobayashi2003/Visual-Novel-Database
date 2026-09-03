"""Search against the VNDB Kana API.

Builds the upstream request from the same parameter names the local search
takes, so a caller can switch source without rewriting its query, and adapts
the reply to the shared {results, count, more} shape.

Also owns the rate-limit handling: the API throttles by request count, so
failures are retried with a backoff rather than surfaced immediately.
"""

import re
import time
import httpx
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable
from enum import Enum

from .filters import get_remote_filters
from .fields import get_remote_fields, validate_sort
from ..common import log_search
from ..params import validate_params, local_only_params
from vndbserve.errors import Failed, Rejected, Unavailable
from vndbserve.logger import logger


VNDB_API_URL = "https://api.vndb.org/kana"

# Exponential-backoff settings for VNDB Kana API rate limiting (HTTP 429).
RATE_LIMIT_MAX_RETRIES = 5
RATE_LIMIT_BASE_DELAY = 1.0   # seconds; doubles each retry
RATE_LIMIT_MAX_DELAY = 60.0   # seconds; backoff ceiling

# A connection that never opened is worth one more attempt: nothing was sent,
# so sending it again cannot repeat any work. httpx offers this as
# `HTTPTransport(retries=...)`, which the client below cannot use — see there.
CONNECT_RETRIES = 1

# Two budgets, because they measure different things. Opening a socket either
# happens quickly or is not going to happen; reading a full page of results is
# allowed to take a while. One number for both would make an unreachable API
# cost a caller the read budget before the fallback even starts.
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0

# How far a walk over every page will go. Termination otherwise rests on the
# source reporting `more` correctly, and a source that always says there is
# more is a worker looping until it runs out of memory.
PAGE_CAP = 500


# ─── The Kana client ──────────────────────────────────────────────────────────

class VNDBEndpoint(Enum):
    VN = "vn"
    CHARACTER = "character"
    PRODUCER = "producer"
    STAFF = "staff"
    TAG = "tag"
    TRAIT = "trait"
    RELEASE = "release"

def raise_for_kana_status(response: httpx.Response) -> None:
    """Turn a non-2xx Kana reply into one of the three kinds.

    A 5xx or a 429 is the API's own trouble, so it passes as Unavailable.

    Any other 4xx says the request was not acceptable, and everything in it
    that varies came from the caller's parameters — `?role=voice` is refused
    because Kana's enum spells that role `seiyuu`, which is the caller's to fix
    and not ours. Kana names the field it objected to, so its own message
    travels with the rejection. It is logged as well: a filter this service
    built wrongly lands here too, and would otherwise leave no trace.
    """
    if response.is_success:
        return

    status = response.status_code
    context = {'url': str(response.request.url), 'status': status,
               'body': response.text[:500]}

    if status >= 500:
        raise Unavailable('upstream_unavailable',
                          "The VNDB API is not answering.", context)
    if status == 429:
        raise Unavailable('upstream_rate_limited',
                          "The VNDB API is rate limiting this service.", context)
    detail = response.text.strip()[:200] or "The VNDB API refused the request."
    logger.warning(f"Kana refused a request: {detail} ({response.request.url})")
    raise Rejected('invalid_request', detail, context)


class VNDBAPIWrapper:
    """The HTTP client for Kana, and the one place a request to it is made.

    One client for the process: it keeps connections alive, so a crawl does not
    open a socket per request. Rate limiting is waited out here rather than
    reported upward — see `_request` for why that division exists.
    """

    def __init__(self, api_token: str | None = None):
        # No `transport=` here, deliberately. Passing one is also what turns off
        # httpx's reading of the proxy environment
        # (`allow_env_proxies = trust_env and transport is None`), and on a host
        # that reaches the API through a proxy the client would then aim every
        # request straight at a network it cannot route — an unreachable API
        # with a working one configured. The retry it would have bought is made
        # in `_send` instead.
        self.client = httpx.Client(
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
        )
        self.client.headers.update({"Content-Type": "application/json"})
        if api_token:
            self.client.headers.update({"Authorization": f"Token {api_token}"})

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        """One request, retried only when the connection never opened.

        Nothing has been sent at that point, so a second attempt cannot repeat
        any work — which is why no other failure is retried here: a read that
        timed out may well have been carried out upstream already.
        """
        for attempt in range(CONNECT_RETRIES + 1):
            try:
                return self.client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if attempt == CONNECT_RETRIES:
                    raise

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send a request to the Kana API, backing off exponentially when it
        replies 429 (rate limited). The API's Retry-After header is honoured
        when present; otherwise the delay doubles each attempt. The final
        response is returned for the caller to classify with
        `raise_for_kana_status`. A network failure never yields a response at
        all, so it is translated here."""
        delay = RATE_LIMIT_BASE_DELAY
        for attempt in range(RATE_LIMIT_MAX_RETRIES):
            try:
                response = self._send(method, url, **kwargs)
            except httpx.HTTPError as exc:
                raise Unavailable('upstream_unreachable',
                                  "The VNDB API could not be reached.",
                                  {'url': url, 'cause': repr(exc)}) from exc
            if response.status_code != 429 or attempt == RATE_LIMIT_MAX_RETRIES - 1:
                return response
            retry_after = response.headers.get("Retry-After", "")
            wait = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else delay
            time.sleep(wait)
            delay = min(delay * 2, RATE_LIMIT_MAX_DELAY)
        return response

    def query(self, endpoint: VNDBEndpoint, filters: list, fields: list[str],
              sort: str = "id", reverse: bool = False, results: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
        url = f"{VNDB_API_URL}/{endpoint.value}"

        payload = {
            "filters": filters,
            "fields": ",".join(fields),
            "sort": sort,
            "reverse": reverse,
            "results": results,
            "page": page,
            "count": count
        }

        response = self._request("POST", url, json=payload)

        if response.status_code != 200:
            log_search(
                source="remote",
                message=f"Error querying {endpoint.value}",
                details={
                    "resource_type": endpoint.value,
                    "url": url,
                    "payload": payload,
                    "status_code": response.status_code,
                    "response": response.text,
                },
                level="error",
            )
        else:
            log_search(
                source="remote",
                message=f"Successfully queried {endpoint.value}",
                details={
                    "resource_type": endpoint.value,
                    "url": url,
                    "payload": payload,
                },
            )

        raise_for_kana_status(response)
        return response.json()

    def get_vn(self, filters: dict[str, Any], fields: list[str], **kwargs) -> dict[str, Any]:
        return self.query(VNDBEndpoint.VN, filters, fields, **kwargs)

    def get_character(self, filters: dict[str, Any], fields: list[str], **kwargs) ->   dict[str, Any]:
        return self.query(VNDBEndpoint.CHARACTER, filters, fields, **kwargs)

    def get_producer(self, filters: dict[str, Any], fields: list[str], **kwargs) -> dict[str, Any]:
        return self.query(VNDBEndpoint.PRODUCER, filters, fields, **kwargs)

    def get_staff(self, filters: dict[str, Any], fields: list[str], **kwargs) -> dict[str, Any]:
        return self.query(VNDBEndpoint.STAFF, filters, fields, **kwargs)

    def get_tag(self, filters: dict[str, Any], fields: list[str], **kwargs) -> dict[str, Any]:
        return self.query(VNDBEndpoint.TAG, filters, fields, **kwargs)

    def get_trait(self, filters: dict[str, Any], fields: list[str], **kwargs) -> dict[str, Any]:
        return self.query(VNDBEndpoint.TRAIT, filters, fields, **kwargs)

    def get_release(self, filters: dict[str, Any], fields: list[str], **kwargs) -> dict[str, Any]:
        return self.query(VNDBEndpoint.RELEASE, filters, fields, **kwargs)

    def update_user_list(self, vn_id: str, data: dict[str, Any]) -> None:
        url = f"{VNDB_API_URL}/ulist/{vn_id}"
        response = self._request("PATCH", url, json=data)
        raise_for_kana_status(response)

    def update_release_list(self, release_id: str, status: int) -> None:
        url = f"{VNDB_API_URL}/rlist/{release_id}"
        response = self._request("PATCH", url, json={"status": status})
        raise_for_kana_status(response)

    def remove_from_user_list(self, vn_id: str) -> None:
        url = f"{VNDB_API_URL}/ulist/{vn_id}"
        response = self._request("DELETE", url)
        raise_for_kana_status(response)

    def remove_from_release_list(self, release_id: str) -> None:
        url = f"{VNDB_API_URL}/rlist/{release_id}"
        response = self._request("DELETE", url)
        raise_for_kana_status(response)

    def get_auth_info(self) -> dict[str, Any]:
        url = f"{VNDB_API_URL}/authinfo"
        response = self._request("GET", url)
        raise_for_kana_status(response)
        return response.json()

api = VNDBAPIWrapper()


# ─── Wrapping a reply ─────────────────────────────────────────────────────────

def memoize(timeout=60*60*24):
    try:
        from vndbserve import cache
        return cache.memoize(timeout=timeout)
    except ImportError:
        return lambda f: f

def dated(search: Callable) -> Callable:
    """Stamp a reply with when it was fetched.

    Inside the memoized call, so a cached payload keeps the time it was really
    fetched rather than the time it was served. Anything that stores the reply
    must date the row from here, not from the clock at the moment of writing.
    """
    @wraps(search)
    def run(*args, **kwargs):
        results = search(*args, **kwargs)
        if isinstance(results, dict):
            results.setdefault('_fetched_at', datetime.now(timezone.utc).isoformat())
        return results
    return run


def unpaginated_search(search_function: Callable, **kwargs) -> dict[str, Any]:
    """Every page of `search_function`, as one reply.

    `PAGE_CAP` bounds the walk. Termination otherwise rests on the source
    reporting `more` correctly, and a source that always says there is more is
    a worker looping until it runs out of memory.
    """
    results = []
    page = 1
    more = True
    while more and page <= PAGE_CAP:
        response = search_function(**kwargs, page=page)
        results.extend(response.get('results', []))
        more = response.get('more', False)
        page += 1
    if more:
        logger.warning(f"Stopped paging {getattr(search_function, '__name__', search_function)} "
                       f"at {PAGE_CAP} pages with more still reported")

    return {'results': results, 'total': len(results), 'count': len(results)}

def _as_page(value: Any, name: str) -> int:
    """A positive whole number, or a rejection naming what was wrong with it."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        raise Rejected('invalid_request',
                       f"'{name}' must be a whole number, not {value!r}")


def paginated_results(results: dict[str, Any], sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, include_count: bool = True) -> dict[str, Any]:
    """One page of an unpaginated reply, sorted.

    `page` and `limit` are clamped to the same range the local search uses, so
    that the two backends answer the same request the same way. Unclamped they
    would slice with a negative bound — `items[0:-5]` is a different set, not an
    empty one — and report `more` on a page that advanced nothing, which is a
    loop for anything walking the pages.
    """
    page, limit = _as_page(page, 'page'), _as_page(limit, 'limit')
    limit = min(limit, 100)

    if not results or 'results' not in results:
        return {'results': [], 'count': 0} if include_count else {'results': []}

    def sort_key(item):
        value = item.get(sort)
        if value is None:
            # Items without the sort field group together (last in ascending
            # order); the second element is never compared across groups.
            return (True, 0)
        if sort == 'id' and isinstance(value, str):
            # VNDB ids are "<prefix><number>"; sort numerically so that
            # e.g. v9 < v10 instead of the lexicographic "v10" < "v9".
            match = re.match(r'^[a-z]+(\d+)$', value)
            if match:
                return (False, int(match.group(1)))
        return (False, value)

    # sorted() (not list.sort) because `results` may be a shared object from
    # the memoize cache; mutating it in place would leak the reordering into
    # other requests.
    items = sorted(results['results'], key=sort_key, reverse=reverse)
    total = len(items)
    start_index = (page - 1) * limit
    end_index = start_index + limit
    items = items[start_index:end_index]

    result = {'results': items, 'more': end_index < total}
    if include_count:
        result['count'] = total
    if '_fetched_at' in results:
        result['_fetched_at'] = results['_fetched_at']

    return result


# ─── One endpoint per resource type ───────────────────────────────────────────

def search_vn(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_vn(filters, fields, page=page, **kwargs)

def search_character(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_character(filters, fields, page=page, **kwargs)

def search_tag(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_tag(filters, fields, page=page, **kwargs)

def search_producer(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_producer(filters, fields, page=page, **kwargs)

def search_staff(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_staff(filters, fields, page=page, **kwargs)

def search_trait(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_trait(filters, fields, page=page, **kwargs)

def search_release(filters: dict[str, Any], fields: list[str], page: int = 1, **kwargs) -> dict[str, Any]:
    return api.get_release(filters, fields, page=page, **kwargs)

# ─── Fields Kana has no field for ─────────────────────────────────────────────

def vn_additional_field_characters(vnid: str):
    characters = unpaginated_search(
        search_function=search_characters_by_resource_id_cache,
        resource_type='vn', resource_id=vnid, response_size='small', limit=100
    )['results']
    characters = [{key: char[key] for key in ['id', 'name', 'original', 'sex', 'vns', 'image']} for char in characters]
    return characters

def vn_additional_field_releases(vnid: str):
    releases = unpaginated_search(
        search_function=search_releases_by_resource_id_cache,
        resource_type='vn', resource_id=vnid, response_size='small', limit=100
    )['results']
    return releases

def vn_additional_field_publishers(releases: list[dict[str, Any]]):
    """The VN's publishers, derived from the releases it already carries.

    Kana has no `publishers` field on a VN: a publisher is a producer marked
    `publisher` on one of its releases, and which languages it published in is
    the languages of that release. Both are read off the releases rather than
    fetched again.
    """
    release_languages = [
        [language['lang'] for language in release['languages']]
        for release in releases
    ]

    publishers = [
        {
            'id': producer['id'],
            'name': producer['name'],
            'original': producer['original'],
            'languages': release_languages[index]
        }
        for index, release in enumerate(releases)
        for producer in release.get('producers', [])
        if producer.get('publisher') is True
    ]

    publishers_map = {}
    for publisher in publishers:
        if publisher['id'] not in publishers_map:
            publishers_map[publisher['id']] = publisher
        else:
            publishers_map[publisher['id']]['languages'].extend(publisher['languages'])

    publishers = list(publishers_map.values())
    for publisher in publishers:
        if 'languages' not in publisher:
            publisher['languages'] = []
        publisher['languages'] = list(set(publisher['languages']))

    return publishers

def character_additional_field_seiyuu(character: dict[str, Any]):
    """The character's voice actors, read out of the VNs they appear in.

    Kana records a voice credit on the VN, not on the character, so this asks
    the character's VNs for their `va` lists and keeps the entries pointing at
    this character. The same actor credited in several VNs collapses to one
    entry, keyed by who they are and the note that distinguishes a re-recording.
    """
    charid = character['id']

    vns = get_vn_cache(
        filters=get_remote_filters('vn', {'id': ','.join([ vn['id'] for vn in character['vns']])}),
        fields=['va.staff.id', 'va.staff.name', 'va.staff.original', 'va.character.id', 'va.note']
    )['results']

    seiyuu = list({
        (d['id'], d['name'], d['original'], d['note']): d
        for d in [
            {
                'id': va['staff']['id'],
                'name': va['staff']['name'],
                'original': va['staff']['original'],
                'note': va['note']
            }
            for vn in vns
            for va in vn['va']
            if va['character']['id'] == charid
    ]}.values())

    return seiyuu

# ─── Searching ────────────────────────────────────────────────────────────────

@dated
def search(resource_type: str, params: dict[str, Any], response_size: str = 'small',
           page: int = 1, limit: int = 100,
           sort: str = 'id', reverse: bool = False, count: bool = True) -> dict[str, Any]:

    search_functions = {
        'vn': search_vn,
        'character': search_character,
        'tag': search_tag,
        'producer': search_producer,
        'staff': search_staff,
        'trait': search_trait,
        'release': search_release
    }

    if resource_type not in search_functions:
        raise Failed('internal_error', f"Invalid search type: {resource_type}")

    validate_params(resource_type, params)

    # A filter Kana has no equivalent for cannot be applied here. Dropping it
    # would answer with rows it was never applied to, which is worse than not
    # answering: nothing in the reply would say the filter had been ignored.
    if unsupported := set(params) & local_only_params(resource_type):
        raise Rejected('invalid_request',
                       f"Search field(s) not available for remote searches: "
                       f"{', '.join(sorted(unsupported))}")

    filters = get_remote_filters(resource_type, params)
    fields = get_remote_fields(resource_type, response_size)
    sort = validate_sort(resource_type, sort)

    if not filters:
        filters = ["search", "=", ""]
    if not fields:
        fields = "id"

    if page and limit:
        results = search_functions[resource_type](filters, fields, page=page, results=limit, sort=sort, reverse=reverse, count=count)
    else:
        results = unpaginated_search(
            search_function=search_functions[resource_type],
            filters=filters, fields=fields, sort=sort, reverse=reverse, count=count
        )

    if (resource_type == 'vn' and response_size == 'large'):
        for vn in results['results']:
            vnid = vn['id']
            vn['characters'] = vn_additional_field_characters(vnid)
            vn['releases'] = vn_additional_field_releases(vnid)
            vn['publishers'] = vn_additional_field_publishers(vn['releases'])

    if (resource_type == 'character' and response_size == 'large'):
        for char in results['results']:
            char['seiyuu'] = character_additional_field_seiyuu(char)

    return results


@dated
def search_resources_by_release_id(release_id: str, related_resource_type: str, response_size: str = "small") -> dict[str, Any]:
    url = "https://api.vndb.org/kana/release"

    related_resource_fields = get_remote_fields(related_resource_type, response_size)
    fields = {
        'vn': [f'vns.{field}' for field in related_resource_fields] + ['vns.rtype'],
        'producer': [f'producers.{field}' for field in related_resource_fields] + ['producers.developer', 'producers.publisher']
    }.get(related_resource_type)

    payload = {
        "filters": ["id", "=", release_id],
        "fields": ",".join(fields),
        "results": 100
    }

    response = api._request("POST", url, json=payload)
    raise_for_kana_status(response)
    api_results = response.json().get('results', [])
    if not api_results:
        return {'results': []}
    results = api_results[0]
    results = results.get(
        {
            'vn': 'vns',
            'producer': 'producers'
        }.get(related_resource_type)
    )

    return {'results': results}

@dated
def search_resources_by_charid(charid: str, related_resource_type: str, response_size: str = "small") -> dict[str, Any]:
    url = "https://api.vndb.org/kana/character"

    related_resource_fields = get_remote_fields(related_resource_type, response_size)
    fields = {
        'trait': [f'traits.{field}' for field in related_resource_fields] + ['traits.spoiler', 'traits.lie'],
        'vn': [f'vns.{field}' for field in related_resource_fields] + ['vns.spoiler', 'vns.role', 'vns.release.id']
    }

    payload = {
        "filters": ["id", "=", charid],
        "fields": ",".join(fields.get(related_resource_type, [])),
        "results": 100
    }

    response = api._request("POST", url, json=payload)
    raise_for_kana_status(response)
    api_results = response.json().get('results', [])
    if not api_results:
        return {'results': []}
    results = api_results[0]
    results = results.get(
        {
            'trait': 'traits',
            'vn': 'vns'
        }.get(related_resource_type)
    )

    return {'results': results}

@dated
def search_resources_by_vnid(vnid: str, related_resource_type: str, response_size: str = "small") -> dict[str, Any]:
    url = "https://api.vndb.org/kana/vn"

    related_resource_fields = get_remote_fields(related_resource_type, response_size)
    fields = {
        'vn': [f'relations.{field}' for field in related_resource_fields] + ['relations.relation', 'relations.relation_official'],
        'tag': [f'tags.{field}' for field in related_resource_fields] + ['tags.rating', 'tags.spoiler', 'tags.lie'],
        'producer': [f'developers.{field}' for field in related_resource_fields],
        'staff': [f'staff.{field}' for field in related_resource_fields] + ['staff.eid', 'staff.role'],
    }.get(related_resource_type)

    payload = {
        "filters": ["id", "=", vnid],
        "fields": ",".join(fields),
        "results": 100
    }

    response = api._request("POST", url, json=payload)
    raise_for_kana_status(response)
    api_results = response.json().get('results', [])
    if not api_results:
        return {'results': []}
    results = api_results[0]
    results = results.get(
        {
            'vn': 'relations',
            'tag': 'tags',
            'producer': 'developers',
            'staff': 'staff'
        }.get(related_resource_type)
    )

    return {'results': results}

@dated
def search_releases_by_resource_id(resource_type: str, resource_id: str, response_size: str = 'small',
                                   sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
    url = "https://api.vndb.org/kana/release"

    filters = {
        'vn': ['vn', '=', ['id', '=', resource_id]],
        'producer': ['producer', '=', ['id', '=', resource_id]]
    }.get(resource_type)

    release_fields = get_remote_fields("release", response_size)
    sort = validate_sort("release", sort)
    payload = {
        "filters": filters,
        "fields": ",".join(release_fields),
        "sort": sort,
        "reverse": reverse,
        "results": limit,
        "page": page,
        "count": count
    }

    response = api._request("POST", url, json=payload)
    raise_for_kana_status(response)

    return response.json()

@dated
def search_characters_by_resource_id(resource_type: str, resource_id: str, response_size: str = 'small',
                                      sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
    url = "https://api.vndb.org/kana/character"

    filters = {
        'trait': ['trait', '=', [resource_id, 0, 0]],
        'dtrait': ['dtrait', '=', [resource_id, 0, 0]],
        'vn': ['vn', '=', ['id', '=', resource_id]]
    }.get(resource_type)

    character_fields = get_remote_fields("character", response_size)
    sort = validate_sort("character", sort)
    payload = {
        "filters": filters,
        "fields": ",".join(character_fields),
        "sort": sort,
        "reverse": reverse,
        "results": limit,
        "page": page,
        "count": count
    }

    response = api._request("POST", url, json=payload)
    raise_for_kana_status(response)

    return response.json()

@dated
def search_vns_by_resource_id(resource_type: str, resource_id: str, response_size: str = 'small',
                              sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
    url = "https://api.vndb.org/kana/vn"

    filters = {
        'tag': ['tag', '=', [resource_id, 0, 0]],
        'dtag': ['dtag', '=', [resource_id, 0, 0]],
        'staff': ['staff', '=', ['id', '=', resource_id]],
        'producer': ['developer', '=', ['id', '=', resource_id]],
        'character': ['character', '=', ['id', '=', resource_id]],
        'release': ['release', '=', ['id', '=', resource_id]]
    }.get(resource_type)

    vn_fields = get_remote_fields("vn", response_size)
    sort = validate_sort("vn", sort)

    payload = {
        "filters": filters,
        "fields": ",".join(vn_fields),
        "sort": sort,
        "reverse": reverse,
        "results": limit,
        "page": page,
        "count": count
    }

    response = api._request("POST", url, json=payload)
    raise_for_kana_status(response)
    results = response.json()

    if response_size == 'small':
        return results

    for vn in results['results']:
        vnid = vn['id']
        characters = unpaginated_search(
            search_function=search_characters_by_resource_id_cache,
            resource_type='vn', resource_id=vnid, response_size='small'
        )
        vn['characters'] = characters['results']
    return results


# ─── Cached and paginated forms ───────────────────────────────────────────────

@memoize(timeout=3600)
def get_vn_cache(*args, **kwargs): return api.get_vn(*args, **kwargs)


@memoize(timeout=3600)
def search_cache(*args, **kwargs): return search(*args, **kwargs)


@memoize(timeout=3600)
def search_resources_by_vnid_cache(*args, **kwargs): return search_resources_by_vnid(*args, **kwargs)


@memoize(timeout=3600)
def search_resources_by_charid_cache(*args, **kwargs): return search_resources_by_charid(*args, **kwargs)


@memoize(timeout=3600)
def search_resources_by_release_id_cache(*args, **kwargs): return search_resources_by_release_id(*args, **kwargs)


@memoize(timeout=3600)
def search_vns_by_resource_id_cache(*args, **kwargs): return search_vns_by_resource_id(*args, **kwargs)


@memoize(timeout=3600)
def search_characters_by_resource_id_cache(*args, **kwargs): return search_characters_by_resource_id(*args, **kwargs)


@memoize(timeout=3600)
def search_releases_by_resource_id_cache(*args, **kwargs): return search_releases_by_resource_id(*args, **kwargs)


def search_resources_by_vnid_paginated(vnid: str, related_resource_type: str, response_size: str = "small",
                                       sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
    return paginated_results(search_resources_by_vnid_cache(vnid, related_resource_type, response_size),
                             sort, reverse, limit, page, count)


def search_resources_by_charid_paginated(charid: str, related_resource_type: str, response_size: str = "small",
                                         sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
    return paginated_results(search_resources_by_charid_cache(charid, related_resource_type, response_size),
                             sort, reverse, limit, page, count)


def search_resources_by_release_id_paginated(release_id: str, related_resource_type: str, response_size: str = "small",
                                             sort: str = 'id', reverse: bool = False, limit: int = 10, page: int = 1, count: bool = True) -> dict[str, Any]:
    return paginated_results(search_resources_by_release_id_cache(release_id, related_resource_type, response_size),
                             sort, reverse, limit, page, count)
