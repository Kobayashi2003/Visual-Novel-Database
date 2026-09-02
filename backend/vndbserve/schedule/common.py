"""Cron decorators for the scheduled jobs.

Each wraps APScheduler's `scheduler.task` with a trigger and a job id derived
from the function name, so a job declares its own schedule at the definition
site. Importing a module that uses one is what registers the job — see the
imports in vndbserve/__init__.py.
"""

import os
from functools import wraps

from vndbserve import scheduler
from vndbserve.errors import ServiceError
from vndbserve.logger import logger


def _guarded(func):
    """The final handler for a scheduled job.

    A job is an entry point with nobody to return an outcome to, so an error
    has nowhere to go but the log — and it must not escape into the scheduler,
    which would report it through a logger of its own that nothing here reads.
    """
    @wraps(func)
    def run(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ServiceError as exc:
            if exc.kind == 'failed':
                logger.exception(f"{func.__name__} failed: {exc.message} {exc.context}")
            else:
                logger.warning(f"{func.__name__} {exc.kind}: {exc.message} {exc.context}")
        except Exception:
            logger.exception(f"{func.__name__} failed")
    return run


# ─── One decorator per cadence ────────────────────────────────────────────────

def _schedules(prefix: str, trigger: str = 'cron', **fixed):
    """A decorator that registers the job it wraps on one schedule.

    The job id is `prefix` and the function's own name, so a job declares its
    schedule where it is defined and APScheduler can tell two of them apart.
    Keyword arguments given to the decorator are the trigger's own; `fixed`
    carries the parts that belong to the cadence rather than to the caller.
    """
    def make(**kwargs):
        def decorator(func):
            guarded = _guarded(func)
            @wraps(func)
            @scheduler.task(trigger=trigger, id=f'{prefix}_{func.__name__}',
                            **fixed, **kwargs)
            def wrapper(*args, **kwargs):
                return guarded(*args, **kwargs)
            return wrapper
        return decorator
    return make


def crawl_task(minute=0):
    """Restricted to an off-peak window: crawling competes with users for the
    VNDB Kana API rate limit, so it is confined to the hours in CRAWL_HOURS (a
    cron hour expression, e.g. '3-6') interpreted in SCHEDULER_TIMEZONE. The job
    still runs once per hour, but only inside that window.

    `max_instances` and `coalesce` are stated rather than left to APScheduler's
    defaults: a crawl that overruns its hour must not be joined by the next one,
    and a run missed while the process was down is not worth catching up on.
    """
    hours = os.environ.get('CRAWL_HOURS', '3-6')
    return _schedules('crawl', max_instances=1, coalesce=True)(hour=hours, minute=minute)


def hourly_task(minute=0):
    return _schedules('hourly')(minute=minute)


def daily_task(hour=0, minute=0):
    return _schedules('daily')(hour=hour, minute=minute)


def weekly_task(day_of_week=0, hour=0, minute=0):
    """`day_of_week` is 0-6, Monday first."""
    return _schedules('weekly')(day_of_week=day_of_week, hour=hour, minute=minute)


def monthly_task(day=1, hour=0, minute=0):
    return _schedules('monthly')(day=day, hour=hour, minute=minute)


def workday_task(hour=9, minute=0):
    return _schedules('workday', day_of_week='mon-fri')(hour=hour, minute=minute)


def custom_interval_task(minutes=0, hours=0, days=0):
    """Interval trigger — fires every `minutes`/`hours`/`days` from start-up,
    where the others fire at wall-clock times."""
    return _schedules('interval', trigger='interval')(minutes=minutes, hours=hours, days=days)


def test_task(func):
    """Every 10 seconds — for checking that the scheduler is alive at all."""
    return _schedules('test', trigger='interval', max_instances=1)(seconds=10)(func)
