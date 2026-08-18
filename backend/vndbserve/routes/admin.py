"""Operator controls. Loopback only: the edge does not expose this prefix.

Two things live here. The query API's data-source mode is held in module state so
it can be flipped without a restart, and the column backfill runs on a background
thread because it walks a whole table.
"""

import threading

from flask import Blueprint, current_app, jsonify, render_template, request

from vndbserve.routes import query as query_module
from vndbserve.utils.backfill import backfill_column

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

_VALID_MODES = ('default', 'local', 'remote', 'disabled')

_backfill_status: dict = {'running': False, 'last': None}


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
    if _backfill_status['running']:
        return jsonify(error="conflict", message="A backfill is already running."), 409

    data = request.get_json(force=True, silent=True) or {}
    resource_type = data.get('resource_type', '').strip()
    field = data.get('field', '').strip()

    if not resource_type or not field:
        return jsonify(error="invalid_request", message="resource_type and field are required."), 400

    def _run():
        with app.app_context():
            try:
                updated, total = backfill_column(resource_type, field)
                _backfill_status['last'] = {'updated': updated, 'total': total, 'error': None}
            except Exception as exc:
                _backfill_status['last'] = {'updated': 0, 'total': 0, 'error': str(exc)}
            finally:
                _backfill_status['running'] = False

    app = current_app._get_current_object()
    _backfill_status['running'] = True
    _backfill_status['last'] = None
    threading.Thread(target=_run, daemon=True).start()
    return jsonify(status='started')


@admin_bp.route('/backfill/status', methods=['GET'])
def get_backfill_status():
    return jsonify(**_backfill_status)
