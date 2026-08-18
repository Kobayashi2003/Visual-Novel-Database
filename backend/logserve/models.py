from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from logserve import db


class LogEntry(db.Model):
    """Read/prune-side mapping of the `logs` table.

    Mirrors vndbserve.database.models.LogEntry column-for-column: that model is the
    *writer* (the local/remote search backends persist entries through
    vndbserve.search.common.log_search), and this one is the *reader* used by the
    logserve diagnostic API. Keep the two definitions in sync — logserve does
    NOT run create_all(), so the table is whatever vndbserve's migrations produced.

    `details` is a free-form JSONB blob. The conventional keys logserve knows
    about:
      - from:          'local' | 'remote'  — which search backend emitted it
      - resource_type: the entity type searched (vn, character, tag, ...)
      - local  entries: query (compiled SQL), params, page, limit, sort, ...
      - remote entries: url, payload, and (on errors) status_code, response
    """

    __tablename__ = 'logs'

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime(timezone=True), default=func.now())
    level = Column(String)
    message = Column(Text)
    details = Column(JSONB)

    def serialize(self, include_details=True):
        data = {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'level': self.level,
            'message': self.message,
            'source': (self.details or {}).get('from'),
            'resource_type': (self.details or {}).get('resource_type'),
        }
        if include_details:
            data['details'] = self.details
        return data

    def __repr__(self):
        return f"<LogEntry(id={self.id}, timestamp={self.timestamp}, level={self.level}, message={self.message})>"
