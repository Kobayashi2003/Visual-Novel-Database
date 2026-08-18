"""A developer's view of the vndbserve `logs` table: browse, filter, replay.

Replay re-executes a logged query against the database, which is why this service
has no route at the edge and is reachable on loopback only.
"""

from flask import Blueprint, jsonify, render_template, request

from . import operations
from .operations import ValidationError
from .replay import replay_log, ReplayError

api_bp = Blueprint('api', __name__, url_prefix='/')


@api_bp.errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e.description)), 400

@api_bp.errorhandler(404)
def not_found(e):
    return jsonify(error="Resource not found"), 404

@api_bp.errorhandler(500)
def server_error(e):
    return jsonify(error="An unexpected error occurred"), 500

@api_bp.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify(error=e.error_code, message=e.message), e.http_status

@api_bp.errorhandler(ReplayError)
def handle_replay_error(e):
    return jsonify(error="replay_error", message=e.message), e.http_status


@api_bp.route('', methods=['GET'])
def dashboard():
    """The built-in single-page diagnostics UI (same-origin; calls the JSON
    endpoints below)."""
    return render_template('index.html')


@api_bp.route('/health', methods=['GET', 'TRACE'])
def health():
    """Programmatic liveness check (the human landing page is at '/')."""
    return jsonify({"message": "LOGSERVE"})


# ----------------------------------------
# Listing / filtering
# ----------------------------------------

@api_bp.route('/logs', methods=['GET'])
def logs_list():
    """Paginated, filtered listing (newest first).

    Query params: level, source ('local'|'remote'), resource_type, search
    (message substring), start / end (ISO-8601 timestamp bounds), page, limit,
    sort (timestamp|level|message), reverse (bool)."""
    reverse = request.args.get('reverse', 'true').lower() in ('true', '1', 'yes')
    return jsonify(operations.list_logs(
        level=request.args.get('level'),
        source=request.args.get('source'),
        resource_type=request.args.get('resource_type'),
        search=request.args.get('search'),
        start=request.args.get('start'),
        end=request.args.get('end'),
        page=int(request.args.get('page', 1)),
        limit=int(request.args.get('limit', 50)),
        sort=request.args.get('sort', 'timestamp'),
        reverse=reverse,
    ))


@api_bp.route('/stats', methods=['GET'])
def logs_stats():
    """Aggregate counts by level and source, for an at-a-glance overview."""
    return jsonify(operations.stats())


@api_bp.route('/logs/<log_id>', methods=['GET'])
def logs_get(log_id):
    """Single entry with full `details` blob."""
    entry = operations.get_log(log_id)
    if entry is None:
        return jsonify(error="not_found", id=log_id), 404
    return jsonify(entry.serialize(include_details=True))


# ----------------------------------------
# Mutation
# ----------------------------------------

@api_bp.route('/logs', methods=['POST'])
def logs_create():
    """Insert a manual entry. Body: {level, message, details?}."""
    body = request.get_json(silent=True) or {}
    entry = operations.create_log(
        level=body.get('level'),
        message=body.get('message'),
        details=body.get('details'),
    )
    return jsonify(entry.serialize(include_details=True)), 201


@api_bp.route('/logs/<log_id>', methods=['DELETE'])
def logs_delete(log_id):
    deleted = operations.delete_log(log_id)
    if not deleted:
        return jsonify(error="not_found", id=log_id), 404
    return jsonify({"status": "ok", "deleted": log_id})


@api_bp.route('/logs/delete', methods=['POST'])
def logs_bulk_delete():
    """Bulk delete by id list OR by filter. Body:
        {"ids": [...]}                                 # explicit ids, or
        {"level"?, "source"?, "resource_type"?,        # filtered delete
         "search"?, "start"?, "end"?}, or
        {"all": true}                                  # clear everything

    A selector is mandatory — an empty body is rejected (see operations)."""
    body = request.get_json(silent=True) or {}
    deleted = operations.bulk_delete(
        ids=body.get('ids'),
        level=body.get('level'),
        source=body.get('source'),
        resource_type=body.get('resource_type'),
        search=body.get('search'),
        start=body.get('start'),
        end=body.get('end'),
        all=bool(body.get('all', False)),
    )
    return jsonify({"status": "ok", "deleted": deleted})


# ----------------------------------------
# Replay
# ----------------------------------------

@api_bp.route('/logs/<log_id>/replay', methods=['POST'])
def logs_replay(log_id):
    """Re-run the query captured by a log entry and return its fresh result.

    Remote entries are re-POSTed to the VNDB Kana API; local entries re-execute
    their compiled SQL against the vndbserve database. Replay does not create a new
    log entry."""
    entry = operations.get_log(log_id)
    if entry is None:
        return jsonify(error="not_found", id=log_id), 404
    return jsonify(replay_log(entry))
