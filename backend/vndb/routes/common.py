"""Route-layer helpers: parameter parsing, and task envelope to HTTP.

`task_response` is where a task's `{status: ...}` becomes a status code and the
field is dropped from the body, the one place the internal envelope and the HTTP
contract meet. See docs/api/README.md.
"""

from flask import abort, jsonify

from vndb.errors import http_error_code

_TRUE = {'true', '1', 'yes', 'on'}
_FALSE = {'false', '0', 'no', 'off'}

def parse_bool(raw, default: bool) -> bool:
    if raw is None:
        return default
    raw = str(raw).strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default

def parse_int(raw, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        abort(400, description=f"Expected an integer, got: {raw!r}")
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


# ----------------------------------------
# Task envelope → HTTP response
# ----------------------------------------

# Tasks report their outcome in a `status` field so that a Celery result carries
# it across the process boundary. The HTTP layer is where that becomes a status
# code: the body never repeats it, because two sources of truth drift apart.
TASK_STATUS_CODE = {
    'SUCCESS': 200,
    'NOT_FOUND': 404,
    'ERROR': 500,
}

_STATUS_MESSAGE = {
    404: "No such resource.",
    500: "Internal error",
}

def task_response(result):
    """Turn a task envelope into a response. On failure the body becomes the
    standard `{error, message}`; on success `status` is stripped and the rest
    is returned as-is."""
    status = result.get('status', 'SUCCESS') if isinstance(result, dict) else 'SUCCESS'
    code = TASK_STATUS_CODE.get(status, 200)
    if code != 200:
        return jsonify(error=http_error_code(code), message=_STATUS_MESSAGE[code]), code
    # A new dict rather than a pop: NOT_FOUND and friends are module-level
    # singletons, and mutating one here would corrupt every later use of it.
    body = {k: v for k, v in result.items() if k != 'status'} if isinstance(result, dict) else result
    return jsonify(body), 200

def execute_task(task, sync=False, *args, **kwargs):
    if not sync:
        return jsonify({"task_id": task.delay(*args, **kwargs).id}), 202
    return task_response(task(*args, **kwargs))
