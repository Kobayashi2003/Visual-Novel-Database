"""The library on disk: one folder per visual novel, holding its soundtrack.

    data/music/v17/01 - Cardinal.flac
                   02 - LeMU.flac
                   cover.jpg          (optional)

There is no database, so the filesystem carries everything. The filename carries
both the order and the title, because tags cannot be relied on in a
hand-assembled library — half the files have no track number. A track is
addressed by its 1-based position in the sorted listing.

Covers resolve in two steps and never fall back to the visual novel's own cover:
a `cover.*` / `folder.*` image in the folder, then art embedded in the first
track that has any. A soundtrack with neither has no cover, and the UI shows a
placeholder rather than borrowing an unrelated image.
"""

from __future__ import annotations

import base64
import os
import re
from typing import Optional, Tuple

from mutagen import File as MutagenFile
from mutagen.flac import Picture
from mutagen.mp4 import MP4Cover

from .logger import logger


# Preference order doubles as the lookup order when several formats coexist.
AUDIO_EXTS = ('.mp3', '.m4a', '.flac', '.ogg', '.opus', '.wav')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')

AUDIO_MIME = {
    '.mp3':  'audio/mpeg',
    '.m4a':  'audio/mp4',
    '.flac': 'audio/flac',
    '.ogg':  'audio/ogg',
    '.opus': 'audio/ogg',
    '.wav':  'audio/wav',
}

IMAGE_MIME = {
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png':  'image/png',
    '.webp': 'image/webp',
}

_MIME_EXT = {
    'image/jpeg': '.jpg',
    'image/png':  '.png',
    'image/webp': '.webp',
}

# Filenames a folder-level cover may use, in preference order.
COVER_STEMS = ('cover', 'folder', 'front')

_VNID_RE = re.compile(r'^v?(\d+)$')
# A stored filename may not reach outside its folder, and Windows rejects these
# outright. Checked rather than rewritten: a silently mangled name would be
# harder to notice than a refused upload.
_UNSAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# "01 - Title", "01. Title", "01_Title", "01 Title" — the numeric prefix is the
# order and is not part of the title.
_TRACK_PREFIX_RE = re.compile(r'^\s*\d+\s*[-._)]?\s*')


class LibraryError(Exception):
    """Base for failures meant to be reported to the client. Each subclass
    carries the error code and status the route layer reports."""
    error_code = "invalid_request"
    message = "Invalid request."
    http_status = 400


class UnsupportedFormatError(LibraryError):
    error_code = "unsupported_media_type"
    message = f"Audio must be one of: {', '.join(AUDIO_EXTS)}."
    http_status = 415


class UnsafeFilenameError(LibraryError):
    error_code = "invalid_request"
    message = "Filename may not contain path separators or reserved characters."


class TrackExistsError(LibraryError):
    error_code = "conflict"
    message = "A track with that filename is already in this soundtrack."
    http_status = 409


def normalize_vnid(raw: str) -> Optional[str]:
    """Validate a client-supplied vnid and normalize to the "v123" form.
    Returns None for anything that isn't a plain (optionally v-prefixed)
    number — which also makes path traversal impossible downstream."""
    m = _VNID_RE.match(str(raw).strip().lower())
    return f"v{m.group(1)}" if m else None


def soundtrack_folder(music_folder: str, vnid: str) -> str:
    """The folder for one soundtrack. `vnid` must already be normalized."""
    return os.path.join(music_folder, vnid)


def _natural_key(name: str):
    """Sort "9 - x" before "10 - x". Plain lexicographic order would not, and a
    library that mixes padded and unpadded numbers is the common case."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', name)]


def list_track_files(music_folder: str, vnid: str) -> list[str]:
    """Absolute paths of a soundtrack's audio files, in playing order."""
    folder = soundtrack_folder(music_folder, vnid)
    try:
        names = os.listdir(folder)
    except (FileNotFoundError, NotADirectoryError):
        return []
    audio = [n for n in names if os.path.splitext(n)[1].lower() in AUDIO_EXTS]
    audio.sort(key=_natural_key)
    return [os.path.join(folder, n) for n in audio]


def track_path(music_folder: str, vnid: str, ordinal: int) -> Optional[str]:
    """The file at 1-based `ordinal`, or None if the soundtrack is shorter."""
    files = list_track_files(music_folder, vnid)
    if 1 <= ordinal <= len(files):
        return files[ordinal - 1]
    return None


def has_tracks(music_folder: str, vnid: str) -> bool:
    return bool(list_track_files(music_folder, vnid))


