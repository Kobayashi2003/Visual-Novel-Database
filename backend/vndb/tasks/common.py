import json
from typing import Any

from functools import wraps

from vndb import celery, cache, db
from vndb.database import convert_model_to_dict
from vndb.logger import logger

NOT_FOUND = {'status': 'NOT_FOUND', 'results': None}
NOT_FOUND_CACHE_TIMEOUT = 60

def format_results(results: Any) -> dict[str, Any]:
    """Wrap a task's return value in the status envelope.

    A dict that already carries a `results` key is passed through rather than
    nested a second level deep. Emptiness is tested with `is None`, not
    truthiness: a search that matched nothing, or a delete that removed 0 rows,
    is a successful answer of zero — only a missing value is NOT_FOUND."""
    if results is None:
        return dict(NOT_FOUND)
    if isinstance(results, db.Model):
        return {'status': 'SUCCESS', 'results': convert_model_to_dict(results)}
    if isinstance(results, list) and all(isinstance(item, db.Model) for item in results):
        return {'status': 'SUCCESS', 'results': [convert_model_to_dict(item) for item in results]}
    if isinstance(results, dict) and 'results' in results:
        return {**results, 'status': 'SUCCESS'}
    return {'status': 'SUCCESS', 'results': results}

def error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception(f"{func.__name__} failed")
            return {"status": "ERROR", "results": "Internal error"}
    return wrapper

def clear_caches(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        cache.clear()
        return result
    return wrapper

def task_with_cache_clear(func):
    @celery.task
    @wraps(func)
    @error_handler
    @clear_caches
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def task_basic(func):
    @celery.task
    @wraps(func)
    @error_handler
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def task_with_memoize(timeout=60*60*24):
    def decorator(func):
        @celery.task
        @wraps(func)
        @error_handler
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{json.dumps(args, sort_keys=True, default=str)}:{json.dumps(kwargs, sort_keys=True, default=str)}"
            result = cache.get(cache_key)
            if result is None:
                result = func(*args, **kwargs)
                if result['status'] == 'SUCCESS':
                    cache.set(cache_key, result, timeout=timeout)
                elif result['status'] == 'NOT_FOUND':
                    cache.set(cache_key, result, timeout=NOT_FOUND_CACHE_TIMEOUT)
            return result
        return wrapper
    return decorator
