"""Turning a function into a Celery task.

Registration, error classification, retry policy and cache invalidation — what
`@task` composes. The reply shape it wraps lives in `envelope.py`.
"""

import json
import random
import re
from functools import wraps
from typing import Any

from celery import current_task

from vndbserve import celery, cache
from vndbserve.database.models import MODEL_MAP
from vndbserve.errors import ServiceError
from vndbserve.logger import logger
from vndbserve.utils.ids import TYPE_BY_PREFIX
from .envelope import NOT_FOUND_CACHE_TIMEOUT, error_envelope


# ─── Constants ────────────────────────────────────────────────────────────────

# The task cache shares a Redis database with the memoized upstream responses in
# search/remote. Only this prefix is ours to drop: a write changes the mirror,
# not what the Kana API replied, so an upstream response it did not invalidate
# must survive it — refetching one costs a call against a rate-limited API.
TASK_CACHE_PREFIX = 'task:'

# What a cached reply is about, recognised in its arguments: a resource type by
# name, a row by the id convention in utils/ids.
_VNDB_ID = re.compile(r'^([vrcpsgi])\d+$')

# Outages worth waiting out in the queue. Rate limiting is deliberately absent:
# the API client already waits the delay the API itself asked for, and retrying
# here as well would multiply the two budgets against an upstream that is
# already complaining.
RETRYABLE_CODES = {'upstream_unavailable', 'upstream_unreachable', 'database_unavailable'}
RETRY_LIMIT = 3
RETRY_BASE_DELAY = 20


# ─── Retry ────────────────────────────────────────────────────────────────────

def _retry_delay(attempt: int) -> int:
    """Exponential, with jitter so a queue that failed together does not come
    back together and knock the dependency over again."""
    return int(RETRY_BASE_DELAY * (2 ** attempt) * (0.5 + random.random()))


def _may_retry(exc: ServiceError) -> bool:
    """Whether a second attempt is worth making, and allowed to be made.

    Only an outage qualifies: the caller cannot change anything to fix it and a
    defect of ours will fail again identically. And only in a worker — a
    synchronous call has a request waiting on it, where retrying would multiply
    someone's wait instead of letting them decide when to come back.
    """
    if exc.kind != 'unavailable' or exc.code not in RETRYABLE_CODES:
        return False
    request = getattr(current_task, 'request', None)
    if request is None or request.id is None or request.called_directly:
        return False
    return (request.retries or 0) < RETRY_LIMIT


# ─── Error classification ─────────────────────────────────────────────────────

def error_handler(retry: bool = False):
    """The queue's final handler: nothing leaves it unclassified.

    The kind decides how it is logged — a defect of ours carries its traceback,
    a dependency outage is noted without one, and a rejected request is not our
    news to report. An exception that arrives unclassified can only be a defect
    of ours.

    `retry` is opt-in per task, because running a task again is only harmless
    where the work is one whole unit; a batch would redo everything it had
    already finished.
    """
    def decorate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ServiceError as exc:
                if retry and _may_retry(exc):
                    attempt = current_task.request.retries or 0
                    logger.warning(f"{func.__name__} retrying after {exc.code} "
                                   f"(attempt {attempt + 1}/{RETRY_LIMIT})")
                    raise current_task.retry(exc=exc, countdown=_retry_delay(attempt),
                                             max_retries=RETRY_LIMIT)
                if exc.kind == 'failed':
                    logger.exception(f"{func.__name__} failed: {exc.message} {exc.context}")
                elif exc.kind == 'unavailable':
                    logger.warning(f"{func.__name__} unavailable: {exc.message} {exc.context}")
                return error_envelope(exc.kind, exc.code, exc.message)
            except Exception:
                logger.exception(f"{func.__name__} failed")
                return error_envelope('failed', 'internal_error', "Internal error")
        return wrapper
    return decorate


# ─── The task cache ───────────────────────────────────────────────────────────

