import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # Flask configurations
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    USE_RELOADER = os.environ.get('USE_RELOADER', 'False').lower() in ('true', '1', 'yes')
    SECRET_KEY = os.environ['SECRET_KEY']
    APP_HOST = os.environ['TRANSSERVE_HOST']
    APP_PORT = int(os.environ['TRANSSERVE_PORT'])

    # Database configuration — the term base lives in its own Postgres DB,
    # peer to vndbserve / imgserve / userserve.
    SQLALCHEMY_DATABASE_URI = os.environ['TRANSSERVE_DB_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # CORS — the frontend may call the term lookup directly. Mirrors the
    # other services' allowlist handling.
    CORS_ORIGINS = [
        o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost,http://localhost:3000').split(',') if o.strip()
    ]

    # Default language pair for the term base / (future) text translation.
    SOURCE_LANG = os.environ.get('TRANSSERVE_SOURCE_LANG', 'en')
    TARGET_LANG = os.environ.get('TRANSSERVE_TARGET_LANG', 'ja')

    # Waitress thread pool (prod). Lookups are short indexed reads.
    WAITRESS_THREADS = int(os.environ.get('TRANSSERVE_WAITRESS_THREADS', '8'))

    SCHEDULER_API_ENABLED = True

    DATA_FOLDER = os.environ['DATA_FOLDER']
    TEMP_FOLDER = os.path.join(DATA_FOLDER, 'tmp')
    BACKUP_FOLDER = os.path.join(DATA_FOLDER, 'backups')
