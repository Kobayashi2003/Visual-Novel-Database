# Errors

## 1. Kinds

Classify an error by who resolves it, and let that classification settle
everything else about it:

| Kind | Resolved by | Status | Retry | Log |
| --- | --- | --- | --- | --- |
| **Rejected** | the caller, by changing the request | 4xx | only after a change | no |
| **Failed** | us, by fixing code | 500 | never | with its traceback |
| **Unavailable** | time — a dependency is down | 503 | worth it | without alarm |

- Classify at the point the error is raised.
- Do not report retryability separately; the kind already states it.

## 2. Success or error

Count a completed operation with a definite answer as a success, however empty
that answer is. Rule the cases where "definite" is easy to misjudge like this:

- **No answer exists** — a lookup of one named resource that is absent. Reject it
  with `404`, never `410`; `410` would leak that the id once existed.
- **The answer is already so** — a delete of something already gone. Count it a
  success.
- **The answer cannot be so** — a create of something that already exists. Reject
  it with `409`.
- **There are many answers** — a batch. Put the per-item outcomes in the body of
  a `200`, and raise only when the batch cannot start at all.

## 3. Representation

- Raise when no intermediate caller can act on the error; return a value when the
  immediate caller must branch on it.
- Give an exception a stable `code`, a human `message`, and optional `context`
  for the log alone. Keep HTTP off it; map each code to its status in one place
  at the boundary.
- Define one exception type per kind — `Rejected`, `Failed`, `Unavailable` — and
  let the code travel as data.
- Never report a failure in a way that loses its kind — not with `None`, not with
  a bare boolean, not with a sentinel, not with an uncoded built-in exception.
- Return `None` only from a single-value lookup, to say the value is absent.
  Absence is a value; whoever knows the request's intent turns it into
  `not_found` where that is warranted.

## 4. Propagation

- Catch only to resolve the error, to add context that only this layer has, or to
  translate it at a boundary you own. Otherwise let it pass.
- Never catch broadly outside a boundary.
- Translate a foreign exception — a driver, an HTTP client — into one of the
  three kinds where you call it. Anything that escapes unclassified can only
  become `Failed`, which reports a dependency outage as a defect of ours.
- Attach context on the way up; never rewrite the message.
- Change representation only where an exception cannot cross — a queue, or HTTP —
  and change it once, carrying the kind, code and message across as a value.
- Log with its traceback before converting an error to a value; the value cannot
  carry one.
- Give each entry point exactly one final handler, and let nothing leave it
  unclassified.

## 5. Contract with the caller

- Promise the status code and `error`, and nothing else. Leave `message` free to
  change; a caller must never work out what happened by reading its text.
- Name a code after what the caller must fix.
- Reuse an existing code wherever it names the same condition; add one only when
  none does. Several codes may share one status.
- Return one error per response.
- Take the base codes from here; declare a service's subdivisions in its spec.

| Status | Base code |
| --- | --- |
| 400 | `invalid_request` |
| 401 | `unauthorized` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 405 | `method_not_allowed` |
| 409 | `conflict` |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 503 | `unavailable` |

## 6. In a queued task

- Retry `Unavailable` only.
- Make a task idempotent before allowing it to be retried.
