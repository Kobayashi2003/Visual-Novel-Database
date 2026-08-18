"""Relation-graph traversal for visual novels.

A VN's `relations` field lists its directly related VNs, and those VNs list
theirs in turn, so the whole web of sequels/prequels/fandiscs/side stories that
a title belongs to is the connected component reachable from it. This module
walks that component breadth-first from a root VN and returns the nodes and
edges needed to draw a relation graph (mirroring VNDB's own /rg view).

Efficiency notes
----------------
* Local-first. Relations are stored on each VN row, so a frontier of ids is
  resolved with one batched local query per layer - no remote call when the
  component is already held locally.
* Remote fill. Ids the crawler has not reached yet are fetched from VNDB in
  batches and persisted, so the component can be completed and later traversals
  stay local.
* Bounded work. Traversal stops at GRAPH_DEPTH_CAP layers or GRAPH_NODE_CAP
  nodes and reports `truncated`, so a single huge component can neither explode
  the response nor stall the worker.
"""

from typing import Any

from vndbserve.search import (
    search_local,
    convert_remote_to_local,
)
# Uncached search: ingest must see fresh data, matching the fetch schedules.
from vndbserve.search.remote.search import search as vndb_search
from vndbserve.database import create
from .common import task_with_memoize, format_results, NOT_FOUND

GRAPH_DEPTH_CAP = 8       # BFS layers walked outward from the root
GRAPH_NODE_CAP = 200      # nodes collected before the graph is reported truncated
INGEST_BATCH = 20         # ids per remote ingest request (keeps the OR filter small)
LOCAL_QUERY_BATCH = 100   # ids per local search call (search clamps its page size to 100)

# Node metadata carried for each VN; `relations` is fetched alongside to drive
# the traversal but is stripped from the emitted nodes (edges carry it instead).
GRAPH_NODE_FIELDS = ['id', 'title', 'alttitle', 'titles', 'image', 'released', 'devstatus']

# VNDB relation types come in reciprocal pairs (A "sequel" B <-> B "prequel" A),
# so every undirected edge is seen twice. Each code maps to a canonical code
# plus how to orient it, collapsing the pair to one edge:
#   canonical - the code reported for the edge
#   reverse   - swap (src, dst) so directed arrows point earliest -> latest
#   directed  - whether the edge carries an arrow at all
RELATION_CANONICAL = {
    'seq':  ('seq', False, True),    # has sequel        -> src precedes dst
    'preq': ('seq', True,  True),    # has prequel       -> dst precedes src
    'side': ('side', False, True),   # has side story    -> parent -> side
    'par':  ('side', True,  True),   # has parent story  -> parent -> side
    'fan':  ('fan', False, True),    # has fandisc       -> original -> fandisc
    'orig': ('fan', True,  True),    # has original game -> original -> fandisc
    'alt':  ('alt', False, False),   # alternative version (symmetric)
    'set':  ('set', False, False),   # same setting        (symmetric)
    'char': ('char', False, False),  # shares characters   (symmetric)
    'ser':  ('ser', False, False),   # same series         (symmetric)
}


def _ingest_vns(ids: list[str]) -> None:
    """Fetch full VN data for `ids` from VNDB and persist them, completing the
    component for titles not held locally as an active row. Best-effort: a remote
    failure leaves the graph with whatever is already local rather than failing
    the whole request. `create` overwrites any soft-deleted row with the freshly
    fetched data (cleanup + insert), so a deleted entry is refreshed, not just
    un-deleted."""
    for start in range(0, len(ids), INGEST_BATCH):
        batch = ids[start:start + INGEST_BATCH]
        try:
            # A comma-joined id filter fetches the whole batch in one request.
            response = vndb_search('vn', {'id': ','.join(batch)}, 'large',
                                   page=1, limit=len(batch), count=False)
        except Exception as exc:
            print(f"[VNDB] relation-graph ingest failed for {batch}: {exc}")
            continue
        for item in response.get('results', []):
            data = convert_remote_to_local('vn', item)
            create('vn', item['id'], data)

def _fetch_vn_records(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch active VN rows for `ids` through the shared local search,
    keyed by id. `search` clamps its page size to 100, so ids are queried in
    chunks of that size; the 'large' field set is required because the traversal
    needs each VN's `relations` column (the 'small' set omits it)."""
    records = {}
    for start in range(0, len(ids), LOCAL_QUERY_BATCH):
        chunk = ids[start:start + LOCAL_QUERY_BATCH]
        response = search_local('vn', {'id': ','.join(chunk)}, 'large',
                                page=1, limit=LOCAL_QUERY_BATCH, count=False)
        for record in response['results']:
            records[record['id']] = record
    return records

def _resolve_vns(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Resolve node records (metadata + relations) for a frontier of ids. Active
    VNs come from the local store; any id without an active local row is fetched
    from VNDB and persisted - overwriting a soft-deleted row with fresh data - so
    the component stays complete."""
    records = _fetch_vn_records(ids)

    unresolved = [id for id in ids if id not in records]
    if unresolved:
        _ingest_vns(unresolved)
        records.update(_fetch_vn_records(unresolved))

    return records

def _node_meta(record: dict[str, Any]) -> dict[str, Any]:
    """Keep only the display metadata of a node, dropping the relations array."""
    return {field: record.get(field) for field in GRAPH_NODE_FIELDS}

def _add_edge(edges: dict[Any, dict[str, Any]], src: str, relation: dict[str, Any]) -> None:
    """Fold one observed relation into `edges`, deduplicating reciprocal pairs
    and orienting directed types from the earlier work to the later one."""
    dst = relation['id']
    if dst == src:
        return

    code = relation.get('relation')
    canonical, reverse, directed = RELATION_CANONICAL.get(code, (code, False, False))
    a, b = (dst, src) if reverse else (src, dst)
    key = (a, b, canonical) if directed else (canonical, frozenset((a, b)))
    official = bool(relation.get('relation_official'))

    edge = edges.get(key)
    if edge is None:
        edges[key] = {'a': a, 'b': b, 'relation': canonical,
                      'official': official, 'directed': directed}
    elif official:
        edge['official'] = True

@task_with_memoize(timeout=60 * 60)
def get_relation_graph_task(vnid: str, depth: int = GRAPH_DEPTH_CAP, official_only: bool = False) -> dict[str, Any]:
    depth = min(max(1, depth), GRAPH_DEPTH_CAP)

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[Any, dict[str, Any]] = {}
    visited = {vnid}
    frontier = [vnid]
    truncated = False
    level = 0

    while frontier and level < depth:
        if len(nodes) >= GRAPH_NODE_CAP:
            truncated = True
            break

        records = _resolve_vns(frontier)
        next_frontier = []
        for id in frontier:
            record = records.get(id)
            if record is None:
                continue  # deleted or unreachable - leave it out of the graph
            nodes[id] = _node_meta(record)
            for relation in record.get('relations') or []:
                if official_only and not relation.get('relation_official'):
                    continue
                _add_edge(edges, id, relation)
                neighbor = relation['id']
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
        level += 1

    if frontier:
        truncated = True  # layers remain beyond the depth/node cap

    if vnid not in nodes:
        return NOT_FOUND

    # Drop edges to nodes left unmaterialised at the traversal boundary.
    edge_list = [edge for edge in edges.values() if edge['a'] in nodes and edge['b'] in nodes]

    return format_results({'results': {
        'root': vnid,
        'nodes': list(nodes.values()),
        'edges': edge_list,
        'truncated': truncated,
    }})
