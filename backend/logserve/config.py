import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # Flask configurations
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    USE_RELOADER = os.environ.get('USE_RELOADER', 'False').lower() in ('true', '1', 'yes')
    SECRET_KEY = os.environ['SECRET_KEY']
    APP_HOST = os.environ['LOGSERVE_HOST']
    APP_PORT = int(os.environ['LOGSERVE_PORT'])

    # Database configuration — logserve reads (and prunes) the `logs` table that
    # the vndbserve search backends write to, so it points at the *vndbserve* database by
    # default rather than a peer DB of its own. Override LOGSERVE_DB_URL only if
    # the logs table is ever relocated.
    SQLALCHEMY_DATABASE_URI = os.environ.get('LOGSERVE_DB_URL') or os.environ['VNDBSERVE_DB_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # CORS — mirrors the other services' allowlist handling. logserve is a
    # developer-facing tool and is intentionally NOT exposed through the Caddy
    # edge (../../Caddyfile.snippet has no route for it), so it is only reachable
    # on the loopback dev port; the allowlist is kept for parity.
    CORS_ORIGINS = [
        o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost,http://localhost:3000').split(',') if o.strip()
    ]

    # Waitress thread pool (prod). Reads are short indexed scans over the logs
    # table; a small pool is plenty for a single-developer diagnostic tool.
    WAITRESS_THREADS = int(os.environ.get('LOGSERVE_WAITRESS_THREADS', '4'))

    # Upper bound on the number of rows a single query replay may return, so a
    # replayed SELECT * against a huge table can't blow up the response.
    REPLAY_MAX_ROWS = int(os.environ.get('LOGSERVE_REPLAY_MAX_ROWS', '500'))
