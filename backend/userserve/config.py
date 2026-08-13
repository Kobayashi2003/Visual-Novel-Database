import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:

    # Flask configurations
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    USE_RELOADER = os.environ.get('USE_RELOADER', 'False').lower() in ('true', '1', 'yes')
    SECRET_KEY = os.environ['SECRET_KEY']
    APP_HOST = os.environ['USERSERVE_HOST']
    APP_PORT = int(os.environ['USERSERVE_PORT'])

    JWT_SECRET_KEY = os.environ['JWT_SECRET_KEY']
    JWT_VERIFY_SUB = False
    JWT_ALGORITHM = 'HS256'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.environ.get('JWT_ACCESS_TOKEN_MINUTES', 30)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get('JWT_REFRESH_TOKEN_DAYS', 30)))

    # JWT transport — access & refresh tokens ride in httpOnly cookies, so they
    # are never readable by browser JavaScript. Each cookie is paired with a
    # readable CSRF token that clients must echo in the X-CSRF-TOKEN header on
    # state-changing requests. Set JWT_COOKIE_SECURE=True when serving over HTTPS.
    JWT_TOKEN_LOCATION = ['cookies']
    JWT_COOKIE_SECURE = os.environ.get('JWT_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
    JWT_COOKIE_SAMESITE = os.environ.get('JWT_COOKIE_SAMESITE', 'Lax')
    JWT_COOKIE_CSRF_PROTECT = True

    # CORS — credentialed cookie requests cannot use a wildcard origin, so the
    # allowed origins are pinned to an explicit list.
    CORS_ORIGINS = [
        o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost,http://localhost:3000').split(',') if o.strip()
    ]

    # Rate limiting (Flask-Limiter). Defaults to in-process memory storage; set
    # USERSERVE_RATELIMIT_STORAGE_URI to a redis:// URL for multi-worker setups.
    RATELIMIT_STORAGE_URI = os.environ.get('USERSERVE_RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True

    # Mail (SMTP). Configure QQ and/or Gmail credentials; send_email tries each
    # configured provider (in MAIL_PROVIDER_ORDER) until one succeeds. With none
    # configured, emails are logged to the console instead of being sent.
    MAIL_QQ_USERNAME = os.environ.get('MAIL_QQ_USERNAME', '')
    MAIL_QQ_PASSWORD = os.environ.get('MAIL_QQ_PASSWORD', '')
    MAIL_GMAIL_USERNAME = os.environ.get('MAIL_GMAIL_USERNAME', '')
    MAIL_GMAIL_PASSWORD = os.environ.get('MAIL_GMAIL_PASSWORD', '')
    MAIL_PROVIDER_ORDER = [
        p.strip().lower() for p in os.environ.get('MAIL_PROVIDER_ORDER', 'qq,gmail').split(',') if p.strip()
    ]
    MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'False').lower() in ('true', '1', 'yes')

    # Password reset & email verification
    FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost')
    RESET_TOKEN_MAX_AGE = int(os.environ.get('RESET_TOKEN_MAX_AGE_SECONDS', 1800))
    VERIFICATION_CODE_MAX_AGE = int(os.environ.get('VERIFICATION_CODE_MAX_AGE_SECONDS', 600))

    # Direct redis client (verification codes + JWT blocklist). Strings are
    # auto-decoded since the userserve keys all store ASCII payloads.
    REDIS_URL = os.environ.get('USERSERVE_REDIS_URL', 'redis://localhost:6379/7')
    REDIS_DECODE_RESPONSES = True

    # Waitress thread pool. Sized for the worst-case route: send_verification_code
    # / forgot_password used to block on SMTP for up to 10s — mail dispatch is now
    # async (see userserve/mail.py) so a modest pool is enough.
    WAITRESS_THREADS = int(os.environ.get('USERSERVE_WAITRESS_THREADS', '16'))

    # Registration invite gate — when INVITATION_CODE is non-empty, new sign-ups
    # must supply a matching code. Leave it blank to keep registration open.
    INVITATION_CODE = os.environ.get('INVITATION_CODE', '').strip()

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ['USERSERVE_DB_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Scheduler configuration
    SCHEDULER_API_ENABLED = True

    # Data folder configuration
    DATA_FOLDER = os.environ['DATA_FOLDER']
    TEMP_FOLDER = os.path.join(DATA_FOLDER, 'tmp')
    BACKUP_FOLDER = os.path.join(DATA_FOLDER, 'backups')