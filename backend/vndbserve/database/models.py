"""The tables: the mirrored resources, and the `logs` table logserve reads.

Relation-like data is held in JSONB columns in the API's own shape rather than
in relationships, which is why a row converts to JSON one column at a time (see
common.py) and why the relation columns carry GIN indexes rather than joins.

Every mirrored row carries four stamps that are easy to confuse: `created_at`
and `updated_at` are this row's own history, `crawled_at` is when the data in it
was fetched from the API, and `edited_at` marks a row a person changed by hand —
which is what freezes it against automatic sync. `deleted_at` is the soft
delete. Which write sets which is in operations.py, at `source`.
"""

from typing import Union

from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.sql import func

from vndbserve import db


class VN(db.Model):
    __tablename__ = 'vns'

    id = Column(String, primary_key=True)
    title = Column(String)
    alttitle = Column(String)
    titles = Column(JSONB)
    aliases = Column(ARRAY(String))
    olang = Column(String)
    devstatus = Column(Integer)
    released = Column(String)
    languages = Column(ARRAY(String))
    platforms = Column(ARRAY(String))
    image = Column(JSONB)
    length = Column(Integer)
    length_minutes = Column(Integer)
    length_votes = Column(Integer)
    description = Column(Text)
    average = Column(Float)
    rating = Column(Integer)
    votecount = Column(Integer)
    screenshots = Column(JSONB)
    relations = Column(JSONB)
    tags = Column(JSONB)
    developers = Column(JSONB)
    editions = Column(JSONB)
    staff = Column(JSONB)
    va = Column(JSONB)
    extlinks = Column(JSONB)
    characters = Column(JSONB)
    releases = Column(JSONB)
    publishers = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

class Release(db.Model):
    __tablename__ ='releases'

    id = Column(String, primary_key=True)
    title = Column(String)
    alttitle = Column(String)
    languages = Column(JSONB)
    platforms = Column(ARRAY(String))
    media = Column(JSONB)
    vns = Column(JSONB)
    producers = Column(JSONB)
    images = Column(JSONB)
    released = Column(String)
    minage = Column(Integer)
    patch = Column(Boolean)
    freeware = Column(Boolean)
    uncensored = Column(Boolean)
    official = Column(Boolean)
    has_ero = Column(Boolean)
    resolution = Column(String)
    engine = Column(String)
    voiced = Column(Integer)
    notes = Column(Text)
    gtin = Column(String)
    catalog = Column(String)
    extlinks = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

class Character(db.Model):
    __tablename__ = 'characters'

    id = Column(String, primary_key=True)
    name = Column(String)
    original = Column(String)
    aliases = Column(ARRAY(String))
    description = Column(Text)
    blood_type = Column(String)
    height = Column(Integer)
    weight = Column(Integer)
    bust = Column(Integer)
    waist = Column(Integer)
    hips = Column(Integer)
    cup = Column(String)
    age = Column(Integer)
    birthday = Column(String)
    sex = Column(ARRAY(String))
    gender = Column(ARRAY(String))
    image = Column(JSONB)
    vns = Column(JSONB)
    traits = Column(JSONB)
    seiyuu = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

class Producer(db.Model):
    __tablename__ = 'producers'

    id = Column(String, primary_key=True)
    name = Column(String)
    original = Column(String)
    aliases = Column(ARRAY(String))
    lang = Column(String)
    type = Column(String)
    description = Column(Text)
    extlinks = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

class Staff(db.Model):
    __tablename__ = 'staff'

    id = Column(String, primary_key=True)
    aid = Column(Integer)
    ismain = Column(Boolean)
    name = Column(String)
    original = Column(String)
    lang = Column(String)
    gender = Column(String)
    description = Column(Text)
    extlinks = Column(JSONB)
    aliases = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

class Tag(db.Model):
    __tablename__ = 'tags'

    id = Column(String, primary_key=True)
    name = Column(String)
    aliases = Column(ARRAY(String))
    description = Column(Text)
    category = Column(String)
    searchable = Column(Boolean)
    applicable = Column(Boolean)
    vn_count = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

class Trait(db.Model):
    __tablename__ = 'traits'

    id = Column(String, primary_key=True)
    name = Column(String)
    aliases = Column(ARRAY(String))
    description = Column(Text)
    searchable = Column(Boolean)
    applicable = Column(Boolean)
    sexual = Column(Boolean)
    group_id = Column(String)
    group_name = Column(String)
    char_count = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    crawled_at = Column(DateTime(timezone=True), nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)

# ----------------------------------------
# Variables
# ----------------------------------------

ModelType = Union[VN, Tag, Producer, Staff, Character, Trait, Release]

MODEL_MAP = {
    'vn': VN,
    'tag': Tag,
    'producer': Producer,
    'staff': Staff,
    'character': Character,
    'trait': Trait,
    'release': Release
}


class LogEntry(db.Model):
    __tablename__ = 'logs'

    id = Column(String, primary_key=True)
    # Indexed: every read of this table is by time — logserve lists newest-first
    # and filters on a range, and the retention job selects on it (see
    # schedule/logs.py).
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    level = Column(String)
    message = Column(Text)
    details = Column(JSONB)

    def __repr__(self):
        return f"<LogEntry(id={self.id}, timestamp={self.timestamp}, level={self.level}, message={self.message})>"