def list_soundtracks(music_folder: str) -> list[str]:
    """Every vnid with at least one track, ascending by number."""
    try:
        names = os.listdir(music_folder)
    except FileNotFoundError:
        return []
    found = []
    for name in names:
        vnid = normalize_vnid(name)
        if vnid and has_tracks(music_folder, vnid):
            found.append(vnid)
    found.sort(key=lambda v: int(v[1:]))
    return found


def title_from_filename(path: str) -> str:
    """"01 - Cardinal.flac" -> "Cardinal". Falls back to the whole stem when
    stripping the prefix would leave nothing."""
    stem = os.path.splitext(os.path.basename(path))[0]
    stripped = _TRACK_PREFIX_RE.sub('', stem).strip()
    return stripped or stem


# ---------- writes ------------------------------------------------------------


def _next_ordinal(music_folder: str, vnid: str) -> int:
    return len(list_track_files(music_folder, vnid)) + 1


def store_track(music_folder: str, vnid: str, filename: str, stream, *,
                replace: bool = False) -> str:
    """Save one uploaded file into a soundtrack, returning the stored filename.

    A name that already starts with a number keeps its own ordering; anything
    else is prefixed with the next free number, so an upload can never land
    unordered. Raises LibraryError subclasses for the client-visible failures.
    """
    # Checked before basename(), not after: stripping the directory first would
    # make the separator check unreachable and quietly accept "../x" as "x".
    name = (filename or '').strip()
    if not name or _UNSAFE_NAME_RE.search(name) or os.path.basename(name) in ('', '.', '..'):
        raise UnsafeFilenameError()
    if os.path.splitext(name)[1].lower() not in AUDIO_EXTS:
        raise UnsupportedFormatError()

    if not _TRACK_PREFIX_RE.match(name):
        name = f"{_next_ordinal(music_folder, vnid):02d} - {name}"

    folder = soundtrack_folder(music_folder, vnid)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    if os.path.exists(path) and not replace:
        raise TrackExistsError()

    # Write beside the target and rename, so a failed or aborted upload never
    # leaves a partial file that the listing would pick up as a track.
    tmp = path + '.part'
    try:
        stream.save(tmp)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    _meta_cache.pop(path, None)
    return name


def delete_track(music_folder: str, vnid: str, ordinal: int) -> Optional[str]:
    """Remove one track. Returns its filename, or None if there was no such
    track. Renumbering is not needed: ordinals are positions in the listing, so
    the tracks after it simply shift up."""
    path = track_path(music_folder, vnid, ordinal)
    if path is None:
        return None
    os.remove(path)
    _meta_cache.pop(path, None)
    return os.path.basename(path)


def delete_soundtrack(music_folder: str, vnid: str) -> int:
    """Remove every track, and the folder itself when nothing else is left.
    Returns how many tracks were removed, 0 when there was no soundtrack."""
    files = list_track_files(music_folder, vnid)
    for path in files:
        os.remove(path)
        _meta_cache.pop(path, None)
    folder = soundtrack_folder(music_folder, vnid)
    if os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
    return len(files)


# ---------- cover art ---------------------------------------------------------


def find_cover_file(music_folder: str, vnid: str) -> Optional[str]:
    """A `cover.*` / `folder.*` / `front.*` image sitting in the folder.

    Matched by scanning rather than by probing exact names: real files are named
    `Front.png` as often as `front.png`, and probing would find those only on a
    case-insensitive filesystem — it would work on Windows and quietly stop
    working in the Linux container.
    """
    folder = soundtrack_folder(music_folder, vnid)
    try:
        names = os.listdir(folder)
    except (FileNotFoundError, NotADirectoryError):
        return None
    by_stem = {}
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS:
            by_stem.setdefault(stem.lower(), name)
    for stem in COVER_STEMS:
        if stem in by_stem:
            return os.path.join(folder, by_stem[stem])
    return None


def _embedded_picture(audio_path: str) -> Optional[Tuple[bytes, str]]:
    """(bytes, mime) of the first embedded cover, or None."""
    audio = MutagenFile(audio_path)
    if audio is None:
        return None

    # FLAC (and anything else exposing .pictures)
    pictures = getattr(audio, 'pictures', None)
    if pictures:
        return pictures[0].data, pictures[0].mime or 'image/jpeg'

    tags = audio.tags
    if tags is None:
        return None

    # ID3 (mp3 / wav-with-ID3 / aiff)
    if hasattr(tags, 'getall'):
        apics = tags.getall('APIC')
        if apics:
            return apics[0].data, apics[0].mime or 'image/jpeg'

    if hasattr(tags, 'get'):
        # MP4 / M4A
        covr = tags.get('covr')
        if covr:
            cover = covr[0]
            mime = 'image/png' if cover.imageformat == MP4Cover.FORMAT_PNG else 'image/jpeg'
            return bytes(cover), mime

        # Vorbis comments (ogg / opus): base64-encoded FLAC picture block
        block = tags.get('metadata_block_picture')
        if block:
            pic = Picture(base64.b64decode(block[0]))
            return pic.data, pic.mime or 'image/jpeg'

    return None


