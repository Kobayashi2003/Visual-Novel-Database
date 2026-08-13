"""HTTP status → machine-readable error code.

Kept dependency-free so both the app factory and the routes can import it
without a cycle. Each service carries its own copy; see docs/api/README.md for
the shared vocabulary these codes come from.
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