def _cache_tags(value: Any) -> set[str]:
    """The resource types and row ids a reply is about, read off its arguments.

    A key already carries the arguments, so most of this is redundant — but not
    all of it: `get_relation_graph_task('v17', …)` names a row without naming
    its type, and a write to some other VN must still reach it. Recording the
    type alongside the id is what makes that write and this reply meet.
    """
    tags: set[str] = set()
    if isinstance(value, str):
        if value in MODEL_MAP:
            tags.add(value)
        elif match := _VNDB_ID.match(value):
            tags.add(value)
            if resource_type := TYPE_BY_PREFIX.get(match.group(1)):
                tags.add(resource_type)
    elif isinstance(value, dict):
        for name, item in value.items():
            tags |= _cache_tags(name) | _cache_tags(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            tags |= _cache_tags(item)
    return tags


def _cache_op(description: str, run):
    """Run a cache operation, and go on without it when the cache is down.

    The cache holds work that can always be done again, so a Redis that cannot
    be reached must not turn a read into a failure — a failed lookup is simply
    a miss. An invalidation that could not run leaves nothing stale to find
    either: while the cache is unreachable nothing is served from it.
    """
    try:
        return run()
    except Exception as exc:
        logger.warning(f"Cache unavailable, {description} skipped: {exc!r}")
        return None


def _memoized(func, timeout):
    """Serve the reply from the cache when the same arguments come back."""
    @wraps(func)
    def run(*args, **kwargs):
        tags = _cache_tags(args) | _cache_tags(kwargs)
        key = (f"{TASK_CACHE_PREFIX}{func.__name__}"
               f":{json.dumps(args, sort_keys=True, default=str)}"
               f":{json.dumps(kwargs, sort_keys=True, default=str)}"
               f":{json.dumps(sorted(tags))}")
        result = _cache_op('lookup', lambda: cache.get(key))
        if result is not None:
            return result
        result = func(*args, **kwargs)
        if result['status'] == 'SUCCESS':
            # A degraded reply is a success — it carries real rows — but it was
            # shaped by a dependency failing. Caching it would outlive the
            # outage and keep serving the fallback after recovery.
            if not result.get('meta', {}).get('degraded'):
                _cache_op('store', lambda: cache.set(key, result, timeout=timeout))
        elif result['status'] == 'NOT_FOUND':
            _cache_op('store', lambda: cache.set(key, result, timeout=NOT_FOUND_CACHE_TIMEOUT))
        return result
    return run


def _drop_task_cache() -> None:
    """Drop every cached task reply, and nothing else.

    For a write that touches more rows than it names, where no tag would be
    narrower than the whole layer. The prefix is what keeps it from reaching the
    upstream response cache, which a mirror write cannot invalidate.
    """
    def drop():
        backend = getattr(cache, 'cache', None)
        client = getattr(backend, '_write_client', None) or getattr(backend, '_read_client', None)
        if client is None:
            cache.clear()      # a backend with no keyspace to scan
            return
        pattern = f'{getattr(backend, "key_prefix", "")}{TASK_CACHE_PREFIX}*'
        for key in client.scan_iter(match=pattern, count=500):
            client.delete(key)

    _cache_op('invalidation', drop)


def _drop_entity_cache(resource_type: str, resource_id: str) -> None:
    """Drop the cached replies that can contain this row.

    Two tags decide it, and the row's id alone is not enough: a listing's key
    names the query rather than the rows in its result, so a reply showing this
    row need not name it. The type is the second tag, and it does reach those
    listings — at the cost of dropping replies of that type which the row never
    appeared in.

    Both are matched quoted, which is what keeps `v17` from matching `v170`.
    Every other type is left alone, which matters because a stale-serve refresh
    runs on ordinary reads.
    """
    def drop():
        backend = getattr(cache, 'cache', None)
        client = getattr(backend, '_write_client', None) or getattr(backend, '_read_client', None)
        if client is None:
            _drop_task_cache()      # a backend with no keyspace to scan
            return

        prefix = f'{getattr(backend, "key_prefix", "")}{TASK_CACHE_PREFIX}'
        for tag in (resource_id, resource_type):
            for key in client.scan_iter(match=f'{prefix}*"{tag}"*', count=500):
                client.delete(key)

    _cache_op('invalidation', drop)


def _invalidating_all(func):
    @wraps(func)
    def run(*args, **kwargs):
        result = func(*args, **kwargs)
        _drop_task_cache()
        return result
    return run


def _invalidating_entity(func):
    """The row is named by the first two arguments, as every such task takes
    the type and the id in that order."""
    @wraps(func)
    def run(resource_type, resource_id, *args, **kwargs):
        result = func(resource_type, resource_id, *args, **kwargs)
        _drop_entity_cache(resource_type, resource_id)
        return result
    return run


# ─── The decorator ────────────────────────────────────────────────────────────

def task(func=None, *, retry=False, cache_for=None, invalidates=None):
    """Register a function as a Celery task.

    Registration and error classification are what every task gets. The keyword
    arguments add what one particular task needs:

    `retry`       — queue another attempt when a dependency is down. Only for
                    work that is one whole unit: retrying a batch would redo
                    what it had already finished.
    `cache_for`   — seconds to keep the reply, keyed by the arguments.
    `invalidates` — `'entity'` drops the cached replies that can contain the row
                    this task wrote; `'all'` drops every cached reply, for a
                    write that touches more rows than it names.

    Caching and invalidating are alternatives: one belongs to a read, the other
    to a write.
    """
    if invalidates not in (None, 'entity', 'all'):
        raise ValueError(f"invalidates must be 'entity', 'all' or None, not {invalidates!r}")
    if cache_for is not None and invalidates is not None:
        raise ValueError("a task either caches its reply or invalidates others, not both")

    def decorate(f):
        run = f
        if cache_for is not None:
            run = _memoized(run, cache_for)
        elif invalidates == 'all':
            run = _invalidating_all(run)
        elif invalidates == 'entity':
            run = _invalidating_entity(run)

        @celery.task
        @wraps(f)
        @error_handler(retry=retry)
        def wrapper(*args, **kwargs):
            return run(*args, **kwargs)
        return wrapper

    return decorate(func) if func else decorate
