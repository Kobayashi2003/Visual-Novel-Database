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
    if not celery.backend.get(f'celery-task-meta-{tid}'):
        return jsonify(error="not_found", message=f"No task with id {tid}."), 404
    celery.AsyncResult(tid).revoke(terminate=True)
    return jsonify(message="Task revoked"), 200
