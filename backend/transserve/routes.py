"""HTTP surface. Request and response shapes are specified in
docs/api/transserve.yaml — the docstrings here cover only the reasoning that a
schema cannot express."""

import re

from flask import Blueprint, abort, jsonify, request

from .service import TranslationService, TranslationNotImplemented
from .operations import ValidationError
from .errors import http_error_code

api_bp = Blueprint('api', __name__, url_prefix='/')

_TRUE = {'true', '1', 'yes', 'on'}
_FALSE = {'false', '0', 'no', 'off'}

def parse_bool(raw, default: bool) -> bool:
    if raw is None:
        return default
    raw = str(raw).strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default

def parse_int(raw, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        abort(400, description=f"Expected an integer, got: {raw!r}")
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


@api_bp.errorhandler(400)
def bad_request(e):
    return jsonify(error="invalid_request", message=str(e.description)), 400

@api_bp.errorhandler(404)
def not_found(e):
    return jsonify(error="not_found", message="Resource not found."), 404

@api_bp.errorhandler(500)
def server_error(e):
    return jsonify(error="internal_error", message="An unexpected error occurred."), 500

@api_bp.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify(error=e.error_code, message=e.message), e.http_status


_HASH_RE = re.compile(r'^[0-9a-f]{64}$')


def _hash_or_400(raw: str) -> str:
    """A passage is addressed by the hash of its normalized source. Validating
    the shape here keeps `/passage/lookup` and `/passage/init` from being read
    as hashes and 404-ing confusingly."""
    if not _HASH_RE.match(raw or ''):
        abort(400, description="Passage id must be a 64-character lowercase hex hash")
    return raw


def _service():
    """Build a TranslationService for the request, honouring optional
    ?source=/&target= overrides (defaults come from config)."""
    source = request.args.get('source')
    target = request.args.get('target')
    return TranslationService(source_lang=source, target_lang=target)


@api_bp.route('', methods=['GET', 'TRACE'])
def hello_world():
    return jsonify({"message": "TRANSSERVE"})


@api_bp.route('/stats', methods=['GET'])
def stats():
    """How much is stored for this language pair."""
    service = _service()
    return jsonify({
        "terms": service.count_term(),
        "passages": service.count_passage(),
        "source_lang": service.source_lang,
        "target_lang": service.target_lang,
    })


# ----------------------------------------
# Term base — lookup (implemented)
# ----------------------------------------

@api_bp.route('/term/lookup', methods=['POST'])
def term_lookup_batch():
    """`fallback=true` maps an unknown term to itself rather than null, so a
    display caller (the frontend in original-text mode) always has something to
    render. `matched` reports the real hits either way."""
    body = request.get_json(silent=True) or {}
    terms = body.get('terms')
    if not isinstance(terms, list):
        raise ValidationError("Body must include a 'terms' list.")
    fallback = bool(body.get('fallback', False))

    found = _service().lookup_term_batch(terms)  # {term: translation | None}
    matched = {t: found.get(t) is not None for t in terms}
    if fallback:
        results = {t: (found[t] if found.get(t) is not None else t) for t in terms}
    else:
        results = found
    return jsonify({"results": results, "matched": matched})


@api_bp.route('/term/<path:term>', methods=['GET'])
def term_lookup(term):
    """`?fallback=true` returns 200 echoing the source instead of 404, for
    display call sites that always need something to show."""
    service = _service()
    translation = service.lookup_term(term)
    fallback = parse_bool(request.args.get('fallback'), False)
    if translation is None and not fallback:
        return jsonify(error="not_found", message=f"No translation for: {term}"), 404
    return jsonify({
        "source": term,
        "target": translation if translation is not None else term,
        "matched": translation is not None,
        "source_lang": service.source_lang,
        "target_lang": service.target_lang,
    })


@api_bp.route('/term', methods=['GET'])
def term_list():
    return jsonify(_service().list_term(
        category=request.args.get('category'),
        search=request.args.get('search'),
        page=parse_int(request.args.get('page'), 1, 1),
        limit=parse_int(request.args.get('limit'), 50, 1, 200),
    ))


# ----------------------------------------
# Term base — initialization & append
# ----------------------------------------

@api_bp.route('/term/init', methods=['POST'])
def term_init():
    """`replace=true` clears the language pair first."""
    body = request.get_json(silent=True) or {}
    entries = body.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValidationError("Body must include a non-empty 'entries' list.")
    count = _service().init_term(
        entries,
        default_category=body.get('category'),
        replace=bool(body.get('replace', False)),
    )
    return jsonify({"submitted": count}), 201


@api_bp.route('/term', methods=['POST'])
def term_append():
    """Upsert by source text — unlike /term/init this never clears."""
    body = request.get_json(silent=True) or {}
    entries = body.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValidationError("Body must include a non-empty 'entries' list.")
    count = _service().append_term(entries, default_category=body.get('category'))
    return jsonify({"submitted": count}), 201


@api_bp.route('/term/<path:term>', methods=['DELETE'])
def term_delete(term):
    if not _service().delete_term(term):
        return jsonify(error="not_found", message=f"No term for: {term}"), 404
    return jsonify({"deleted": term})


# ----------------------------------------
# Passage translation memory (descriptions)
# ----------------------------------------

@api_bp.route('/passage/lookup', methods=['POST'])
def passage_lookup_batch():
    """`fallback` mirrors /term/lookup. Keys are the source texts you sent, so
    the result maps straight back onto the caller's own data."""
    body = request.get_json(silent=True) or {}
    texts = body.get('texts')
    if not isinstance(texts, list):
        raise ValidationError("Body must include a 'texts' list.")
    fallback = bool(body.get('fallback', False))

    found = _service().lookup_passage_batch(texts)  # {text: translation | None}
    matched = {t: found.get(t) is not None for t in texts}
    if fallback:
        results = {t: (found[t] if found.get(t) is not None else t) for t in texts}
    else:
        results = found
    return jsonify({"results": results, "matched": matched})


@api_bp.route('/passage/<source_hash>', methods=['GET'])
def passage_get(source_hash):
    """One stored passage, addressed by its source hash. The hash is an opaque
    handle taken from a listing — do not compute it client-side."""
    item = _service().get_passage(_hash_or_400(source_hash))
    if item is None:
        return jsonify(error="not_found",
                       message=f"No passage for hash: {source_hash}"), 404
    return jsonify(dict(item))


@api_bp.route('/passage', methods=['GET'])
def passage_list():
    return jsonify(_service().list_passage(
        entity_type=request.args.get('entity_type'),
        search=request.args.get('search'),
        page=parse_int(request.args.get('page'), 1, 1),
        limit=parse_int(request.args.get('limit'), 50, 1, 200),
    ))


@api_bp.route('/passage/init', methods=['POST'])
def passage_init():
    """`replace=true` clears the language pair first. Every translation is
    checked for VNDB markup preservation (see markup.py) and rejected if it
    dropped, added or translated a token."""
    body = request.get_json(silent=True) or {}
    entries = body.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValidationError("Body must include a non-empty 'entries' list.")
    count = _service().init_passage(
        entries,
        default_entity=body.get('entity_type'),
        default_category=body.get('category'),
        replace=bool(body.get('replace', False)),
    )
    return jsonify({"submitted": count}), 201


@api_bp.route('/passage', methods=['POST'])
def passage_append():
    """Upsert by source hash — unlike /passage/init this never clears."""
    body = request.get_json(silent=True) or {}
    entries = body.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValidationError("Body must include a non-empty 'entries' list.")
    count = _service().append_passage(
        entries,
        default_entity=body.get('entity_type'),
        default_category=body.get('category'),
    )
    return jsonify({"submitted": count}), 201


@api_bp.route('/passage/<source_hash>', methods=['DELETE'])
def passage_delete(source_hash):
    if not _service().delete_passage(_hash_or_400(source_hash)):
        return jsonify(error="not_found",
                       message=f"No passage for hash: {source_hash}"), 404
    return jsonify({"deleted": source_hash})


# ----------------------------------------
# Text translation (reserved — not implemented)
# ----------------------------------------

@api_bp.route('/translate', methods=['POST'])
def translate_text():
    """Reserved; always 501 until an MT backend is wired in."""
    body = request.get_json(silent=True) or {}
    text = body.get('text', '')
    try:
        result = _service().translate_text(text)
        return jsonify({"text": text, "translation": result})
    except TranslationNotImplemented as e:
        return jsonify(error="not_implemented", message=str(e)), 501
