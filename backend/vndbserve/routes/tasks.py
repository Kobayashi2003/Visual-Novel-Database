"""Following a queued task.

`execute_task(..., sync=False)` answers with a task id; these are the routes
that id is for.
"""

from flask import Blueprint, jsonify

from vndbserve import celery
from vndbserve.errors import ServiceError
from vndbserve.logger import logger
from vndbserve.tasks.envelope import error_envelope
from .common import task_response

task_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


def _outcome(task):
    """The finished task's envelope.

    A task that returned carries the one a synchronous call would have, so it
    maps onto a status code the same way. One that did not return carries an
    exception instead — retries exhausted, or revoked — and an exception is not
    an envelope: reporting it as a success would answer `200` with a body that
    will not even serialise.
    """
    if task.state == 'SUCCESS' and isinstance(task.result, dict):
        return task.result
    if isinstance(task.result, ServiceError):
        return error_envelope(task.result.kind, task.result.code, task.result.message)
    logger.error(f"Task {task.id} ended in {task.state}: {task.result!r}")
    return error_envelope('failed', 'internal_error', "The task did not complete.")


@task_bp.route('/<string:tid>', methods=['GET'])
def get_task_result(tid: str):
    task = celery.AsyncResult(tid)
    if not task.ready():
        return jsonify(state=task.state), 202
    return task_response(_outcome(task))

@task_bp.route('/<string:tid>', methods=['POST'])
def revoke_task(tid: str):
    if not celery.backend.get(f'celery-task-meta-{tid}'):
        return jsonify(error="not_found", message=f"No task with id {tid}."), 404
    celery.AsyncResult(tid).revoke(terminate=True)
    return jsonify(message="Task revoked"), 200
