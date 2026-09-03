"""The whole service: browse soundtracks, stream a track, upload one.

There is no database — the folder layout in library.py is the index, scanned per
request. Audio is served with range support so a player can seek without
fetching the whole file.

One visual novel is one soundtrack, so a track is addressed by the vnid and its
1-based position: `/soundtracks/v17/tracks/3`. Positions shift when a track is
added or removed, which costs nothing because nothing persists a reference to a
track — the play queue lives in the browser.

Uploading is the only write, and the only one the edge exposes for any service.
It is restricted to administrators, and the identity comes from the edge (see
`_require_admin`) rather than from any auth code here.
"""

import os

from flask import Blueprint, current_app, jsonify, request, send_file, abort

from .library import (
    AUDIO_MIME, IMAGE_MIME, LibraryError,
    normalize_vnid, list_soundtracks, list_track_files, track_path,
    has_tracks, read_meta, soundtrack_cover,
    store_track, delete_track, delete_soundtrack,
)

api_bp = Blueprint('api', __name__, url_prefix='/')


@api_bp.errorhandler(LibraryError)
def handle_library_error(e):
    return jsonify(error=e.error_code, message=e.message), e.http_status


_TRUE = {'true', '1', 'yes', 'on'}
_FALSE = {'false', '0', 'no', 'off'}

def parse_bool(raw, default: bool) -> bool:
    """A query parameter as a boolean, or the default when it was not sent.

    A value that is neither is refused rather than replaced by the default:
    `?sync=perhaps` would otherwise answer with a task id where the caller asked
    for a result, and nothing in the reply would say so.
    """
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    abort(400, description=f"Expected true or false, got: {raw!r}")


def _music_folder() -> str:
    return current_app.config['MUSIC_FOLDER']


def _vnid_or_400(raw: str) -> str:
    vnid = normalize_vnid(raw)
    if vnid is None:
        abort(400, description="vnid must be a number, optionally v-prefixed (e.g. v17)")
    return vnid


def _require_admin() -> None:
    """The edge probes userserve on every request and copies the answer into
    X-Is-Admin, having first stripped whatever the client sent under that name.
    So this service still holds no auth code — it only reads the verdict."""
    if request.headers.get('X-Is-Admin', '').lower() != 'true':
        abort(403, description="Uploading is restricted to administrators.")


def _track_json(path: str, ordinal: int) -> dict:
    return {'ordinal': ordinal, 'filename': os.path.basename(path), **read_meta(path)}


@api_bp.route('', methods=['GET', 'TRACE'])
def hello_world():
    return jsonify({"message": "MUSICSERVE"})


# ----------------------------------------
# Soundtracks
# ----------------------------------------

@api_bp.route('/soundtracks', methods=['GET'])
def soundtracks():
    """Every visual novel with at least one track. Only ids and counts — the
    caller already has the titles and covers from vndbserve and imgserve."""
    folder = _music_folder()
    ids = list_soundtracks(folder)
    total = len(ids)

    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = max(1, min(int(request.args.get('limit', 24)), 100))
    except (TypeError, ValueError):
        abort(400, description="page and limit must be integers.")

    start = (page - 1) * limit
    window = ids[start:start + limit]
    results = [{'id': v, 'track_count': len(list_track_files(folder, v))} for v in window]
    return jsonify({'results': results, 'count': total, 'more': start + limit < total})


@api_bp.route('/soundtracks/available', methods=['POST'])
def available():
    """Which of the posted vnids have a soundtrack. Body: {"ids": ["v17", 23]}.
    Keys echo the caller's spelling so the response maps straight onto its own
    data."""
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
        result[key] = bool(vnid and has_tracks(folder, vnid))
    return jsonify({'available': result})


@api_bp.route('/soundtracks/<raw_id>', methods=['GET'])
def soundtrack(raw_id: str):
    vnid = _vnid_or_400(raw_id)
    files = list_track_files(_music_folder(), vnid)
    if not files:
        abort(404)
    tracks = [_track_json(p, i) for i, p in enumerate(files, start=1)]
    return jsonify({
        'id': vnid,
        'track_count': len(tracks),
        'duration': round(sum(t['duration'] or 0 for t in tracks), 2),
        'results': tracks,
    })


@api_bp.route('/soundtracks/<raw_id>', methods=['DELETE'])
def remove_soundtrack(raw_id: str):
    _require_admin()
    vnid = _vnid_or_400(raw_id)
    removed = delete_soundtrack(_music_folder(), vnid)
    if not removed:
        abort(404)
    return jsonify(message=f"Removed {removed} track(s)."), 200


# ----------------------------------------
# Cover art
# ----------------------------------------

@api_bp.route('/soundtracks/<raw_id>/cover', methods=['GET'])
def cover(raw_id: str):
    """The soundtrack's own cover. 404 when it has none — the caller shows a
    placeholder rather than the visual novel's cover, which is a different
    picture."""
    vnid = _vnid_or_400(raw_id)
    path = soundtrack_cover(_music_folder(), current_app.config['COVER_CACHE_FOLDER'], vnid)
    if path is None:
        abort(404)
    ext = os.path.splitext(path)[1].lower()
    resp = send_file(path, mimetype=IMAGE_MIME.get(ext, 'image/jpeg'), conditional=True)
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


# ----------------------------------------
# Tracks
# ----------------------------------------

@api_bp.route('/soundtracks/<raw_id>/tracks/<int:ordinal>', methods=['GET'])
def track(raw_id: str, ordinal: int):
    """The audio itself. `conditional=True` gives Range / If-Modified-Since
    handling for free — seeking is a 206 partial fetch, not a re-download."""
    vnid = _vnid_or_400(raw_id)
    path = track_path(_music_folder(), vnid, ordinal)
    if path is None:
        abort(404)
    ext = os.path.splitext(path)[1].lower()
    resp = send_file(path, mimetype=AUDIO_MIME.get(ext), conditional=True)
    # Files can be swapped in place, so cache briefly rather than immutably;
    # the conditional revalidation keeps repeat plays cheap.
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    resp.headers.setdefault('Accept-Ranges', 'bytes')
    return resp


@api_bp.route('/soundtracks/<raw_id>/tracks', methods=['POST'])
def upload_tracks(raw_id: str):
    """Add files to a soundtrack. multipart/form-data, field `files`, repeated
    for each track. `replace=true` overwrites an existing filename instead of
    reporting a conflict.

    Synchronous: the slow part is the transfer itself, which the caller waits
    for either way, so a queue would add a worker process and buy nothing.
    """
    _require_admin()
    vnid = _vnid_or_400(raw_id)
    files = request.files.getlist('files')
    if not files:
        abort(400, description="Attach at least one file under the 'files' field.")

    replace = parse_bool(request.args.get('replace'), False)
    stored = [store_track(_music_folder(), vnid, f.filename, f, replace=replace)
              for f in files]
    return jsonify({'id': vnid, 'stored': stored}), 201


@api_bp.route('/soundtracks/<raw_id>/tracks/<int:ordinal>', methods=['DELETE'])
def remove_track(raw_id: str, ordinal: int):
    _require_admin()
    vnid = _vnid_or_400(raw_id)
    removed = delete_track(_music_folder(), vnid, ordinal)
    if removed is None:
        abort(404)
    return jsonify(message=f"Removed {removed}."), 200
