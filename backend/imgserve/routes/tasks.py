from flask import Blueprint, jsonify

from imgserve import celery
from .common import task_response

task_bp = Blueprint('tasks', __name__, url_prefix='/tasks')

@task_bp.route('/<string:tid>', methods=['GET'])
def get_task_result(tid: str):
    task = celery.AsyncResult(tid)
    if not task.ready():
        return jsonify(state=task.state), 202
    # The finished task carries the same outcome a sync call would have
    # returned, so it maps onto a status code the same way.
    return task_response(task.result)

@task_bp.route('/<string:tid>', methods=['POST'])
def revoke_task(tid: str):
    """Ask the queue not to run this task.

    The id is not checked first: the result backend only holds a task once it
    has finished, so an id still queued and an id that never existed are
    indistinguishable — and refusing the first is refusing the only case this
    route exists for. Revoking an id the queue does not know costs nothing.

    Not `terminate=True`: the workers run a thread pool, which cannot kill a
    running job. This stops a task that has not started yet; one already
    running finishes.
    """
    celery.AsyncResult(tid).revoke()
    return jsonify(message="Task revoked"), 200
