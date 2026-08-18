"""Replay a logged search — re-run the exact query a log entry recorded.

Two flavours, keyed on details['from'] (stamped by
vndbserve.search.common.log_search):

  - remote: re-POST the recorded {url, payload} to the VNDB Kana API and
    return the fresh HTTP status + body.
  - local:  re-execute the recorded compiled SQL (details['query']) against
    the vndbserve database and return the rows.

Replay does NOT go through the vndbserve search functions, so it does not itself
append a new log entry — it's a faithful re-issue of the captured request.
"""

import httpx
from flask import current_app
from sqlalchemy import text

from logserve import db


class ReplayError(Exception):
    def __init__(self, message, http_status=400):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def replay_log(entry):
    details = entry.details or {}
    source = details.get('from')
    if source == 'remote':
        return _replay_remote(details)
    if source == 'local':
        return _replay_local(details)
    raise ReplayError(
        f"Log entry {entry.id} is not replayable: expected details.from in "
        f"('local', 'remote'), got {source!r}."
    )


def _replay_remote(details):
    url = details.get('url')
    payload = details.get('payload')
    if not url or payload is None:
        raise ReplayError("Remote log entry is missing 'url' and/or 'payload'.")

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url, json=payload, headers={'Content-Type': 'application/json'}
        )

    try:
        body = response.json()
    except ValueError:
        body = response.text

    return {
        'backend': 'remote',
        'url': url,
        'payload': payload,
        'status_code': response.status_code,
        'ok': response.is_success,
        'result': body,
    }


def _replay_local(details):
    sql = details.get('query')
    if not sql:
        raise ReplayError("Local log entry is missing the compiled 'query'.")
    if not sql.lstrip().lower().startswith('select'):
        # The captured query is always a compiled SELECT; anything else means a
        # malformed/foreign entry, and we won't run arbitrary DML on replay.
        raise ReplayError("Refusing to replay a non-SELECT local query.")

    # The query is logged with render_postcompile: :name placeholders intact,
    # with the matching values captured under 'query_params'. Re-bind them via
    # text() rather than inlining — that is exactly how the search issued it.
    params = details.get('query_params') or {}
    max_rows = current_app.config['REPLAY_MAX_ROWS']
    try:
        result = db.session.execute(text(sql), params)
        rows = result.mappings().fetchmany(max_rows + 1)
    except Exception as e:
        # Rollback so the poisoned transaction doesn't wedge later requests on
        # this connection. Entries logged before parameter capture carry unbound
        # :param placeholders and can't be re-executed.
        db.session.rollback()
        raise ReplayError(
            f"Could not execute the logged query (entries logged before "
            f"parameter capture are not replayable): {e}"
        )
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    return {
        'backend': 'local',
        'query': sql,
        'query_params': params,
        'row_count': len(rows),
        'truncated': truncated,
        'result': [dict(r) for r in rows],
    }
