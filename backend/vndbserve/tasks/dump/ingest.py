"""Bringing the mirror up to a published dump.

The Kana API cannot say what changed: it returns no ETag, no Last-Modified and
carries no modification time on any entity, so freshness there can only be
guessed from a TTL. A dump can — it is a whole snapshot, and the file carries a
Last-Modified, so it is read only when it has actually been republished.

A snapshot also allows two things a paginated API does not: every row at once,
so coverage no longer depends on how far a crawl got; and ids held locally that
the snapshot omits, which is the only way to notice an entry was deleted
upstream, since through the API a deleted id and one that never existed look
alike.
"""

import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from flask import current_app

from vndbserve.database import create, update, delete, exists, all_ids
from vndbserve.errors import Failed, Unavailable
from vndbserve.logger import logger
from vndbserve.utils.ids import format_id
from vndbserve.utils.state import load_state, save_state
from ..common import task
from ..envelope import format_results
from .archive import cached_archive, read_tables
from .convert import (ARCHIVE_URL, ARCHIVE_SOURCES, SOURCES,
                      ArchiveSource, DumpSource, convert_dump_to_local)

# A snapshot that has lost most of the rows held locally is a truncated
# download, not a mass deletion upstream. Below this share the run is abandoned
# rather than allowed to soft-delete the difference.
MIN_RETAINED = 0.9

# How often a newer archive is pulled. The file is republished daily and is
# hundreds of megabytes, while most of what it holds moves far more slowly.
ARCHIVE_INTERVAL = timedelta(days=3)


def _state_path(resource_type: str) -> str:
    """One file per resource type, because the types are ingested concurrently.

    A shared file would be read-modify-written by three tasks at once and only
    the last writer's entry would survive — the other two would re-ingest a
    whole snapshot every run, which is the one thing the saved timestamp exists
    to prevent.
    """
    return f"{current_app.config['DATA_FOLDER']}/dump_state_{resource_type}.json"


def _archive_dir() -> str:
    return os.path.join(current_app.config['DATA_FOLDER'], 'dumps')


# ─── Fetching ─────────────────────────────────────────────────────────────────

def _published_at(response: httpx.Response) -> datetime | None:
    stamp = response.headers.get('Last-Modified')
    if not stamp:
        return None
    try:
        return parsedate_to_datetime(stamp)
    except (TypeError, ValueError):
        return None


def published_since(url: str, since: str | None) -> datetime | None | bool:
    """When the file at `url` was published, or False when that is `since`.

    Asked before every download: these are republished daily whether or not
    anything in them changed, and re-reading the same bytes costs the whole
    file.
    """
    try:
        head = httpx.head(url, follow_redirects=True, timeout=30)
        head.raise_for_status()
    except httpx.HTTPError as exc:
        raise Unavailable('dump_unreachable',
                          "The VNDB dump could not be reached.",
                          {'url': url, 'cause': repr(exc)}) from exc
    published = _published_at(head)
    if published and since and published.isoformat() == since:
        return False
    return published


def current_archive(state: dict) -> tuple[str, datetime]:
    """The archive on disk, fetching a newer one only every so often.

    One download serves every resource type read out of it, so the file is kept
    rather than streamed per type. And it is replaced on its own cadence rather
    than whenever it is republished: the archive is republished daily, most of
    what it holds moves slowly, and it is hundreds of megabytes.
    """
    entry = state.setdefault('archive', {})
    path, stamp = entry.get('path'), entry.get('published_at')
    if path and stamp and os.path.exists(path):
        published = datetime.fromisoformat(stamp)
        if datetime.now(timezone.utc) - published < ARCHIVE_INTERVAL:
            return path, published

    published = published_since(ARCHIVE_URL, None) or datetime.now(timezone.utc)
    path = cached_archive(_archive_dir(), ARCHIVE_URL, published)
    entry['path'], entry['published_at'] = path, published.isoformat()
    return path, published


