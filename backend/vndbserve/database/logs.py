"""The `logs` table — what logserve reads.

Not part of operations.py: this table is neither mirrored nor part of a
request's own work, so none of the guarantees that layer owes a caller apply to
it. Both functions here run on a session of their own for that reason.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from vndbserve import db
from .models import LogEntry

# What a successful search writes. Separated from the rest because the two are
# worth keeping for different lengths of time — see schedule/logs.py.
ROUTINE_LEVELS = ('debug', 'info')

# Rows per transaction. A single DELETE over months of rows holds one lock for
# as long as it takes and writes one enormous WAL record; a loop of bounded
# statements lets other writers in between them.
DELETE_BATCH = 20_000


def add_log_entry(level: str, message: str, details: dict | None = None) -> None:
    """Write one row, on a session of its own.

    Observing something must not decide when that something's own work is
    committed. Sharing the request's session would commit whatever the caller
    still had pending, and a failure here would poison the session the caller
    is still using.
    """
    with Session(db.engine) as session:
        session.add(LogEntry(
            id=str(uuid.uuid4()),
            level=level,
            message=message,
            details=details
        ))
        session.commit()


def delete_log_entries_before(cutoff: datetime, levels: tuple[str, ...] | None = None) -> int:
    """Remove log rows older than `cutoff`, and say how many.

    `levels` narrows it to those levels; without it every level goes. Deleted in
    bounded batches on a session of its own, for the same reason `add_log_entry`
    uses one: this is housekeeping, and it has no business committing anything
    a caller still had open.
    """
    removed = 0
    with Session(db.engine) as session:
        while True:
            doomed = session.query(LogEntry.id).filter(LogEntry.timestamp < cutoff)
            if levels is not None:
                doomed = doomed.filter(LogEntry.level.in_(levels))
            ids = [row.id for row in doomed.limit(DELETE_BATCH)]
            if not ids:
                return removed
            removed += (session.query(LogEntry)
                        .filter(LogEntry.id.in_(ids))
                        .delete(synchronize_session=False))
            session.commit()
