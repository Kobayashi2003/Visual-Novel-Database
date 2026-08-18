# Backend API

One OpenAPI 3.1 document per service. The specs are the contract; this file only
says how to read them.

## Browsing

Open **`/vndb/docs`** on the running stack. `index.html` renders
these specs and can send requests to the live services. It is served from this
directory, so it always shows the checked-in version with nothing to rebuild
after an edit.

It sits behind the same `forward_auth` gate as everything else, which is what
makes "try it" real: the request carries your session.

> The gate covers the whole directory, so once the access token expires a direct
> visit returns a raw `401` with no way to re-authenticate from that URL. Load
> the site once to refresh, then reopen.

`js-yaml.min.js` is vendored (MIT, see `js-yaml.LICENSE`) rather than pulled from
a CDN.

| Service | Prefix | Spec |
| --- | --- | --- |
| vndbserve | `/vndbserve` | [vndbserve.yaml](vndbserve.yaml) |
| imgserve | `/imgserve` | [imgserve.yaml](imgserve.yaml) |
| userserve | `/userserve` | [userserve.yaml](userserve.yaml) |
| transserve | `/transserve` | [transserve.yaml](transserve.yaml) |
| musicserve | `/musicserve` | [musicserve.yaml](musicserve.yaml) |

> The API carries **no stability guarantee** — there is no versioning and no
> backward-compatibility promise.