def fetch_archive(source: ArchiveSource, since: str | None,
                  state: dict) -> tuple[list, datetime, dict] | None:
    """The archive's rows for one resource type, already indexed for conversion."""
    path, published = current_archive(state)
    if since and published.isoformat() == since:
        return None

    tables = read_tables(path, source.tables)
    context = source.prepare(tables) if source.prepare else {}
    return tables[source.table], published, context


def fetch_dump(source: DumpSource, since: str | None) -> tuple[list, datetime, dict] | None:
    """The dump's records and the time it was published, or None if unchanged.

    The published time is asked for first: a dump republished daily is otherwise
    a download of the same bytes we already hold.
    """
    published = published_since(source.url, since)
    if published is False:
        return None

    try:
        response = httpx.get(source.url, follow_redirects=True, timeout=600)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise Unavailable('dump_unreachable',
                          "The VNDB dump could not be fetched.",
                          {'url': source.url, 'cause': repr(exc)}) from exc

    published = _published_at(response) or published or datetime.now(timezone.utc)
    try:
        records = json.loads(gzip.decompress(response.content))
    except (OSError, json.JSONDecodeError) as exc:
        raise Unavailable('dump_unreadable',
                          "The VNDB dump could not be read.",
                          {'url': source.url, 'cause': repr(exc)}) from exc

    context = source.prepare(records) if source.prepare else {}
    return records, published, context


# ─── Ingest ───────────────────────────────────────────────────────────────────

def ingest(resource_type: str, force: bool = False) -> dict[str, Any]:
    """Bring one resource type up to the published snapshot.

    Rows are dated from the dump's own publication time, not from the clock at
    the moment of writing, so freshness reflects the content rather than the
    ingest.
    """
    source = SOURCES.get(resource_type) or ARCHIVE_SOURCES.get(resource_type)
    if not source:
        raise Failed('internal_error', f"No dump for resource type: {resource_type}")

    state = load_state(_state_path(resource_type))
    since = None if force else state.get(resource_type, {}).get('published_at')

    fetched = (fetch_archive(source, since, state) if isinstance(source, ArchiveSource)
               else fetch_dump(source, since))
    if fetched is None:
        return {'skipped': 'unchanged', 'created': 0, 'updated': 0, 'deleted': 0}
    records, published, context = fetched

    held = all_ids(resource_type)
    incoming = {format_id(resource_type, r['id']) for r in records}
    missing = held - incoming
    if held and len(incoming & held) < len(held) * MIN_RETAINED:
        raise Unavailable(
            'dump_incomplete',
            "The dump holds too few of the rows already stored to be trusted.",
            {'resource_type': resource_type, 'held': len(held), 'incoming': len(incoming)})

    created = updated = skipped = 0
    for record in records:
        id_, fields = convert_dump_to_local(resource_type, record, context)
        if exists(resource_type, id_):
            updated += update(resource_type, id_, fields, crawled_at=published) is not None
        elif source.creates:
            created += create(resource_type, id_, fields, crawled_at=published) is not None
        else:
            skipped += 1

    # Absent from a whole snapshot is the one signal the API cannot give: through
    # it, a deleted id and one that never existed look the same.
    for id_ in missing:
        delete(resource_type, id_)

    state.setdefault(resource_type, {})['published_at'] = published.isoformat()
    save_state(_state_path(resource_type), state)

    logger.info(f"Dump ingest {resource_type}: +{created} ~{updated} -{len(missing)} "
                f"({skipped} left for the crawl) published {published.isoformat()}")
    return {'created': created, 'updated': updated, 'deleted': len(missing),
            'left_to_crawl': skipped, 'published_at': published.isoformat()}


@task(retry=True, invalidates='all')
def ingest_dump_task(resource_type: str, force: bool = False) -> dict[str, Any]:
    return format_results(ingest(resource_type, force))
