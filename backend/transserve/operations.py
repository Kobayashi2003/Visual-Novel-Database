import hashlib
import re
from typing import Any, Iterable

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from transserve import db
from . import markup
from .models import TermEntry, PassageEntry


class ValidationError(Exception):
    """Input-validation failure meant to be reported to the client as a 4xx."""
    error_code = "invalid_request"
    message = "Invalid input."
    http_status = 400

    def __init__(self, message=None, error_code=None, http_status=None):
        if message is not None:
            self.message = message
        if error_code is not None:
            self.error_code = error_code
        if http_status is not None:
            self.http_status = http_status
        super().__init__(self.message)


def normalize_key(text: str) -> str:
    """Normalize a source term into its lookup key: trim, collapse internal
    whitespace, and lower-case. Matching is therefore case- and
    spacing-insensitive while the original form is preserved in `source_text`."""
    return re.sub(r'\s+', ' ', str(text)).strip().lower()


def _coerce_terms(entries: Iterable[dict], default_category: str | None,
                    source_lang: str, target_lang: str) -> list[dict]:
    """Validate and shape raw entry dicts into rows ready for bulk upsert.

    Each entry must provide a non-empty `source` and `target`. `category` is
    optional and falls back to `default_category`. Duplicate source keys within
    the same batch are de-duplicated (last one wins) so the upsert never tries
    to touch the same conflict target twice in one statement."""
    rows: dict[tuple, dict] = {}
    for entry in entries:
        source = (entry.get('source') or '').strip()
        target = (entry.get('target') or '').strip()
        if not source or not target:
            raise ValidationError("Each entry needs a non-empty 'source' and 'target'.")
        s_lang = (entry.get('source_lang') or source_lang).strip()
        t_lang = (entry.get('target_lang') or target_lang).strip()
        key = normalize_key(source)
        rows[(s_lang, t_lang, key)] = {
            'source_lang': s_lang,
            'target_lang': t_lang,
            'source_text': source,
            'source_key': key,
            'target_text': target,
            'category': entry.get('category') or default_category,
        }
    return list(rows.values())


def append_term(entries: Iterable[dict], default_category: str | None = None,
                source_lang: str = 'en', target_lang: str = 'ja') -> int:
    """Insert or update term entries (append/merge semantics).

    Conflicts on (source_lang, target_lang, source_key) update the translation,
    display form and category in place. Returns the number of rows submitted."""
    rows = _coerce_terms(entries, default_category, source_lang, target_lang)
    if not rows:
        return 0

    stmt = pg_insert(TermEntry).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint='uq_term_langs_key',
        set_={
            'source_text': stmt.excluded.source_text,
            'target_text': stmt.excluded.target_text,
            'category': stmt.excluded.category,
            'updated_at': func.now(),
        },
    )
    db.session.execute(stmt)
    db.session.commit()
    return len(rows)


def init_term(entries: Iterable[dict], default_category: str | None = None,
              source_lang: str = 'en', target_lang: str = 'ja',
              replace: bool = False) -> int:
    """Initialize the term base from a batch of entries.

    With `replace=True` the existing rows for the (source_lang, target_lang)
    pair are cleared first, so the term base becomes exactly the provided set.
    Otherwise this behaves like `append_term` (merge into what's there)."""
    if replace:
        (db.session.query(TermEntry)
         .filter(TermEntry.source_lang == source_lang)
         .filter(TermEntry.target_lang == target_lang)
         .delete(synchronize_session=False))
        db.session.commit()
    return append_term(entries, default_category, source_lang, target_lang)


def lookup_term(term: str, source_lang: str = 'en', target_lang: str = 'ja') -> str | None:
    """Return the target translation for a single source term, or None."""
    key = normalize_key(term)
    if not key:
        return None
    row = db.session.execute(
        select(TermEntry.target_text)
        .where(TermEntry.source_lang == source_lang)
        .where(TermEntry.target_lang == target_lang)
        .where(TermEntry.source_key == key)
    ).first()
    return row[0] if row else None


def lookup_term_batch(terms: Iterable[str], source_lang: str = 'en',
                      target_lang: str = 'ja') -> dict[str, str | None]:
    """Look up several terms at once. Returns a map keyed by the *original*
    input terms; an unknown term maps to None. One query for the whole batch."""
    originals = list(terms)
    keys = {normalize_key(t): t for t in originals if normalize_key(t)}
    found: dict[str, str] = {}
    if keys:
        rows = db.session.execute(
            select(TermEntry.source_key, TermEntry.target_text)
            .where(TermEntry.source_lang == source_lang)
            .where(TermEntry.target_lang == target_lang)
            .where(TermEntry.source_key.in_(list(keys.keys())))
        ).all()
        found = {row[0]: row[1] for row in rows}
    return {t: found.get(normalize_key(t)) for t in originals}


