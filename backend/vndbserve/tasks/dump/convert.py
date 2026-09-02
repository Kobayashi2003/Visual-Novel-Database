"""One dump record as the columns of a local row.

The counterpart of `search.convert_remote_to_local`: a dump is shaped
differently from an API reply, so it needs its own mapping, but both feed the
same `create` and `update`.

A source declares what it can fill. `prepare` exists because some columns are in
no single record — a trait's group is derived from the whole set, a vn's release
date from the releases it belongs to — so a converter may need the set before it
can convert a row of it.
"""

from typing import Any, Callable

from vndbserve.errors import Failed
from vndbserve.utils.ids import format_id

DUMP_BASE = 'https://dl.vndb.org/dump'
ARCHIVE_URL = f'{DUMP_BASE}/vndb-db-latest.tar.zst'


# ─── Conversion ───────────────────────────────────────────────────────────────

def _tag_fields(record: dict[str, Any], context: dict) -> dict[str, Any]:
    return {
        'name': record.get('name'),
        'aliases': record.get('aliases') or [],
        'description': record.get('description'),
        'category': record.get('cat'),
        'searchable': record.get('searchable'),
        'applicable': record.get('applicable'),
        'vn_count': record.get('vns'),
    }


def _trait_context(records: list[dict[str, Any]]) -> dict:
    """Resolve every trait's group once, for the whole set.

    The API states a trait's group directly; the dump states only `parents`, and
    the group is the topmost ancestor of the chain. Walking that chain per row
    would re-walk the same ancestors thousands of times, so it is resolved once
    here — and memoized as it goes, which also bounds a cycle should the data
    ever contain one.
    """
    by_id = {r['id']: r for r in records}
    root: dict[int, int] = {}

    def resolve(tid: int, seen: frozenset) -> int:
        if tid in root:
            return root[tid]
        record = by_id.get(tid)
        parents = (record or {}).get('parents') or []
        if not record or not parents or tid in seen:
            root[tid] = tid
        else:
            root[tid] = resolve(parents[0], seen | {tid})
        return root[tid]

    for record in records:
        resolve(record['id'], frozenset())
    return {'by_id': by_id, 'root': root}


def _trait_fields(record: dict[str, Any], context: dict) -> dict[str, Any]:
    root_id = context['root'][record['id']]
    is_root = root_id == record['id']
    group = context['by_id'].get(root_id) or {}
    return {
        'name': record.get('name'),
        'aliases': record.get('aliases') or [],
        'description': record.get('description'),
        'searchable': record.get('searchable'),
        'applicable': record.get('applicable'),
        'sexual': record.get('sexual'),
        # A group's own row states no group, matching what the API reports.
        'group_id': None if is_root else format_id('trait', root_id),
        'group_name': None if is_root else group.get('name'),
        'char_count': record.get('chars'),
    }


class DumpSource:
    """One published dump, and how its records become local rows.

    `prepare` exists because some columns are not in any single record — a
    trait's group is derived from the whole set — so a converter may need the
    set before it can convert a row of it.
    """

    def __init__(self, resource_type: str, filename: str,
                 fields: Callable[[dict, dict], dict],
                 prepare: Callable[[list], dict] | None = None,
                 creates: bool = True):
        self.resource_type = resource_type
        self.filename = filename
        self.fields = fields
        self.prepare = prepare
        # These dumps carry every column their model has, so a row seen only
        # here is a whole row and may be brought into being from it.
        self.creates = creates

    @property
    def url(self) -> str:
        return f'{DUMP_BASE}/{self.filename}'


SOURCES = {
    'tag': DumpSource('tag', 'vndb-tags-latest.json.gz', _tag_fields),
    'trait': DumpSource('trait', 'vndb-traits-latest.json.gz', _trait_fields,
                        prepare=_trait_context),
}


# ─── The database archive ─────────────────────────────────────────────────────

def _int(value: str | None) -> int | None:
    return None if value in (None, '') else int(value)


