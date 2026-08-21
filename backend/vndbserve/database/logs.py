"""The `logs` table — what logserve reads.

Not part of operations.py: this table is neither mirrored nor part of a
request's own work. See README.md.
"""

import uuid

from sqlalchemy.orm import Session

from vndbserve import db
from .models import LogEntry


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
