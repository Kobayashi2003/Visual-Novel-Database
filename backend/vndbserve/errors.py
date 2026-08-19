"""This service's error vocabulary: the three kinds, and their codes.

An error is classified by who resolves it — the caller (`Rejected`), us
(`Failed`), or time (`Unavailable`) — and that classification settles its
status, whether retrying helps, and whether it is logged with a traceback.
The code travels as data on the exception; `error_status` is the one place a
code becomes an HTTP status.

The counterpart of the shared table in docs/api/README.md. Each service keeps
its own copy — the backend has no shared package, deliberately — so a change
here belongs in every copy and in that document.

The status→code mapping is spelled out rather than derived from Werkzeug's status names
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
    503: 'unavailable',
}


def http_error_code(status: int | None) -> str:
    return HTTP_ERROR_CODES.get(status or 500, 'internal_error')


class ServiceError(Exception):
    """Base for the three kinds; never raised directly.

    `code` is stable and is what a caller branches on; `message` is human and
    free to change; `context` is for the log alone and never reaches a client.
    """

    kind = 'failed'

    def __init__(self, code: str, message: str, context: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}


class Rejected(ServiceError):
    """The caller resolves it by changing the request."""

    kind = 'rejected'


class Failed(ServiceError):
    """We resolve it by fixing code."""

    kind = 'failed'


class Unavailable(ServiceError):
    """Time resolves it — a dependency is down."""

    kind = 'unavailable'


KIND_STATUS = {
    'rejected': 400,
    'failed': 500,
    'unavailable': 503,
}

ERROR_CODE_STATUS = {code: status for status, code in HTTP_ERROR_CODES.items()}


def error_status(kind: str, code: str) -> int:
    """The status an error becomes at the boundary.

    A code that names a status of its own decides it — `not_found` is Rejected
    yet must be 404, not 400. Otherwise the kind's own status stands.
    """
    return ERROR_CODE_STATUS.get(code) or KIND_STATUS.get(kind, 500)
