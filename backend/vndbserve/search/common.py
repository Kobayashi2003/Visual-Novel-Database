"""Helpers shared by the local and remote search paths.

`convert_remote_to_local` reshapes a Kana API payload into the local column
layout, dropping the relation-only fields the local schema has no place for; every
crawl path writes through it. The `process_*` helpers normalise the formats the
two sides disagree on (resolution, release date, birthday), and `log_search`
records a query for logserve to replay.
"""

import re

from vndbserve.logger import add_log_entry, logger
from vndbserve.errors import Failed


def log_search(source: str, message: str, details: dict | None = None, level: str = 'info') -> None:
    """Record a search event in the `logs` table (see database.models.LogEntry).

    This centralizes the observability write shared by the local and remote
    search backends: the originating backend is stamped under
    ``details['from']`` ('local' | 'remote') so downstream tooling (logserve)
    can filter and replay by source.

    Best-effort by design: a logging failure must never break the search it is
    observing, so any DB error is swallowed (and noted in the file log) after
    rolling the session back to a clean state.
    """
    entry = {'from': source}
    if details:
        entry.update(details)
    try:
        add_log_entry(level, message, entry)
    except Exception:
        try:
            from vndbserve import db
            db.session.rollback()
        except Exception:
            pass
        logger.exception("Failed to record search log entry")


def process_resolution(resolution_value):
    if not resolution_value:
        return None
    s = re.sub(r'\s', '', str(resolution_value))
    # Normalize "[WIDTH,HEIGHT]" or "WIDTH,HEIGHT" → "WIDTHxHEIGHT"
    m = re.match(r'^\[?(\d+),(\d+)\]?$', s)
    if m:
        return f"{m.group(1)}x{m.group(2)}"
    return s

def process_released(released_value):
    if not released_value:
        return None
    return re.sub(r'\s', '', str(released_value))

def process_birthday(birthday_value):
    if not birthday_value:
        return None
    return re.sub(r'\s', '', str(birthday_value))

def convert_remote_to_local(entity_type, remote_data):
    entity_type = entity_type.lower()
    local_data = remote_data.copy()

    local_data.pop('id', None)

    if entity_type == 'vn':
        for field in ['relation', 'relation_official', 'role', 'spoiler', 'release', 'rtype']:
            local_data.pop(field, None)
        local_data['released'] = process_released(local_data.pop('released'))

    elif entity_type == 'character':
        for field in ['role', 'spoiler']:
            local_data.pop(field, None)
        local_data['birthday'] = process_birthday(local_data.pop('birthday'))

    elif entity_type == 'staff':
        for field in ['eid', 'role', 'note']:
            local_data.pop(field, None)

    elif entity_type == 'tag':
        for field in ['rating', 'spoiler', 'lie']:
            local_data.pop(field, None)

    elif entity_type == 'trait':
        for field in ['spoiler', 'lie']:
            local_data.pop(field, None)

    elif entity_type == 'producer':
        for field in ['developer', 'publisher']:
            local_data.pop(field, None)

    elif entity_type == 'release':
        local_data['resolution'] = process_resolution(local_data.pop('resolution', None))
        local_data['released'] = process_released(local_data.pop('released'))

    else:
        raise Failed('internal_error', f"Unknown entity type: {entity_type}")

    return local_data