def get_term(term: str, source_lang: str = 'en', target_lang: str = 'ja') -> TermEntry | None:
    key = normalize_key(term)
    if not key:
        return None
    return (db.session.query(TermEntry)
            .filter(TermEntry.source_lang == source_lang)
            .filter(TermEntry.target_lang == target_lang)
            .filter(TermEntry.source_key == key)
            .first())


def list_term(source_lang: str = 'en', target_lang: str = 'ja',
              category: str | None = None, search: str | None = None,
              page: int = 1, limit: int = 50) -> dict[str, Any]:
    """Paginated listing of term entries with optional category/search."""
    query = (db.session.query(TermEntry)
             .filter(TermEntry.source_lang == source_lang)
             .filter(TermEntry.target_lang == target_lang))
    if category:
        query = query.filter(TermEntry.category == category)
    if search:
        like = f"%{normalize_key(search)}%"
        query = query.filter(TermEntry.source_key.ilike(like))

    total = query.count()
    page = max(1, page)
    limit = min(max(1, limit), 200)
    items = (query.order_by(TermEntry.source_key)
             .offset((page - 1) * limit).limit(limit).all())
    return {
        'results': [dict(item) for item in items],
        'count': total,
        'more': page * limit < total,
    }


def count_term(source_lang: str | None = None, target_lang: str | None = None) -> int:
    query = db.session.query(TermEntry)
    if source_lang:
        query = query.filter(TermEntry.source_lang == source_lang)
    if target_lang:
        query = query.filter(TermEntry.target_lang == target_lang)
    return query.count()


def delete_term(term: str, source_lang: str = 'en', target_lang: str = 'ja') -> bool:
    item = get_term(term, source_lang, target_lang)
    if not item:
        return False
    db.session.delete(item)
    db.session.commit()
    return True


# ======================================================================
# Passage translation memory (long-form description text)
# ======================================================================

def passage_hash(text: str) -> str:
    """Lookup key for a passage: SHA-256 (hex) of its normalized form. Two
    passages differing only in case/whitespace collapse to the same key; any
    other change yields a different key (a miss)."""
    return hashlib.sha256(normalize_key(text).encode('utf-8')).hexdigest()


def _coerce_passages(entries: Iterable[dict], default_entity: str | None,
                     default_category: str | None,
                     source_lang: str, target_lang: str) -> list[dict]:
    """Validate and shape raw passage dicts into rows ready for bulk upsert.

    Each entry needs a non-empty `source` and `target`. The translation must
    preserve the source's VNDB markup tokens exactly (links / formatting tags /
    bare id references) — a translation that dropped, added or translated one is
    rejected, since storing it would corrupt the rendered description. Duplicate
    source hashes within the batch are de-duplicated (last wins)."""
    rows: dict[tuple, dict] = {}
    for entry in entries:
        source = (entry.get('source') or '').strip()
        target = (entry.get('target') or '').strip()
        if not source or not target:
            raise ValidationError("Each passage needs a non-empty 'source' and 'target'.")
        ok, why = markup.validate_markup_preserved(source, target)
        if not ok:
            raise ValidationError(
                f"Translation does not preserve the source markup ({why}). "
                f"Source starts: {source[:60]!r}")
        s_lang = (entry.get('source_lang') or source_lang).strip()
        t_lang = (entry.get('target_lang') or target_lang).strip()
        h = passage_hash(source)
        rows[(s_lang, t_lang, h)] = {
            'source_lang': s_lang,
            'target_lang': t_lang,
            'source_hash': h,
            'source_text': source,
            'target_text': target,
            'entity_type': entry.get('entity_type') or default_entity,
            'category': entry.get('category') or default_category,
        }
    return list(rows.values())


