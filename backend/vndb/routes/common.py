from flask import abort, jsonify

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

def execute_task(task, sync=False, *args, **kwargs):
    if sync:
        result = task(*args, **kwargs)
        return jsonify(result)
    else:
        task_result = task.delay(*args, **kwargs)
        return jsonify({"task_id": task_result.id}), 202