def _tenths(value: str | None) -> float | None:
    """A score the dump keeps as tenths of a point."""
    return None if value in (None, '') else _int(value) / 10


def _released(value: str | None) -> str | None:
    """A release date as the API words it.

    The dump keeps it as YYYYMMDD with 99 standing for a part nobody knows, and
    9999 for a date nobody has announced.
    """
    if not value:
        return None
    text = str(value)
    if len(text) != 8:
        return text
    year, month, day = text[:4], text[4:6], text[6:]
    if year == '9999':
        return 'TBA'
    if month == '99':
        return year
    if day == '99':
        return f'{year}-{month}'
    return f'{year}-{month}-{day}'


def _vn_context(tables: dict[str, list[dict[str, Any]]]) -> dict:
    """Gather everything a vn row cannot state about itself.

    A vn states no title, no release date, no platform and no language: those
    live in `vn_titles` and in the releases the vn belongs to. Each is indexed
    once here rather than scanned per vn, which would be a pass over the whole
    release set for every one of sixty-five thousand rows.
    """
    titles: dict[str, list[dict]] = {}
    for row in tables['vn_titles']:
        titles.setdefault(row['id'], []).append(row)

    relations: dict[str, list[dict]] = {}
    for row in tables['vn_relations']:
        relations.setdefault(row['id'], []).append(row)

    editions: dict[str, list[dict]] = {}
    for row in tables['vn_editions']:
        editions.setdefault(row['id'], []).append(row)

    releases = {row['id']: row for row in tables['releases']}
    platforms: dict[str, set[str]] = {}
    for row in tables['releases_platforms']:
        platforms.setdefault(row['id'], set()).add(row['platform'])
    languages: dict[str, set[str]] = {}
    for row in tables['releases_titles']:
        languages.setdefault(row['id'], set()).add(row['lang'])

    of_vn: dict[str, list[dict]] = {}
    for row in tables['releases_vn']:
        of_vn.setdefault(row['vid'], []).append(row)

    return {'titles': titles, 'relations': relations, 'editions': editions,
            'releases': releases, 'platforms': platforms, 'languages': languages,
            'of_vn': of_vn,
            # A related vn's title is stated in *its* original language, not the
            # language of the vn that points at it.
            'olang': {row['id']: row['olang'] for row in tables['vn']}}


def _vn_title(vn_id: str, context: dict, olang: str | None) -> tuple[str | None, str | None]:
    """The romanised title and the original the API keeps beside it."""
    main = next((r for r in context['titles'].get(vn_id, []) if r['lang'] == olang), None)
    if not main:
        return None, None
    return (main.get('latin') or main['title'],
            main['title'] if main.get('latin') else None)


def _vn_fields(record: dict[str, Any], context: dict) -> dict[str, Any]:
    rows = sorted(context['titles'].get(record['id'], []), key=lambda r: r['lang'])
    olang = record.get('olang')
    main = next((r for r in rows if r['lang'] == olang), None)
    return {
        'olang': olang,
        'aliases': [a for a in (record.get('alias') or '').split('\n') if a],
        # 0 is the dump's way of saying nobody has estimated the length.
        'devstatus': _int(record.get('devstatus')),
        'length': _int(record.get('length')) or None,
        'length_minutes': _int(record.get('c_length')),
        'length_votes': _int(record.get('c_lengthnum')),
        'votecount': _int(record.get('c_votecount')),
        'rating': None if record.get('c_rating') in (None, '')
                  else int(_int(record['c_rating']) / 10 + 0.5),
        'average': _tenths(record.get('c_average')),
        'description': record.get('description'),
        # The API states the romanised title where one exists and keeps the
        # original as the alternative, so the pair is reconstructed the same way.
        'title': (main.get('latin') or main['title']) if main else None,
        'alttitle': main['title'] if main and main.get('latin') else None,
        'titles': [{'lang': r['lang'], 'title': r['title'], 'latin': r.get('latin'),
                    'official': r['official'] == 't', 'main': r['lang'] == olang}
                   for r in rows],
        'released': _released(_vn_released(record['id'], context)),
        'platforms': sorted({p for r in context['of_vn'].get(record['id'], [])
                             for p in context['platforms'].get(r['id'], ())}),
        'languages': sorted({l for r in context['of_vn'].get(record['id'], [])
                             for l in context['languages'].get(r['id'], ())}),
        'editions': [{'eid': _int(e['eid']), 'lang': e['lang'], 'name': e['name'],
                      'official': e['official'] == 't'}
                     for e in sorted(context['editions'].get(record['id'], []),
                                     key=lambda e: _int(e['eid']) or 0)],
        'relations': [_vn_relation(r, context)
                      for r in sorted(context['relations'].get(record['id'], []),
                                      key=lambda r: r['vid'])],
    }


