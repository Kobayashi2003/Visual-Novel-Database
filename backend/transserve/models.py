from typing import Union

from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func

from transserve import db


class TermEntry(db.Model):
    """A single source-term → target-term translation pair.

    The term base is intentionally generic (any `source_lang` → `target_lang`
    pair), but is seeded for English → Japanese and currently used to translate
    VNDB tag / trait names. Lookups are case/space-insensitive: every entry
    stores a normalized `source_key` (lower-cased, whitespace-collapsed) which
    is what queries and the uniqueness constraint key on, while `source_text`
    keeps the original display form.
    """

    __tablename__ = 'terms'

    id = Column(Integer, primary_key=True)
    source_lang = Column(String(8), nullable=False, default='en')
    target_lang = Column(String(8), nullable=False, default='ja')
    source_text = Column(String(512), nullable=False)   # original/display form
    source_key = Column(String(512), nullable=False)    # normalized lookup key
    target_text = Column(Text, nullable=False)          # translation
    # Provenance of the entry: 'tag' | 'trait' | 'general' | ... Lets a later
    # re-seed touch only its own rows and lets clients group results.
    category = Column(String(32), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('source_lang', 'target_lang', 'source_key',
                         name='uq_term_langs_key'),
        Index('ix_term_lookup', 'source_lang', 'target_lang', 'source_key'),
    )

    def __iter__(self):
        yield 'id', self.id
        yield 'source_lang', self.source_lang
        yield 'target_lang', self.target_lang
        yield 'source', self.source_text
        yield 'target', self.target_text
        yield 'category', self.category
        yield 'created_at', self.created_at.isoformat() if self.created_at else None
        yield 'updated_at', self.updated_at.isoformat() if self.updated_at else None

    def __repr__(self):
        return (f"TermEntry(id={self.id!r}, {self.source_lang}->{self.target_lang}, "
                f"source={self.source_text!r}, target={self.target_text!r})")


class PassageEntry(db.Model):
    """A long-form source→target translation: one whole passage of text.

    Where `TermEntry` translates short tag/trait *names*, this is a
    translation memory for *passages* — primarily VNDB `description` text, which
    is long and effectively immutable. Lookups key on a hash of the normalized
    source (the full text is far too long for a `String` index), so a passage is
    matched by its exact content; a tiny edit simply misses (acceptable, since
    descriptions rarely change).

    Crucially, a description carries VNDB markup (``[url=..]``, ``[b]``, bare id
    references like ``g749``…) that must NOT be translated. The translation is
    stored verbatim with that markup preserved; `transserve.markup` validates the
    preservation at write time. See `markup.py` for the token model.
    """

    __tablename__ = 'passages'

    id = Column(Integer, primary_key=True)
    source_lang = Column(String(8), nullable=False, default='en')
    target_lang = Column(String(8), nullable=False, default='ja')
    # SHA-256 (hex) of the normalized source text — the lookup/uniqueness key.
    source_hash = Column(String(64), nullable=False)
    source_text = Column(Text, nullable=False)          # original passage (markup kept)
    target_text = Column(Text, nullable=False)          # translation (markup preserved)
    # Provenance: 'tag' | 'trait' | 'vn' | 'character' | ... Lets a re-seed touch
    # only its own rows and lets callers tag where a passage came from.
    entity_type = Column(String(16), nullable=True)
    category = Column(String(32), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('source_lang', 'target_lang', 'source_hash',
                         name='uq_passage_langs_hash'),
        Index('ix_passage_lookup', 'source_lang', 'target_lang', 'source_hash'),
    )

    def __iter__(self):
        yield 'id', self.id
        yield 'source_hash', self.source_hash
        yield 'source_lang', self.source_lang
        yield 'target_lang', self.target_lang
        yield 'source', self.source_text
        yield 'target', self.target_text
        yield 'entity_type', self.entity_type
        yield 'category', self.category
        yield 'created_at', self.created_at.isoformat() if self.created_at else None
        yield 'updated_at', self.updated_at.isoformat() if self.updated_at else None

    def __repr__(self):
        return (f"PassageEntry(id={self.id!r}, {self.source_lang}->{self.target_lang}, "
                f"hash={self.source_hash[:12]!r}…)")


ModelType = Union[TermEntry, PassageEntry]

MODEL_MAP = {
    'terms': TermEntry,
    'passages': PassageEntry,
}
