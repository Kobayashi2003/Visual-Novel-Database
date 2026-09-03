import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # Flask configurations
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    USE_RELOADER = os.environ.get('USE_RELOADER', 'False').lower() in ('true', '1', 'yes')
    SECRET_KEY = os.environ['SECRET_KEY']
    APP_HOST = os.environ['VNDBSERVE_HOST']
    APP_PORT = int(os.environ['VNDBSERVE_PORT'])

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ['VNDBSERVE_DB_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Cache configuration
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ['VNDBSERVE_CACHE_REDIS_URL']
    CACHE_DEFAULT_TIMEOUT = 300

    # Celery configuration
    CELERY_DEFAULT_QUEUE = os.environ['VNDBSERVE_CELERY_DEFAULT_QUEUE']
    CELERY_BROKER_URL = os.environ['VNDBSERVE_CELERY_BROKER_URL']
    CELERY_RESULT_BACKEND = os.environ['VNDBSERVE_CELERY_RESULT_BACKEND']
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    FLOWER_PORT = os.environ['VNDBSERVE_FLOWER_PORT']

    # Scheduler configuration
    SCHEDULER_API_ENABLED = True
    # Timezone the cron schedules (incl. the CRAWL_HOURS off-peak window) are
    # interpreted in. Set to the user base's timezone so "off-peak" is real.
    SCHEDULER_TIMEZONE = os.environ.get('SCHEDULER_TIMEZONE', 'Asia/Shanghai')

    # Log retention
    # How long the `logs` table keeps a row, by what the row records. Routine
    # entries are one per search and are read within days if at all; the ones
    # that record a failure are worth having when a problem surfaces later, and
    # there are three orders of magnitude fewer of them. Zero or less keeps
    # everything — see schedule/logs.py.
    LOG_RETENTION_DAYS = int(os.environ.get('LOG_RETENTION_DAYS', 30))
    LOG_FAILURE_RETENTION_DAYS = int(os.environ.get('LOG_FAILURE_RETENTION_DAYS', 365))

    # Data folder configuration
    DATA_FOLDER = os.environ['DATA_FOLDER']
    TEMP_FOLDER = os.path.join(DATA_FOLDER, 'tmp')
    BACKUP_FOLDER = os.path.join(DATA_FOLDER, 'backups')