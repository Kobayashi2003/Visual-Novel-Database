"""Cron decorators for the scheduled jobs.

Each wraps APScheduler's `scheduler.task` with a trigger and a job id derived
from the function name, so a job declares its own schedule at the definition
site. Importing a module that uses one is what registers the job — see the
imports in vndb/__init__.py.
"""

import os
from vndb import scheduler
from functools import wraps

def crawl_task(minute=0):
    """Restricted to an off-peak window: crawling competes with users for the
    VNDB Kana API rate limit, so it is confined to the hours in CRAWL_HOURS (a
    cron hour expression, e.g. '3-6') interpreted in SCHEDULER_TIMEZONE. The job
    still runs once per hour, but only inside that window."""
    hours = os.environ.get('CRAWL_HOURS', '3-6')
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'crawl_{func.__name__}',
                        hour=hours, minute=minute,
                        max_instances=1, coalesce=True)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def daily_task(hour=0, minute=0):
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'daily_{func.__name__}', hour=hour, minute=minute)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def weekly_task(day_of_week=0, hour=0, minute=0):
    """`day_of_week` is 0-6, Monday first."""
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'weekly_{func.__name__}', day_of_week=day_of_week, hour=hour, minute=minute)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def monthly_task(day=1, hour=0, minute=0):
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'monthly_{func.__name__}', day=day, hour=hour, minute=minute)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def hourly_task(minute=0):
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'hourly_{func.__name__}', minute=minute)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def custom_interval_task(minutes=0, hours=0, days=0):
    """Interval trigger — fires every `minutes`/`hours`/`days` from start-up,
    where the others fire at wall-clock times."""
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='interval', id=f'interval_{func.__name__}', minutes=minutes, hours=hours, days=days)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def workday_task(hour=9, minute=0):
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'workday_{func.__name__}', day_of_week='mon-fri', hour=hour, minute=minute)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

def test_task(func):
    """Every 10 seconds — for checking that the scheduler is alive at all."""
    @wraps(func)
    @scheduler.task(trigger='interval', id=f'test_{func.__name__}', seconds=10, max_instances=1)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
