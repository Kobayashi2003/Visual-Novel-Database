"""Route-layer helpers, and the cache-miss path.

`task_response` turns a task outcome into a status code (see docs/api/README.md).
`serve_or_fetch_image` is the rest: a hit is sent straight off disk, and a miss is
downloaded under a single-flight lock, so a page requesting the same image forty
times triggers one fetch. Requesting one variant also queues its sibling.
"""

import os

from flask import abort, jsonify, send_file

from imgserve.errors import http_error_code
from imgserve.database import exists, create
from imgserve.utils import (
    download_image_to_disk, get_image_path,
    record_access, with_single_flight,
)
from imgserve.tasks.images import ensure_image_task


# Covers and screenshots come in a full-size and a '.t' thumbnail variant;
# requesting either is a good signal to prefetch the other.
VARIANT_PAIR = {'cv': 'cv.t', 'cv.t': 'cv', 'sf': 'sf.t', 'sf.t': 'sf'}

# How long a request will wait on an in-flight upstream fetch before giving
# up with 503. Worst case download is FAST_RETRIES * (FAST_TIMEOUT + delay),
# plus some slack so a normal-speed t.vndb.org fetch always finishes inside.
SINGLE_FLIGHT_WAIT = 15.0


# Tasks report their outcome in a `status` field so a Celery result can carry it
# across the process boundary. The HTTP layer is where that becomes a status
# code: the body never repeats it, because two sources of truth drift apart.
TASK_STATUS_CODE = {
    'SUCCESS': 200,
    'NOT_FOUND': 404,
    'CONFLICT': 409,
    'UNAVAILABLE': 503,
    'ERROR': 500,
}

_STATUS_MESSAGE = {
    404: "No such image.",
    409: "That image is already on record.",
    503: "The upstream fetch did not succeed.",
    500: "Internal error",
}

def task_response(result):
    """Turn a task outcome into a response. On failure the body becomes the
    standard `{error, message}`; on success `status` is stripped."""
    status = result.get('status', 'SUCCESS') if isinstance(result, dict) else 'SUCCESS'
    code = TASK_STATUS_CODE.get(status, 200)
    if code != 200:
        return jsonify(error=http_error_code(code), message=_STATUS_MESSAGE[code]), code
    # A new dict rather than a pop: SUCCESS and friends are module-level
    # singletons, and mutating one here would corrupt every later use of it.
    body = {k: v for k, v in result.items() if k != 'status'} if isinstance(result, dict) else result
    return jsonify(body), 200

def execute_task(task, sync=False, *args, **kwargs):
    if not sync:
        return jsonify({"task_id": task.delay(*args, **kwargs).id}), 202
    return task_response(task(*args, **kwargs))


def send_cached_image(path):
    """Serve a cached image file. VNDB images are immutable, so the response
    is marked publicly cacheable for a year — a cache hit never goes back to
    the server."""
    response = send_file(path, mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


def _prefetch_sibling(type: str, id: int) -> None:
    """Best-effort background fetch of the matching .t variant (or full-size
    if a thumbnail was requested) so the next time it's needed, it's local."""
    sibling = VARIANT_PAIR.get(type)
    if sibling is None:
        return
    if os.path.exists(get_image_path(sibling, id)):
        return
    try:
        ensure_image_task.delay(sibling, id)
    except Exception as exc:
        # Don't fail the user-facing response if Celery enqueue blips.
        print(f"[image] sibling prefetch enqueue failed for {sibling}/{id}: {exc}")


def serve_or_fetch_image(type: str, id: int, *, prefetch_sibling: bool = False):
    """Cache-hit fast path + single-flight cold fetch. Returns a Flask
    response or aborts with 503 on timeout / upstream failure.

    `prefetch_sibling=True` schedules a background fetch of the matching
    .t/non-.t variant for the next visitor."""
    image_path = get_image_path(type, id)

    def _finish():
        record_access(type, id)
        if prefetch_sibling:
            _prefetch_sibling(type, id)
        return send_cached_image(image_path)

    if os.path.exists(image_path):
        return _finish()

    def _work() -> bool:
        # If the DB row exists but the file vanished (manual delete, disk
        # wipe, etc.), just re-download without touching the row. Otherwise
        # download + insert the row, matching create()'s semantics.
        if exists(type, id):
            return download_image_to_disk(type, id, fast=True)
        return create(type, id, fast=True) is not None

    def _have_file() -> bool:
        return os.path.exists(image_path)

    ok = with_single_flight(
        f"{type}:{id}", _work, _have_file,
        wait_timeout=SINGLE_FLIGHT_WAIT,
    )
    if not ok:
        # We can't cheaply distinguish "upstream 404" from "upstream slow / down"
        # here, so report transient. The frontend's onError path shows a retry
        # button, which is the right UX for both cases.
        abort(503)
    return _finish()
