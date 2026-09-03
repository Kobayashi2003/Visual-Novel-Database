import time
from abc import ABC, abstractmethod
from functools import wraps

from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from sqlalchemy import text

from .logger import logger


def wait_for_db(db, app, initial_delay=1.0, max_delay=30.0):
    delay = initial_delay
    attempt = 0
    while True:
        attempt += 1
        try:
            with app.app_context():
                with db.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            if attempt > 1:
                msg = f"Database connection established after {attempt} attempts"
                logger.info(msg)
                print(msg)
            return
        except Exception as e:
            msg = f"Database not ready (attempt {attempt}): {e}; retrying in {delay:.1f}s"
            logger.warning(msg)
            print(msg)
            time.sleep(delay)
            delay = min(delay * 2, max_delay)


class Extension(ABC):
    def __init__(self, app):
        self._app = app
        self._instance = self.create(app)

    def __getattr__(self, name):
        # Read through __dict__: __getattr__ runs whenever normal lookup fails,
        # so reaching for a not-yet-set attribute through `self` would re-enter
        # this method forever.
        instance = self.__dict__.get('_instance')
        if instance is None:
            raise AttributeError(f"{self.__class__.__name__} has not been initialized")
        return getattr(instance, name)

    @abstractmethod
    def create(self, app):
        pass


class ExtSQLAlchemy(Extension):
    def create(self, app):
        db = SQLAlchemy(app)
        wait_for_db(db, app)
        with app.app_context():
            db.create_all()
        return db


class ExtAPScheduler(Extension):
    def __getattr__(self, name):
        if name == 'task':
            return self.scheduled_task
        return super().__getattr__(name)

    def create(self, app):
        scheduler = APScheduler()
        scheduler.init_app(app)
        scheduler.start()
        return scheduler

    def scheduled_task(self, *args, **kwargs):
        def decorator(func):
            @wraps(func)
            @self._instance.task(*args, **kwargs)
            def wrapper(*a, **kw):
                with self._app.app_context():
                    return func(*a, **kw)
            return wrapper
        return decorator