def _vn_released(vn_id: str, context: dict) -> str | None:
    """When the vn came out.

    A vn states no date of its own; it is dated by the earliest release that is
    the whole thing, since a trial or a partial one comes out sooner and is not
    what the site reports. Where nothing complete has been released — an
    unfinished work, or one that only ever saw a partial — the earliest of any
    release stands, because reporting nothing would lose a date that is known.
    """
    complete, any_release = [], []
    for row in context['of_vn'].get(vn_id, []):
        release = context['releases'].get(row['id'])
        if not release or not release['released']:
            continue
        any_release.append(release['released'])
        if row['rtype'] == 'complete':
            complete.append(release['released'])
    dates = complete or any_release
    return min(dates) if dates else None


def _vn_relation(row: dict[str, Any], context: dict) -> dict[str, Any]:
    """One related vn, named the way the API names it.

    The relation table states only the other vn's id, so its title is resolved
    the same way the vn's own is — in that vn's original language.
    """
    title, alttitle = _vn_title(row['vid'], context, context['olang'].get(row['vid']))
    return {'id': row['vid'], 'title': title, 'alttitle': alttitle,
            'relation': row['relation'], 'relation_official': row['official'] == 't'}


class ArchiveSource:
    """One resource type read out of the database archive.

    `tables` names everything the conversion needs — the entity's own table plus
    whatever it must be joined against — so the archive is streamed once and
    only for those.

    `creates` says whether a row this source has never seen may be brought into
    being from it. A conversion that fills only part of a model must not: the
    row would exist while missing what a caller expects of it, and an absent row
    is the more honest answer until the crawl fetches a whole one.
    """

    def __init__(self, resource_type: str, table: str, tables: set[str],
                 fields: Callable[[dict, dict], dict],
                 prepare: Callable[[dict], dict] | None = None,
                 creates: bool = False):
        self.resource_type = resource_type
        self.table = table
        self.tables = tables
        self.fields = fields
        self.prepare = prepare
        self.creates = creates


# vn fills 18 of the model's 29 columns. What is still missing — `image`,
# `developers`, `characters`, `releases`, `staff`, `va`, `screenshots`,
# `publishers`, `extlinks`, `tags` — is derivable from the archive too, but is
# not read yet, so this updates the rows the crawl has already made and creates
# none of its own.
ARCHIVE_SOURCES = {
    'vn': ArchiveSource('vn', 'vn',
                       {'vn', 'vn_titles', 'vn_relations', 'vn_editions',
                        'releases', 'releases_vn', 'releases_platforms',
                        'releases_titles'},
                       _vn_fields, _vn_context),
}


def convert_dump_to_local(resource_type: str, record: dict[str, Any],
                          context: dict) -> tuple[str, dict[str, Any]]:
    """One dump record as a local id and its column values."""
    source = SOURCES.get(resource_type) or ARCHIVE_SOURCES.get(resource_type)
    if not source:
        raise Failed('internal_error', f"No dump for resource type: {resource_type}")
    return format_id(resource_type, record['id']), source.fields(record, context)
