"""Every read and write against the mirrored tables.

The only layer that touches the session. Each operation exists twice — a private
`_name` that does the work and a public `name` that wraps it — because the
private ones call each other and the wrapper must run once, not once per nesting
level. What each wrapper guarantees is stated where it is defined.
"""

from typing import Any
from datetime import datetime, timezone, timedelta
from functools import wraps

from sqlalchemy import Integer, asc, desc, func
from sqlalchemy.exc import SQLAlchemyError, OperationalError, InterfaceError

from vndbserve import db
from vndbserve.errors import Failed, Rejected, Unavailable
from vndbserve.utils.ids import format_id
from .models import MODEL_MAP, ModelType

# How long after a crawl an automatic one may write the row again. It lives here
# rather than with the rest of the freshness policy because it guards the write,
# not the decision to serve.
AUTO_CRAWL_INTERVAL = timedelta(minutes=10)

# The most rows one call will ever materialise. Not a page size — callers state
# that — but a ceiling, so a mistaken `limit` cannot pull a whole table into
# memory.
MAX_ROWS = 100

# Maintained here from `source`, never writable by a caller.
PROTECTED_COLUMNS = {'id', 'created_at', 'updated_at', 'crawled_at', 'edited_at',
                     'deleted_at'}


# ─── Wrappers ─────────────────────────────────────────────────────────────────

def _classified(exc: Exception, call: str) -> Exception:
    """The kind a driver exception belongs to.

    A dropped connection or a database refusing queries is a dependency being
    down; anything else the ORM raises is a statement this service built
    wrongly.
    """
    if isinstance(exc, (OperationalError, InterfaceError)):
        return Unavailable('database_unavailable',
                           "The database is not answering.",
                           {'call': call, 'cause': repr(exc)})
    return Failed('internal_error',
                  "The database refused a statement this service built.",
                  {'call': call, 'cause': repr(exc)})


