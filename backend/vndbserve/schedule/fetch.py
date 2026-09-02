"""Data-fetching schedules for the VNDB resource database.

The VNDB Kana API (https://api.vndb.org/kana) is a paginated list API whose
ids are assigned sequentially, which makes two deterministic strategies
possible:

  fetch_new_schedule      - walk the newest ids (sorted by id, descending) and
                            ingest anything not held locally, stopping as soon
                            as a page is fully known. In steady state this is
                            one cheap request per type per run.

  fetch_backfill_schedule - sweep the whole id space (sorted ascending) a few
                            pages per run, persisting a per-type page cursor so
                            every run continues where the last left off and the
                            historical gaps left by random sampling are filled.

Efficiency notes
----------------
* Batched reads. A page returns 100 entries in one request; ingestion fetches
  a whole batch of ids through a single comma-joined `id` filter (the API
  treats commas as OR) instead of one request per id.
* Live reads. The cached `search_remote` is bypassed on purpose - a fetch job
  must see fresh data, not an hour-old memoized page.
* List-driven. Ids come from the API's own listing, which only contains live
  entries, so deleted/never-assigned ids are never probed or retried.
* Bounded work. Each run is capped (MAX_NEW_PAGES / BACKFILL_PAGES_PER_RUN) so
  a scheduled run never blocks the scheduler thread for long.
* Correct conversion. Remote payloads pass through convert_remote_to_local
  before storage, dropping the relation-only fields the local schema lacks.
"""

import os
import time

from flask import current_app

from .common import crawl_task
from vndbserve import db
from vndbserve.database import MODEL_MAP, create
from vndbserve.logger import logger
from vndbserve.search import convert_remote_to_local
from vndbserve.utils.state import load_state, save_state
# Uncached search: a fetch job needs live results, not memoized ones.
from vndbserve.search.remote.search import search as vndb_search

# Resource types fetched on every run. Add 'release', 'producer', 'staff',
# 'tag' or 'trait' here to widen coverage.
FETCH_TYPES = ['vn', 'character']

PAGE_SIZE = 100             # entries per API page (API maximum)
INGEST_BATCH = 20           # ids per ingest request (keeps the OR filter small)
MAX_NEW_PAGES = 3           # fetch_new: page cap for a cold-start catch-up
BACKFILL_PAGES_PER_RUN = 2  # fetch_backfill: pages swept per run
REQUEST_DELAY = 2           # seconds between API requests
TYPE_DELAY = 5              # seconds between resource types


# ----------------------------------------
# Per-type cursor persistence (fetch_backfill)
# ----------------------------------------

def _state_path():
    return os.path.join(current_app.config['DATA_FOLDER'], 'fetch_state.json')

def _load_state():
    return load_state(_state_path())

def _save_state(state):
    save_state(_state_path(), state)


# ----------------------------------------
# Shared helpers
# ----------------------------------------

def _known_ids(resource_type, ids):
    """Return the subset of `ids` already present locally (any state, including
    soft-deleted) in a single query, so they are never re-fetched."""
    if not ids:
        return set()
    model = MODEL_MAP[resource_type]
    rows = db.session.query(model.id).filter(model.id.in_(ids)).all()
    return {row[0] for row in rows}

def _ingest(resource_type, ids):
    """Fetch full ('large') data for `ids` from VNDB and create them locally.
    Returns the number of rows successfully created."""
    created = 0
    for start in range(0, len(ids), INGEST_BATCH):
        batch = ids[start:start + INGEST_BATCH]
        # A comma-joined id filter fetches the whole batch in one request.
        response = vndb_search(resource_type, {'id': ','.join(batch)}, 'large',
                               page=1, limit=len(batch), count=False)
        for item in response.get('results', []):
            data = convert_remote_to_local(resource_type, item)
            if create(resource_type, item['id'], data) is not None:
                created += 1
        time.sleep(REQUEST_DELAY)
    return created


# ----------------------------------------
# Schedules
# ----------------------------------------

@crawl_task()
def fetch_new_schedule():
    """Ingest entries newer than anything currently held locally."""
    summary = {}
    for resource_type in FETCH_TYPES:
        try:
            summary[resource_type] = _fetch_new(resource_type)
        except Exception:
            logger.exception(f"fetch_new failed for {resource_type}")
        time.sleep(TYPE_DELAY)
    logger.info(f"[VNDB] fetch_new created: {summary}")

def _fetch_new(resource_type):
    created = 0
    for page in range(1, MAX_NEW_PAGES + 1):
        # Newest ids first; the local frontier is wherever a page becomes known.
        response = vndb_search(resource_type, {}, 'small', page=page,
                               limit=PAGE_SIZE, sort='id', reverse=True, count=False)
        page_ids = [item['id'] for item in response.get('results', [])]
        if not page_ids:
            break
        known = _known_ids(resource_type, page_ids)
        new_ids = [i for i in page_ids if i not in known]
        if not new_ids:
            break  # page fully known - nothing newer remains
        created += _ingest(resource_type, new_ids)
        if len(new_ids) < len(page_ids):
            break  # page straddles the known frontier - caught up
        time.sleep(REQUEST_DELAY)
    return created

@crawl_task(minute=30)
def fetch_backfill_schedule():
    """Sweep the full id space to fill historical gaps, a few pages per run."""
    state = _load_state()
    summary = {}
    for resource_type in FETCH_TYPES:
        cursor = state.get(resource_type, {}).get('backfill_page', 1)
        try:
            created, cursor = _fetch_backfill(resource_type, cursor)
            summary[resource_type] = created
        except Exception:
            logger.exception(f"fetch_backfill failed for {resource_type}")
        state.setdefault(resource_type, {})['backfill_page'] = cursor
        # Saved per type rather than once at the end: a run that dies partway
        # would otherwise discard the progress of the types it had finished.
        _save_state(state)
        time.sleep(TYPE_DELAY)
    logger.info(f"[VNDB] fetch_backfill created: {summary}")

def _fetch_backfill(resource_type, page):
    created = 0
    page = max(1, page)
    for _ in range(BACKFILL_PAGES_PER_RUN):
        response = vndb_search(resource_type, {}, 'small', page=page,
                               limit=PAGE_SIZE, sort='id', reverse=False, count=False)
        page_ids = [item['id'] for item in response.get('results', [])]
        if not page_ids:
            page = 1  # cursor ran past the last page - restart the sweep
            break
        known = _known_ids(resource_type, page_ids)
        missing = [i for i in page_ids if i not in known]
        created += _ingest(resource_type, missing)
        if response.get('more'):
            page += 1
        else:
            page = 1  # reached the last page - wrap to the start
            break
        time.sleep(REQUEST_DELAY)
    return created, page
