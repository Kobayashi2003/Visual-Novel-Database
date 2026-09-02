"""Route-layer helpers: parameter parsing, and task envelope to HTTP.

`task_response` is where a task's `{status: ...}` becomes a status code and the
field is dropped from the body, the one place the internal envelope and the HTTP
contract meet. See docs/api/README.md.
"""

from flask import abort, jsonify

from vndbserve.errors import error_status

_TRUE = {'true', '1', 'yes', 'on'}
_FALSE = {'false', '0', 'no', 'off'}

def parse_bool(raw, default: bool) -> bool:
    """A query parameter as a boolean, or the default when it was not sent.

    A value that is neither is refused rather than replaced by the default, as
    `parse_int` refuses a non-integer: `?sync=perhaps` would otherwise answer
    with a task id where the caller asked for a result, and nothing in the reply
    would say the parameter had been ignored.
    """
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    abort(400, description=f"Expected true or false, got: {raw!r}")

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


# ─── Task envelope to HTTP response ───────────────────────────────────────────

# Tasks report their outcome in a `status` field so that a Celery result carries
# it across the process boundary. The HTTP layer is where that becomes a status
# code: the body never repeats it, because two sources of truth drift apart.
#
# An error arrives already classified (see tasks.common.error_envelope), so the
# status follows from its kind and code rather than from a table of statuses
# kept here.

def task_response(result):
    """Turn a task envelope into a response. On failure the body becomes the
    standard `{error, message}`; on success `status` is stripped and the rest
    is returned as-is."""
    status = result.get('status', 'SUCCESS') if isinstance(result, dict) else 'SUCCESS'
    if status == 'ERROR':
        error = result.get('error') or {}
        code = error.get('code', 'internal_error')
        return (jsonify(error=code, message=error.get('message', "Internal error")),
                error_status(error.get('kind', 'failed'), code))
    if status == 'NOT_FOUND':
        return jsonify(error='not_found', message="No such resource."), 404
    # A new dict rather than a pop: NOT_FOUND and friends are module-level
    # singletons, and mutating one here would corrupt every later use of it.
    # A leading underscore marks a field the layers below pass among themselves;
    # this is the boundary where it stops.
    body = ({k: v for k, v in result.items() if k != 'status' and not k.startswith('_')}
            if isinstance(result, dict) else result)
    return jsonify(body), 200

def execute_task(task, sync=False, *args, **kwargs):
    if not sync:
        return jsonify({"task_id": task.delay(*args, **kwargs).id}), 202
    return task_response(task(*args, **kwargs))
