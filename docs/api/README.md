# Backend API

Five services sit behind one Caddy edge on `:30709`, each on its own path prefix.
This directory holds one OpenAPI 3.1 document per service.

## Browsing them

Open **`/visual-novel-database/docs`** on the running stack. `index.html` here renders these specs and
can send requests to the live services — it is served from this directory, so it
always shows the checked-in version, with nothing to rebuild after an edit.

It sits behind the same `forward_auth` gate as everything else, which is what
makes "try it" real: the request carries your session, and a route outside a
prefix's allowlist answers `403` exactly as it would for the frontend.

> The gate is on the *whole* directory, so after the access token expires
> (30 minutes) a direct visit returns a raw `401` with no way to
> re-authenticate from that URL. Load the site once to refresh, then reopen.

`js-yaml.min.js` is vendored (MIT, see `js-yaml.LICENSE`) rather than pulled from
a CDN — the same reason this project mirrors images instead of hotlinking them.

| Service | Prefix | Spec | Status |
| --- | --- | --- | --- |
| transserve | `/transserve` | [transserve.yaml](transserve.yaml) | ✅ normalized |
| musicserve | `/musicserve` | [musicserve.yaml](musicserve.yaml) | ✅ normalized |
| imgserve | `/imgserve` | [imgserve.yaml](imgserve.yaml) | ✅ normalized |
| userserve | `/userserve` | [userserve.yaml](userserve.yaml) | ✅ normalized |
| vndb | `/vndb` | [vndb.yaml](vndb.yaml) | ✅ normalized |

> The API is documented well enough to integrate against without reading the
> source, but it carries **no stability guarantee** — there is no versioning and
> no backward-compatibility promise.

## Conventions

Everything below applies to every service. Per-service specs describe only what
is specific to them.

### Authentication

Caddy gates every backend prefix with `forward_auth` against
`userserve /auth/verify`. A request without a valid session cookie is rejected
at the edge with **401** and never reaches the service. Each prefix also exposes
an explicit allowlist; anything outside it is answered **403** without being
forwarded. Services therefore contain no authentication code.

**Identity** travels only where a service needs it. The probe answers with
`X-User-Id` and `X-Is-Admin`, and the edge copies them upstream after stripping
whatever the client sent under those names — so a service can gate an
administrator-only route by reading a header without authenticating anything
itself. Today only musicserve does: its soundtrack upload is the single write
route exposed at the edge, and it answers **403** to a non-administrator.

### Status is carried by the HTTP status code

Success and failure are expressed by the status code alone. Responses do **not**
carry a `status` field — a second source of truth would inevitably drift from
the first.

| Situation | Code |
| --- | --- |
| Success | `200`, or `201` when something was created |
| Accepted for async processing | `202` with `{"task_id": "..."}` |
| Malformed parameter or body | `400` |
| Not signed in | `401` (edge) |
| Path not exposed by the edge | `403` (edge) |
| A single resource does not exist | `404` |
| Method not allowed on this path | `405` |
| Not implemented | `501` |
| Temporarily disabled | `503` |

A **list query that matches nothing is a success**, not an error: it returns
`200` with an empty `results` array. `404` is reserved for a lookup of one named
resource that does not exist.

A soft-deleted row is reported as `404`, not `410` — `410` would leak the fact
that the id once existed.

### Errors

```json
{ "error": "not_found", "message": "No term for: Maid" }
```

- `error` — a snake_case machine code. **Part of the contract**; each spec lists
  the codes its endpoints can return.
- `message` — for humans. **Not stable**, never parse it.

Shared vocabulary, available in every service:

| Code | Status | Meaning |
| --- | --- | --- |
| `invalid_request` | 400 | Malformed parameter or request body |
| `unauthorized` | 401 | No valid session |
| `forbidden` | 403 | Path not exposed by the edge |
| `not_found` | 404 | The named resource does not exist |
| `method_not_allowed` | 405 | Wrong HTTP method for this path |
| `conflict` | 409 | The request collides with existing state |
| `payload_too_large` | 413 | Body exceeds the accepted size |
| `unsupported_media_type` | 415 | Body is not in an accepted format |
| `rate_limited` | 429 | Too many requests |
| `internal_error` | 500 | Unhandled server-side failure |
| `not_implemented` | 501 | Endpoint reserved but not built |
| `unavailable` | 503 | Temporarily disabled |

Each service keeps its own copy of this table in `errors.py` — the backend has
no shared package, deliberately (services import nothing from one another).
Consistency is maintained by this document, not by shared code.

Services add their own codes on top (for example userserve's
`invalid_credentials`); those are documented in the service's own spec.

### Pagination

```json
{ "results": [ ... ], "count": 1042, "more": true }
```

| Field | Meaning |
| --- | --- |
| `results` | The page, always an array |
| `count` | Total matching rows, ignoring pagination |
| `more` | Whether another page follows |

Requested `page` and `limit` are **not** echoed back — the caller already knows
what it asked for. `page` is 1-based; out-of-range values are clamped rather
than rejected.

### Diagnostics

Fields describing *how* a response was produced — rather than the data itself —
live under `meta`, so they can never collide with the payload:

```json
{ "results": [ ... ], "count": 42, "more": false,
  "meta": { "source": "local", "refreshing": true } }
```

`meta` is optional and appears only when a service has something to report.

### Field naming

`results`, `count` and `more` mirror the [VNDB Kana API](https://api.vndb.org/kana),
which the vndb service proxies. Keeping the names identical is deliberate: it
lets a caller move between this API and the upstream one without a translation
layer. Local additions go under `meta` for the same reason — so an upstream
field added later can never clash with one of ours.
