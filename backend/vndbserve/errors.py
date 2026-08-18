"""This service's error-code vocabulary: HTTP status → machine-readable code.

The counterpart of the shared table in docs/api/README.md. Each service keeps
its own copy — the backend has no shared package, deliberately — so a change
here belongs in every copy and in that document.

The mapping is spelled out rather than derived from Werkzeug's status names
because 5 of the 12 codes deliberately differ from them: `bad_request` →
`invalid_request`, `request_entity_too_large` → `payload_too_large`,
`too_many_requests` → `rate_limited`, `internal_server_error` →
`internal_error`, `service_unavailable` → `unavailable`.

Imports nothing, so the app factory can pick it up at module level without
tripping the package's own import cycle.
"""

HTTP_ERROR_CODES = {
    400: 'invalid_request',
    401: 'unauthorized',
    403: 'forbidden',
    404: 'not_found',
    405: 'method_not_allowed',
    409: 'conflict',
    413: 'payload_too_large',
    415: 'unsupported_media_type',
    429: 'rate_limited',
    500: 'internal_error',
    501: 'not_implemented',
    503: 'unavailable',
}


def http_error_code(status: int | None) -> str:
    return HTTP_ERROR_CODES.get(status or 500, 'internal_error')