def append_passage(entries: Iterable[dict], default_entity: str | None = None,
                   default_category: str | None = None,
                   source_lang: str = 'en', target_lang: str = 'ja') -> int:
    """Insert or update passage translations (append/merge semantics). Conflicts
    on (source_lang, target_lang, source_hash) update the translation in place.
    Returns the number of rows submitted."""
    rows = _coerce_passages(entries, default_entity, default_category,
                            source_lang, target_lang)
    if not rows:
        return 0

    stmt = pg_insert(PassageEntry).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint='uq_passage_langs_hash',
        set_={
            'source_text': stmt.excluded.source_text,
            'target_text': stmt.excluded.target_text,
            'entity_type': stmt.excluded.entity_type,
            'category': stmt.excluded.category,
            'updated_at': func.now(),
        },
    )
    db.session.execute(stmt)
    db.session.commit()
    return len(rows)


def init_passage(entries: Iterable[dict], default_entity: str | None = None,
                 default_category: str | None = None,
                 source_lang: str = 'en', target_lang: str = 'ja',
                 replace: bool = False) -> int:
    """Initialize the passage memory from a batch. With `replace=True` the rows
    for this (source_lang, target_lang) pair are cleared first."""
    if replace:
        (db.session.query(PassageEntry)
         .filter(PassageEntry.source_lang == source_lang)
         .filter(PassageEntry.target_lang == target_lang)
         .delete(synchronize_session=False))
        db.session.commit()
    return append_passage(entries, default_entity, default_category,
                           source_lang, target_lang)


def lookup_passage(text: str, source_lang: str = 'en',
                   target_lang: str = 'ja') -> str | None:
    """Return the stored translation for one passage, or None."""
    if not (text or '').strip():
        return None
    h = passage_hash(text)
    row = db.session.execute(
        select(PassageEntry.target_text)
        .where(PassageEntry.source_lang == source_lang)
        .where(PassageEntry.target_lang == target_lang)
        .where(PassageEntry.source_hash == h)
    ).first()
    return row[0] if row else None


def lookup_passage_batch(texts: Iterable[str], source_lang: str = 'en',
                         target_lang: str = 'ja') -> dict[str, str | None]:
    """Look up several passages at once. Returns a map keyed by the *original*
    input strings; an unknown passage maps to None. One query for the batch."""
    originals = list(texts)
    by_hash = {passage_hash(t): t for t in originals if (t or '').strip()}
    found: dict[str, str] = {}
    if by_hash:
        rows = db.session.execute(
            select(PassageEntry.source_hash, PassageEntry.target_text)
            .where(PassageEntry.source_lang == source_lang)
            .where(PassageEntry.target_lang == target_lang)
            .where(PassageEntry.source_hash.in_(list(by_hash.keys())))
        ).all()
        found = {row[0]: row[1] for row in rows}
    return {t: (found.get(passage_hash(t)) if (t or '').strip() else None)
            for t in originals}


def list_passage(source_lang: str = 'en', target_lang: str = 'ja',
                 entity_type: str | None = None, search: str | None = None,
                 page: int = 1, limit: int = 50) -> dict[str, Any]:
    """Paginated listing of passages with optional entity_type/search (search
    matches the source text)."""
    query = (db.session.query(PassageEntry)
             .filter(PassageEntry.source_lang == source_lang)
             .filter(PassageEntry.target_lang == target_lang))
    if entity_type:
        query = query.filter(PassageEntry.entity_type == entity_type)
    if search:
        query = query.filter(PassageEntry.source_text.ilike(f"%{search}%"))

    total = query.count()
    page = max(1, page)
    limit = min(max(1, limit), 200)
    items = (query.order_by(PassageEntry.id)
             .offset((page - 1) * limit).limit(limit).all())
    return {
        'results': [dict(item) for item in items],
        'count': total,
        'more': page * limit < total,
    }


def count_passage(source_lang: str | None = None,
                  target_lang: str | None = None) -> int:
    query = db.session.query(PassageEntry)
    if source_lang:
        query = query.filter(PassageEntry.source_lang == source_lang)
    if target_lang:
        query = query.filter(PassageEntry.target_lang == target_lang)
    return query.count()


def get_passage(source_hash: str, source_lang: str = 'en',
                target_lang: str = 'ja') -> PassageEntry | None:
    """One passage addressed by its source hash, or None."""
    return (db.session.query(PassageEntry)
            .filter(PassageEntry.source_lang == source_lang)
            .filter(PassageEntry.target_lang == target_lang)
            .filter(PassageEntry.source_hash == source_hash)
            .first())


def delete_passage(source_hash: str, source_lang: str = 'en',
                   target_lang: str = 'ja') -> bool:
    item = get_passage(source_hash, source_lang, target_lang)
    if not item:
        return False
    db.session.delete(item)
    db.session.commit()
    return True

