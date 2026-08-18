"""Freshness policy for the `both` search mode.

The both mode treats local data as a first-class answer, not merely a
fallback: a locally-stored row is served when it is judged fresh enough for
its intrinsic rate of change. Two independent gates are involved:

- freshness (this module): how old may this row get, given what it is?
  A finished VN from 2008 barely changes; an in-development VN changes weekly.
- coverage (in search.py): can the local DB answer this *query* completely?
  Freshness of individual rows never compensates for rows that were simply
  never crawled.

Manually edited rows (edited_at set) are pinned: they are always considered
fresh and are never auto-refreshed, because an automatic overwrite would
destroy the user's edits. They re-enter the cycle when explicitly refreshed
(update_resource_task clears edited_at).

The Kana API exposes no per-entity modification time, so a conditional
"changed since?" probe is impossible — TTL heuristics on devstatus /
released / crawled_at are the only available signal.
"""

import re
from datetime import datetime, timezone, timedelta

# How long a crawled row stays fresh, by how volatile the entity is.
TTL_SHORT = timedelta(days=1)    # actively changing (in development, just released)
TTL_MID = timedelta(days=7)      # settling (released within the last year)
TTL_LONG = timedelta(days=30)    # stable catalogue data
TTL_STATIC = timedelta(days=90)  # near-static reference data (tags, traits)

# Volatility windows on the release date.
RECENT_WINDOW = timedelta(days=90)
YEAR_WINDOW = timedelta(days=365)

# A stale row may still be served (with a background refresh kicked off) until
# its age exceeds TTL × this multiplier; beyond that the caller should block
# on a remote fetch instead of showing hopelessly outdated data.
STALE_SERVE_MULTIPLIER = 6

DEVSTATUS_IN_DEVELOPMENT = 1


def _parse_released(value) -> datetime | None:
    """Parse the locally stored release date (YYYY[-MM[-DD]]). 'TBA', partial
    junk, and None all map to None — treated as unknown/future, i.e. volatile."""
    if not value:
        return None
    match = re.match(r'^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?', str(value))
    if not match:
        return None
    year, month, day = (int(g) if g else 1 for g in match.groups())
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def freshness_ttl(resource_type: str, row) -> timedelta:
    """TTL for a row, derived from its intrinsic change-rate signals."""
    now = datetime.now(timezone.utc)

    if resource_type == 'vn':
        if getattr(row, 'devstatus', None) == DEVSTATUS_IN_DEVELOPMENT:
            return TTL_SHORT
        released = _parse_released(getattr(row, 'released', None))
        if released is None or released > now - RECENT_WINDOW:
            return TTL_SHORT
        if released > now - YEAR_WINDOW:
            return TTL_MID
        return TTL_LONG

    if resource_type == 'release':
        released = _parse_released(getattr(row, 'released', None))
        if released is None or released > now - RECENT_WINDOW:
            return TTL_SHORT
        if released > now - YEAR_WINDOW:
            return TTL_MID
        return TTL_LONG

    if resource_type in ('tag', 'trait'):
        return TTL_STATIC

    # character / producer / staff: essentially append-only reference data
    return TTL_LONG


def _age(row) -> timedelta | None:
    last_crawl = getattr(row, 'crawled_at', None) or getattr(row, 'updated_at', None)
    if last_crawl is None:
        return None
    return datetime.now(timezone.utc) - last_crawl


def is_fresh(resource_type: str, row) -> bool:
    """Row can be served as-is, no refresh needed."""
    if row is None or row.deleted_at is not None:
        return False
    if row.edited_at is not None:
        return True  # pinned: manual edits are never auto-refreshed
    age = _age(row)
    return age is not None and age <= freshness_ttl(resource_type, row)


def is_servable_stale(resource_type: str, row) -> bool:
    """Row is stale but tolerable: serve it now, refresh in the background
    (stale-while-revalidate). Beyond this window, block on remote instead."""
    if row is None or row.deleted_at is not None:
        return False
    age = _age(row)
    return age is not None and age <= freshness_ttl(resource_type, row) * STALE_SERVE_MULTIPLIER
