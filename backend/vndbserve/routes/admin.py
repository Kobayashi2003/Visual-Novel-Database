"""Operator controls. Loopback only: the edge does not expose this prefix.

Two things live here. The query API's data-source mode is held in module state
so it can be flipped without a restart, and the column backfill is queued as a
task because it walks a whole table.
"""

from flask import Blueprint, jsonify, render_template, request

from vndbserve.routes import query as query_module
from vndbserve.tasks.backfill import backfill_column_task
from .common import execute_task

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

_VALID_MODES = ('default', 'local', 'remote', 'disabled')

@admin_bp.route('', methods=['GET'])
def admin_page():
    return render_template('admin.html')


# ─── Query mode ───────────────────────────────────────────────────────────────

@admin_bp.route('/query-mode', methods=['GET'])
def get_query_mode():
    return jsonify(mode=query_module.QUERY_MODE)


@admin_bp.route('/query-mode', methods=['POST'])
def set_query_mode():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get('mode', '')
    if mode not in _VALID_MODES:
        return jsonify(error="invalid_request",
                       message=f"Mode must be one of: {', '.join(_VALID_MODES)}."), 400
    query_module.QUERY_MODE = mode
    return jsonify(mode=mode)


# ─── Backfill ─────────────────────────────────────────────────────────────────

@admin_bp.route('/backfill', methods=['POST'])
def trigger_backfill():
    data = request.get_json(force=True, silent=True) or {}
    resource_type = data.get('resource_type', '').strip()
    field = data.get('field', '').strip()

    if not resource_type or not field:
        return jsonify(error="invalid_request",
                       message="resource_type and field are required."), 400

    # Queued, not run here: the reply carries a task id, and /tasks/<id> is
    # where its outcome is read — the same path every other queued job takes.
    return execute_task(backfill_column_task, False, resource_type, field)
