import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # Flask configurations
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    USE_RELOADER = os.environ.get('USE_RELOADER', 'False').lower() in ('true', '1', 'yes')
    SECRET_KEY = os.environ['SECRET_KEY']
    APP_HOST = os.environ['MUSICSERVE_HOST']
    APP_PORT = int(os.environ['MUSICSERVE_PORT'])

    # CORS — mirrors the other services' allowlist handling.
    CORS_ORIGINS = [
        o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost,http://localhost:3000').split(',') if o.strip()
    ]

    # Data folder configuration. Paths are made absolute here (resolved
    # against the launcher's cwd, backend/): Flask's send_file resolves a
    # relative path against app.root_path — the musicserve package dir —
    # which is NOT where a relative DATA_FOLDER points.
    DATA_FOLDER = os.path.abspath(os.environ['DATA_FOLDER'])

    # The music library: one folder per visual novel, holding its soundtrack —
    # "music/v17/01 - Cardinal.flac". See musicserve/library.py.
    MUSIC_FOLDER = os.path.abspath(os.environ.get(
        'MUSICSERVE_MUSIC_FOLDER',
        os.path.join(DATA_FOLDER, 'music'),
    ))

    # Upload ceiling for one request. A lossless soundtrack is easily several
    # hundred MB, and the whole album arrives in a single multipart POST.
    MAX_CONTENT_LENGTH = int(os.environ.get('MUSICSERVE_MAX_UPLOAD_BYTES', 1024 ** 3))

    # Where covers extracted from embedded album art are cached, so mutagen
    # only parses each audio file once per modification.
    COVER_CACHE_FOLDER = os.path.abspath(os.environ.get(
        'MUSICSERVE_COVER_CACHE_FOLDER',
        os.path.join(DATA_FOLDER, 'tmp', 'music_covers'),
    ))

    # Waitress thread pool (prod). Range requests are short partial reads, but
    # several can be in flight while a track streams; keep some headroom.
    WAITRESS_THREADS = int(os.environ.get('MUSICSERVE_WAITRESS_THREADS', '16'))
