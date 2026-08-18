"""The site-facing read API: `/v17`, `/v`, `/v17/rg`.

One path segment carries both the entity type and, optionally, the id, which is
what lets the frontend build a URL from a VNDB id directly. Reads are
freshness-aware by default (see search/both); `from` pins the source, and the
operator-set QUERY_MODE overrides both.

Because these routes sit at the root they also catch anything the other
blueprints did not claim, so a bad path reports an unknown resource type rather
than a 404.
"""

from flask import Blueprint, abort, jsonify, request
from vndbserve.utils.ids import formatId, TYPE_BY_PREFIX
from vndbserve.tasks.resources import (
    get_resources_task, search_resources_task, query_resources_task
)
from vndbserve.tasks.relation_graph import get_relation_graph_task, GRAPH_DEPTH_CAP
from .common import execute_task, parse_bool, parse_int


def _normalize(query):
    """Split '/v17' into ('vn', 'v17'). Unlike the /vns/<id> routes the prefix
    is mandatory here, because it is what selects the resource type."""
    resource_type = TYPE_BY_PREFIX.get(query[0].lower())
    if not resource_type:
        abort(400, description="Invalid resource type")
    try:
        return resource_type, formatId(resource_type, query)
    except ValueError:
        abort(400, description=f"Invalid ID format: {query}")

query_bp = Blueprint('query', __name__, url_prefix='/')

QUERY_MODE = 'default'  # 'default' | 'local' | 'remote' | 'disabled'


@query_bp.route('/<string:query>/rg', methods=['GET'])
def handle_relation_graph(query):

    if TYPE_BY_PREFIX.get(query[0].lower()) != 'vn':
        abort(400, description="Relation graph is only available for visual novels")

    _, query = _normalize(query)

    if QUERY_MODE == 'disabled':
        abort(503, description="Query API is currently disabled")

    params = request.args.to_dict()
    depth = parse_int(params.pop('depth', None), GRAPH_DEPTH_CAP, 1, GRAPH_DEPTH_CAP)
    official_only = params.pop('official_only', 'false').lower() == 'true'

    return execute_task(get_relation_graph_task, True, query, depth, official_only)

@query_bp.route('/<string:query>', methods=['GET'])
def handle_query(query):

    resource_type = TYPE_BY_PREFIX.get(query[0].lower())
    if not resource_type:
        abort(400, description="Invalid resource type")

    if QUERY_MODE == 'disabled':
        abort(503, description="Query API is currently disabled")

    params = request.args.to_dict()

    # One character is the type prefix on its own — "/v" — so it is a search;
    # anything longer carries an id, "/v17".
    if len(query) == 1:
        page = parse_int(params.pop('page', None), 1, 1)
        limit = parse_int(params.pop('limit', None), 20, 1, 100)
        sort = params.pop('sort', 'id')
        reverse = parse_bool(params.pop('reverse', None), False)
        count = parse_bool(params.pop('count', None), True)

        search_from = params.pop('from', '')
        response_size = params.pop('response_size', 'large')

        if search_from == 'remote' or QUERY_MODE == 'remote':
            return execute_task(search_resources_task,
                True, resource_type, params, response_size, page, limit, sort, reverse, count)

        if search_from == 'local' or QUERY_MODE == 'local':
            return execute_task(get_resources_task,
                True, resource_type, params, response_size, page, limit, sort, reverse, count)

        # both: freshness-aware local/remote composition (vndbserve/search/both)
        return execute_task(query_resources_task,
            True, resource_type, params, response_size, page, limit, sort, reverse, count)

    elif len(query) > 1:
        try:
            int(query[1:])
        except ValueError:
            abort(400, description="Invalid ID format")

        search_from = params.pop('from', '')
        response_size = params.pop('response_size', 'large')

        if search_from == 'remote' or QUERY_MODE == 'remote':
            return execute_task(search_resources_task,
                True, resource_type, {'id': query}, response_size, 1, 1, 'id', False, True)

        if search_from == 'local' or QUERY_MODE == 'local':
            return execute_task(get_resources_task,
                True, resource_type, {'id': query}, response_size, 1, 1, 'id', False, True)

        # both: stale-while-revalidate detail lookup (vndbserve/search/both)
        return execute_task(query_resources_task,
            True, resource_type, {'id': query}, response_size, 1, 1, 'id', False, True)
