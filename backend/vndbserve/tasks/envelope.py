"""What a task returns.

Every task answers with the same envelope, so an outcome survives the trip back
from a worker and the route layer can turn it into a status code without knowing
which task produced it. See routes/common.
"""

from typing import Any

from vndbserve import db
from vndbserve.database import convert_model_to_dict

NOT_FOUND = {'status': 'NOT_FOUND', 'results': None}

# A missing row is worth remembering only briefly: unlike a found one, it is
# expected to change as soon as the crawl reaches it.
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


def already_so(resource_id: str) -> dict[str, Any]:
    """A definite answer of "the state you asked for is already the case".

    An operation whose goal is a state — absent, present — has met that goal
    when the row it looked for is not there. Reporting NOT_FOUND instead would
    make a second identical request fail where the first succeeded, which is
    also what a retried one would do.
    """
    return {'status': 'SUCCESS', 'results': {'id': resource_id}}


def error_envelope(kind: str, code: str, message: str) -> dict[str, Any]:
    """An error, as a value that survives the trip back from a worker.

    The kind and the code both travel: the route needs the code to name the
    error and the kind to settle its status. `context` does not travel — it is
    for the log alone and must never reach a client.
    """
    return {'status': 'ERROR',
            'error': {'kind': kind, 'code': code, 'message': message}}


def with_meta(results: dict[str, Any], **axes: Any) -> dict[str, Any]:
    """Say how the answer was produced, without guessing.

    An axis the layer did not actually determine is left out — a caller reads a
    missing axis as unknown, which is true, where a filled-in default would not
    be. Only `both` weighs freshness and coverage, so only `both` reports them.
    """
    results['meta'] = {**results.get('meta', {}), **axes}
    return results
