"""The whole service: browse the music folder, stream a track, read its tags.

There is no database. The folder on disk is the library, scanned per request.
Audio is served with range support so a player can seek without fetching the whole
file, and cover art is extracted from the tags and cached separately.
"""

import os

from flask import Blueprint, current_app, jsonify, request, send_file, abort

from .library import (
    AUDIO_MIME, IMAGE_MIME,
    normalize_vnid, find_audio, find_cover_file, extract_cover, read_meta,
)

api_bp = Blueprint('api', __name__, url_prefix='/')


@api_bp.errorhandler(400)
def bad_request(e):
    return jsonify(error="invalid_request", message=str(e.description)), 400

@api_bp.errorhandler(404)
def not_found(e):
    return jsonify(error="not_found", message="Resource not found."), 404

@api_bp.errorhandler(500)
def server_error(e):
    return jsonify(error="internal_error", message="An unexpected error occurred."), 500


def _music_folder() -> str:
    return current_app.config['MUSIC_FOLDER']


def _vnid_or_400(raw: str) -> str:
    vnid = normalize_vnid(raw)
    if vnid is None:
        abort(400, description="vnid must be a number, optionally v-prefixed (e.g. v17)")
    return vnid


@api_bp.route('', methods=['GET', 'TRACE'])
def hello_world():
    return jsonify({"message": "MUSICSERVE"})


# ----------------------------------------
# Audio stream
# ----------------------------------------

@api_bp.route('/music/<raw_id>', methods=['GET'])
def music(raw_id: str):
    """The audio file for a vnid. `conditional=True` gives Range /
    If-Modified-Since handling for free — seeking in the player is a
    206 partial fetch, not a re-download."""
    vnid = _vnid_or_400(raw_id)
    path = find_audio(_music_folder(), vnid)
    if path is None:
        abort(404)
    ext = os.path.splitext(path)[1].lower()
    resp = send_file(path, mimetype=AUDIO_MIME.get(ext), conditional=True)
    # Files can be swapped in place, so cache briefly rather than immutably;
    # the conditional revalidation keeps repeat plays cheap.
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    resp.headers.setdefault('Accept-Ranges', 'bytes')
    return resp


# ----------------------------------------
# Cover art
# ----------------------------------------

@api_bp.route('/cover/<raw_id>', methods=['GET'])
def cover(raw_id: str):
    """Cover for a vnid: a sibling image file first, embedded album art
    (extracted + cached) second, 404 when neither exists."""
    vnid = _vnid_or_400(raw_id)
    folder = _music_folder()

    path = find_cover_file(folder, vnid)
    if path is None:
        audio = find_audio(folder, vnid)
        if audio is None:
            abort(404)
        path = extract_cover(audio, current_app.config['COVER_CACHE_FOLDER'], vnid)
        if path is None:
            abort(404)

    ext = os.path.splitext(path)[1].lower()
    resp = send_file(path, mimetype=IMAGE_MIME.get(ext, 'image/jpeg'), conditional=True)
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


# ----------------------------------------
# Track metadata
# ----------------------------------------

@api_bp.route('/meta/<raw_id>', methods=['GET'])
def meta(raw_id: str):
    vnid = _vnid_or_400(raw_id)
    folder = _music_folder()
    audio = find_audio(folder, vnid)
    if audio is None:
        abort(404)

    info = read_meta(audio)
    has_cover = (
        find_cover_file(folder, vnid) is not None
        or extract_cover(audio, current_app.config['COVER_CACHE_FOLDER'], vnid) is not None
    )
    return jsonify({'id': vnid, 'has_cover': has_cover, **info})


# ----------------------------------------
# Batch availability
# ----------------------------------------

@api_bp.route('/available', methods=['POST'])
def available():
    """Which of the posted vnids have music. Body: {"ids": ["v17", 23, ...]}.
    Returns {"available": {<id as posted>: bool, ...}} — keys echo the
    caller's spelling so the response maps straight onto its own data."""
    body = request.get_json(silent=True) or {}
    ids = body.get('ids')
    if not isinstance(ids, list):
        abort(400, description="Body must include an 'ids' list.")
    if len(ids) > 2000:
        abort(400, description="At most 2000 ids per request.")

    folder = _music_folder()
    result = {}
    for raw in ids:
        key = str(raw)
        vnid = normalize_vnid(key)
        result[key] = bool(vnid and find_audio(folder, vnid))
    return jsonify({'available': result})
