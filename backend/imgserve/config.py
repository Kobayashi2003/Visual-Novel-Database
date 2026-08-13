import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # Flask configurations
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    USE_RELOADER = os.environ.get('USE_RELOADER', 'False').lower() in ('true', '1', 'yes')
    SECRET_KEY = os.environ['SECRET_KEY']
    APP_HOST = os.environ['IMGSERVE_HOST']
    APP_PORT = int(os.environ['IMGSERVE_PORT'])
    # Waitress thread pool. Cold image requests block on httpx fetches from
    # t.vndb.org, so we want plenty of threads to absorb concurrent misses.
    # Combined with the Redis single-flight in routes/images.py, duplicate
    # requests for the same image collapse to one upstream fetch regardless
    # of thread count.
    WAITRESS_THREADS = int(os.environ.get('IMGSERVE_WAITRESS_THREADS', '64'))

    SQLALCHEMY_DATABASE_URI = os.environ['IMGSERVE_DB_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ['IMGSERVE_CACHE_REDIS_URL']
    CACHE_DEFAULT_TIMEOUT = 300

    # Direct redis client (single-flight + access ZSET). Kept in its own DB so
    # the Flask-Caching keyspace stays free of bookkeeping junk.
    REDIS_URL = os.environ['IMGSERVE_REDIS_URL']
    REDIS_DECODE_RESPONSES = False

    CELERY_DEFAULT_QUEUE = os.environ['IMGSERVE_CELERY_DEFAULT_QUEUE']
    CELERY_BROKER_URL = os.environ['IMGSERVE_CELERY_BROKER_URL']
    CELERY_RESULT_BACKEND = os.environ['IMGSERVE_CELERY_RESULT_BACKEND']
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    # CELERY_TIMEZONE = 'UTC'
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    FLOWER_PORT = os.environ['IMGSERVE_FLOWER_PORT']

    SCHEDULER_API_ENABLED = True
    # Timezone the cron schedules (incl. the CRAWL_HOURS off-peak window) are
    # interpreted in. Set to the user base's timezone so "off-peak" is real.
    SCHEDULER_TIMEZONE = os.environ.get('SCHEDULER_TIMEZONE', 'Asia/Shanghai')

    DATA_FOLDER = os.environ['DATA_FOLDER']
    TEMP_FOLDER = os.path.join(DATA_FOLDER, 'tmp')
    IMAGE_FOLDER = os.path.join(DATA_FOLDER, 'images')
    BACKUP_FOLDER = os.path.join(DATA_FOLDER, 'backups')