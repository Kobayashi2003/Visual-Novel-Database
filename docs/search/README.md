# Search

`backend/vndbserve/search` answers a query from the local mirror, from the VNDB Kana
API, or from both. This file covers the changes that come up most often, and the
capability gaps between the two sides.

## Modes

`GET /v…` picks a mode from `?from=`, or from the operator-set `QUERY_MODE`
(`default` · `local` · `remote` · `disabled` → 503).

| Mode | Behaviour |
| --- | --- |
| `local` | the mirror only |
| `remote` | Kana only |
| `both` | the default — per-query choice, below |

`both` sorts a query into one of four classes:

1. **Lookup by id** — serve the local row while it is fresh; serve it and queue a
   background refresh while it is merely stale; block on Kana once it is older
   than that. If Kana is unreachable and a row exists, serve it as `local-stale`.
2. **A list embedded in its parent** — the releases or characters of one VN come
   out of that VN row's own JSONB, gated on the VN's freshness.
3. **A fully mirrored type** — `tag` and `trait` go local-first.
4. **Everything else** — Kana first, because the mirror cannot prove it holds
   every match for an arbitrary filter. A local fallback is marked
   `local-partial`.

Freshness lives in `search/both/policy.py`: a TTL per entity by how fast that
kind of entity changes, `edited_at` pinning a hand-edited row, and a serve
window of six TTLs before a read blocks on Kana.

## Caching

Two independent systems. They do not know about each other.

| | What | How long |
| --- | --- | --- |
| Response cache | `search_cache` and the `get_*_cache` / `*_by_*_cache` wrappers, Flask-Caching on Redis DB 0 | 1 hour |
| Task cache | `@task_with_memoize` on the search tasks | 10 minutes |
| Freshness | `crawled_at` per row, judged by `policy.py` | 1 to 90 days |

A crawl job must see live data, so `schedule/fetch.py` imports
`search.remote.search.search` directly instead of the memoized `search_remote`.
Anything else that needs upstream truth should do the same.

Note that a background refresh currently reads through the response cache, so a
refresh started inside that hour writes back the cached payload and still stamps
`crawled_at`.

## What only the local side can do

- **`ero=false`** — excludes adult content by combining the tag category with the
  `sexual` and `violence` scores on the cover and screenshots. Kana has no
  equivalent filter.
- **`*_exclude_lies` tag and trait variants** — drop applications flagged as
  lies. Kana's tag filter takes `[id, max_spoiler, min_level]` and never exposes
  that flag.
- **Sorting by `average`, `length_minutes`, `length_votes`, `created_at`,
  `updated_at`** — Kana sorts by `searchrank` instead, which the mirror has no
  column for.
- **Soft delete and manual edits** — `deleted_at`, `edited_at` and the trash
  verbs exist only here.

## What only the remote side can do

Four VN filters raise `ValueError` locally, because the mirror holds none of the
data behind them:

| Filter | Missing locally |
| --- | --- |
| `has_anime`, `anime_id` | anime relations are not mirrored |
| `has_review` | reviews are not mirrored |
| `label` | user-list labels are out of scope |

Sorting by `searchrank` is remote-only for the same reason.

## What is not mirrored

Every field named in `remote/fields.py` has a local column, so nothing that is
fetched is discarded. The gaps are whole subjects rather than individual fields:
anime relations, reviews, and anything belonging to a user's own lists.

The authority on what Kana offers is its `/schema` endpoint; check there before
concluding a field is unavailable rather than merely unrequested.

## Kana added a field — how do I take it

Six places, in this order. Skipping the migration is the usual mistake:
`convert_remote_to_local` drops any field the local schema has no column for, so
the value is fetched and thrown away.

1. **`search/remote/fields.py`** — add the name to the right `_fields` list. Use
   the nested `FieldGroup` when it belongs to a sub-object; `_prefix` builds the
   dotted path the API wants (`image.url`). `large` picks it up on its own,
   because `FIELDS_<TYPE>` is `.ALL`.
2. **`database/models.py`** — add the column. Anything array- or object-shaped
   goes in as `JSONB`.
3. **A migration** — `pixi run migrate -- migrate vndbserve`, then review what it
   generated and `pixi run migrate -- upgrade vndbserve`.
4. **`search/common.py`** — only if the field needs reshaping on the way in, or
   is relation-only and should be dropped. Everything else passes through.
5. **`search/remote/fields.py` and `search/local/fields.py`** — add it to
   `SMALL_FIELDS_<TYPE>` and `SMALL_<TYPE>` if a card should see it.
6. **`search/*/filters.py`** — add it to `get_<type>_filters` on both sides if it
   should be searchable.

## The frontend wants a different `small` set

`small` is defined twice and both must move together, or the two sources hand
back different shapes for the same query:

- `search/remote/fields.py` → `SMALL_FIELDS_<TYPE>`
- `search/local/fields.py` → `SMALL_<TYPE>`

A field can only join `small` if it already has a local column — otherwise the
local side cannot produce it and only `large` would carry it.

Then check the frontend: `lib/types.ts` describes these shapes by hand, and
`lib/api.ts`'s `processVNImages` reads `vn.characters` and `vn.screenshots`
without guarding, so dropping either from a VN response breaks the client.
