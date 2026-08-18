# Handling success

Report a completed operation with one of these codes; the route converts it into
the status.

| Code | Status | Reported when |
| --- | --- | --- |
| `ok` | 200 | the answer is in the body |
| `created` | 201 | the operation brought a new resource into being |
| `accepted` | 202 | the work was queued and has not run yet |

- Report a query that matched nothing as `ok` with an empty collection.