def translates_db_errors(func):
    """Let nothing the driver raises escape unclassified.

    The rollback is for the driver's own failures only: a failed statement
    leaves the session unusable for the next one. Anything else passes
    untouched, because the caller may well have work pending that is none of a
    read's business.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise _classified(exc, func.__name__) from exc
    return wrapper


def _commits(func):
    """A write, committed before it returns.

    Undoing a failed write is the savepoint's own job — leaving the block by way
    of an exception rolls that back and nothing else, so whatever the caller had
    pending survives. Rolling the session back here as well would throw that
    away, which is why this holds no handler: the driver's failures belong to
    `translates_db_errors`, which does roll the session back, because a failed
    statement leaves all of it unusable.

    Committing is what every exported write owes its caller; leaving it to them
    is how half-written state escapes.
    """
    @translates_db_errors
    @wraps(func)
    def wrapper(*args, **kwargs):
        with db.session.begin_nested():
            result = func(*args, **kwargs)
        db.session.commit()
        return result
    return wrapper


def sort_column(model, sort: str):
    """The expression a listing is ordered by.

    An id is ordered by the number inside it. The column is text, so plain
    ordering puts `v10` before `v9`, while the remote backend sorts them
    numerically — and `id` is the default sort, so every unordered listing
    would be paged one way locally and another way remotely.
    """
    column = getattr(model, sort)
    if sort == 'id':
        return func.cast(func.substring(column, r'\d+'), Integer)
    return column


def _order_by(model, sort: str, reverse: bool):
    if sort not in {c.name for c in model.__table__.columns}:
        raise Rejected('invalid_request', f"Invalid sort column: {sort}")
    return (desc if reverse else asc)(sort_column(model, sort))


def _page(query, page: int | None, limit: int | None):
    if not (page and limit):
        return query
    return query.offset((max(1, page) - 1) * limit).limit(min(max(1, limit), MAX_ROWS))


# ─── The work ─────────────────────────────────────────────────────────────────

def _exists(resource_type: str, id: str) -> bool:
    id = format_id(resource_type, id)
    item = db.session.get(MODEL_MAP[resource_type], id)
    return item is not None and item.deleted_at is None


def _get(resource_type: str, id: str) -> ModelType | None:
    id = format_id(resource_type, id)
    model = MODEL_MAP[resource_type]
    return (db.session.query(model)
            .filter(model.id == id, model.deleted_at.is_(None))
            .first())


def _get_all(resource_type: str, page: int | None = None, limit: int | None = None,
             sort: str = 'id', reverse: bool = False) -> list[ModelType]:
    model = MODEL_MAP[resource_type]
    query = (db.session.query(model)
             .filter(model.deleted_at.is_(None))
             .order_by(_order_by(model, sort, reverse)))
    return _page(query, page, limit).all()


def _get_inactive(resource_type: str, id: str) -> ModelType | None:
    id = format_id(resource_type, id)
    model = MODEL_MAP[resource_type]
    return (db.session.query(model)
            .filter(model.id == id, model.deleted_at.is_not(None))
            .first())


def _get_inactive_all(resource_type: str, page: int | None = None,
                      limit: int | None = None, sort: str = 'id',
                      reverse: bool = False) -> list[ModelType]:
    model = MODEL_MAP[resource_type]
    query = (db.session.query(model)
             .filter(model.deleted_at.is_not(None))
             .order_by(_order_by(model, sort, reverse)))
    return _page(query, page, limit).all()


# `source` records what kind of write this is:
#   'crawl' (default) — data fetched from the remote API; stamps crawled_at with
#                       `crawled_at` when given, because a reply that came
#                       through a cache is as old as its fetch, not as new as
#                       this write
#   'edit'            — a manual user edit; stamps edited_at, which freezes the
#                       row against automatic sync (see `updatable`)
#   'refresh'         — explicit re-crawl of one row; stamps crawled_at and
#                       clears edited_at, returning the row to the sync cycle
#   None              — maintenance write (e.g. backfill); stamps neither
def _create(resource_type: str, id: str, data: dict[str, Any],
            source: str | None = 'crawl',
            crawled_at: datetime | None = None) -> ModelType | None:
    id = format_id(resource_type, id)
    if _exists(resource_type, id):
        return None
    # An id may still be held by a row in the trash, which would collide on the
    # primary key.
    _cleanup(resource_type, id)
    item = MODEL_MAP[resource_type](
        id=id, **{k: v for k, v in data.items() if k != 'id'})
    if source == 'crawl':
        item.crawled_at = crawled_at or datetime.now(timezone.utc)
    elif source == 'edit':
        item.edited_at = datetime.now(timezone.utc)
    db.session.add(item)
    db.session.flush()
    return item


def _update(resource_type: str, id: str, data: dict[str, Any],
            source: str | None = 'crawl',
            crawled_at: datetime | None = None) -> ModelType | None:
    item = _get(resource_type, id)
    if not item:
        return None
    columns = {c.name for c in item.__table__.columns}
    for key, value in data.items():
        if key in columns and key not in PROTECTED_COLUMNS:
            setattr(item, key, value)
    now = datetime.now(timezone.utc)
    item.updated_at = now
    if source == 'crawl':
        item.crawled_at = crawled_at or now
    elif source == 'edit':
        item.edited_at = now
    elif source == 'refresh':
        item.crawled_at = now
        item.edited_at = None
    db.session.flush()
    return item


def _delete(resource_type: str, id: str) -> ModelType | None:
    item = _get(resource_type, id)
    if not item:
        return None
    item.deleted_at = datetime.now(timezone.utc)
    db.session.flush()
    return item


def _delete_all(resource_type: str) -> int:
    model = MODEL_MAP[resource_type]
    count = (db.session.query(model)
             .filter(model.deleted_at.is_(None))
             .update({model.deleted_at: datetime.now(timezone.utc)}))
    db.session.flush()
    return count


def _recover(resource_type: str, id: str) -> ModelType | None:
    item = _get_inactive(resource_type, id)
    if not item:
        return None
    item.deleted_at = None
    db.session.flush()
    return item


def _recover_all(resource_type: str) -> int:
    model = MODEL_MAP[resource_type]
    count = (db.session.query(model)
             .filter(model.deleted_at.is_not(None))
             .update({model.deleted_at: None}))
    db.session.flush()
    return count


def _cleanup(resource_type: str, id: str) -> ModelType | None:
    item = _get_inactive(resource_type, id)
    if not item:
        return None
    db.session.delete(item)
    db.session.flush()
    return item


def _cleanup_all(resource_type: str) -> int:
    items = _get_inactive_all(resource_type)
    for item in items:
        db.session.delete(item)
    db.session.flush()
    return len(items)


# ─── The public names ─────────────────────────────────────────────────────────

@translates_db_errors
def exists(resource_type: str, id: str) -> bool:
    return _exists(resource_type, id)


@translates_db_errors
def count_all(resource_type: str) -> int:
    model = MODEL_MAP[resource_type]
    return db.session.query(model).filter(model.deleted_at.is_(None)).count()


@translates_db_errors
def deleted_among(resource_type: str, ids: list[str]) -> set[str]:
    """Which of `ids` name a soft-deleted row.

    For a caller holding ids from somewhere other than a query — a parent row's
    relation column, which records what the API reported and knows nothing of a
    later delete. Asking by id keeps the read bounded by the list in hand.
    """
    if not ids:
        return set()
    model = MODEL_MAP[resource_type]
    return {row.id for row in db.session.query(model.id)
            .filter(model.id.in_(ids), model.deleted_at.is_not(None))}


@translates_db_errors
def count_inactive_all(resource_type: str) -> int:
    model = MODEL_MAP[resource_type]
    return db.session.query(model).filter(model.deleted_at.is_not(None)).count()


@translates_db_errors
def updatable(resource_type: str, id: str,
              update_interval: timedelta = AUTO_CRAWL_INTERVAL) -> bool:
    """Whether an automatic crawl may overwrite this row.

    A row nobody holds is free to be written, and so is one that was never
    crawled. A hand-edited row never is: an automatic sync would destroy the
    edit silently. Freshness is judged on `crawled_at` rather than `updated_at`,
    which any write bumps, including the edit this is meant to protect.

    Explicit refresh paths bypass this and clear `edited_at`, which is how a row
    returns to the cycle.
    """
    item = _get(resource_type, id)
    if not item:
        return True
    if item.edited_at is not None:
        return False
    last_crawl = item.crawled_at or item.updated_at
    if last_crawl is None:
        return True
    return datetime.now(timezone.utc) - last_crawl > update_interval


@translates_db_errors
def get(resource_type: str, id: str) -> ModelType | None:
    return _get(resource_type, id)


@translates_db_errors
def get_all(resource_type: str, page: int | None = None, limit: int | None = None,
            sort: str = 'id', reverse: bool = False) -> list[ModelType]:
    return _get_all(resource_type, page, limit, sort, reverse)


@translates_db_errors
def get_inactive(resource_type: str, id: str) -> ModelType | None:
    return _get_inactive(resource_type, id)


@translates_db_errors
def get_inactive_all(resource_type: str, page: int | None = None,
                     limit: int | None = None, sort: str = 'id',
                     reverse: bool = False) -> list[ModelType]:
    return _get_inactive_all(resource_type, page, limit, sort, reverse)


@_commits
def create(resource_type: str, id: str, data: dict[str, Any],
           source: str | None = 'crawl',
           crawled_at: datetime | None = None) -> ModelType | None:
    """The row as written, or None where one already holds that id."""
    return _create(resource_type, id, data, source, crawled_at)


@_commits
def update(resource_type: str, id: str, data: dict[str, Any],
           source: str | None = 'crawl',
           crawled_at: datetime | None = None) -> ModelType | None:
    """The row as written, or None where there is no such row."""
    return _update(resource_type, id, data, source, crawled_at)


@_commits
def delete(resource_type: str, id: str) -> ModelType | None:
    return _delete(resource_type, id)


@_commits
def delete_all(resource_type: str) -> int:
    return _delete_all(resource_type)


@_commits
def recover(resource_type: str, id: str) -> ModelType | None:
    return _recover(resource_type, id)


@_commits
def recover_all(resource_type: str) -> int:
    return _recover_all(resource_type)


@_commits
def cleanup(resource_type: str, id: str) -> ModelType | None:
    return _cleanup(resource_type, id)


@_commits
def cleanup_all(resource_type: str) -> int:
    return _cleanup_all(resource_type)