def extract_cover(audio_path: str, cache_folder: str, vnid: str) -> Optional[str]:
    """Path to the embedded-art cover for `audio_path`, extracting and caching it
    on first sight. Keyed to the audio file's mtime, so a replaced file
    invalidates the cached image. A zero-byte `.none` marker records "this file
    has no art", which keeps a coverless soundtrack from re-parsing audio on
    every request."""
    mtime = int(os.path.getmtime(audio_path))
    stem = os.path.join(cache_folder, f"{vnid}.{mtime}")

    for ext in ('.jpg', '.png', '.webp', '.none'):
        cached = stem + ext
        if os.path.isfile(cached):
            return None if ext == '.none' else cached

    os.makedirs(cache_folder, exist_ok=True)
    # Drop stale entries for this vnid (older mtimes).
    prefix = f"{vnid}."
    for name in os.listdir(cache_folder):
        if name.startswith(prefix) and not name.startswith(f"{prefix}{mtime}"):
            try:
                os.remove(os.path.join(cache_folder, name))
            except OSError:
                pass

    try:
        found = _embedded_picture(audio_path)
    except Exception as e:
        logger.warning(f"embedded-art parse failed for {audio_path}: {e}")
        found = None

    if not found or not found[0]:
        open(stem + '.none', 'wb').close()
        return None

    data, mime = found
    path = stem + _MIME_EXT.get(mime, '.jpg')
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def soundtrack_cover(music_folder: str, cache_folder: str, vnid: str) -> Optional[str]:
    """The soundtrack's cover: a folder image, else art embedded in the first
    track that carries any. Never the visual novel's own cover — that is a
    different picture, and substituting it would misrepresent the release."""
    path = find_cover_file(music_folder, vnid)
    if path:
        return path
    for track in list_track_files(music_folder, vnid):
        found = extract_cover(track, cache_folder, vnid)
        if found:
            return found
    return None


# ---------- tag metadata -------------------------------------------------------


# Per-container tag keys for title / artist / album: easy-mode (mp3/flac/ogg),
# raw ID3 frames (wav/aiff, where mutagen has no easy wrapper), and MP4 atoms.
_TAG_KEYS = {
    'title':  ('title', 'TIT2', '\xa9nam'),
    'artist': ('artist', 'TPE1', '\xa9ART'),
    'album':  ('album', 'TALB', '\xa9alb'),
}

# Reading tags means parsing the file, and a track listing asks for every track
# at once. Keyed by mtime so an edited file is re-read.
_meta_cache: dict[str, Tuple[int, dict]] = {}


def _first_tag(tags, keys) -> Optional[str]:
    for key in keys:
        try:
            val = tags.get(key)
        except Exception:
            val = None
        if not val:
            continue
        item = val[0] if isinstance(val, (list, tuple)) else val
        # ID3 frames stringify to their text; everything else already is text.
        text = str(item).strip()
        if text:
            return text
    return None


def read_meta(audio_path: str) -> dict:
    """Duration and tags, best effort — a missing tag comes back None. The title
    always comes from the filename, which is the one thing every file in the
    library is guaranteed to have."""
    try:
        mtime = int(os.path.getmtime(audio_path))
    except OSError:
        mtime = 0
    cached = _meta_cache.get(audio_path)
    if cached and cached[0] == mtime:
        return cached[1]

    duration = artist = album = None
    tag_title = None
    try:
        audio = MutagenFile(audio_path, easy=True)
        if audio is not None:
            if audio.info is not None:
                duration = round(float(audio.info.length), 2)
            tags = audio.tags
            if tags is not None:
                tag_title = _first_tag(tags, _TAG_KEYS['title'])
                artist = _first_tag(tags, _TAG_KEYS['artist'])
                album = _first_tag(tags, _TAG_KEYS['album'])
    except Exception as e:
        logger.warning(f"meta parse failed for {audio_path}: {e}")

    meta = {
        'title': title_from_filename(audio_path),
        'tag_title': tag_title,
        'artist': artist,
        'album': album,
        'duration': duration,
        'format': os.path.splitext(audio_path)[1].lstrip('.').lower(),
    }
    _meta_cache[audio_path] = (mtime, meta)
    return meta
