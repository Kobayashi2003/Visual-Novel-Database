"""Cron decorators for the scheduled jobs.

Each wraps APScheduler's `scheduler.task` with a trigger and a job id derived
from the function name, so a job declares its own schedule at the definition
site. Importing a module that uses one is what registers the job — see the
imports in imgserve/__init__.py.
"""

import os
from imgserve import scheduler
from functools import wraps

def crawl_task(minute=0):
    """Restricted to an off-peak window: crawling competes with users for the
    remote rate limit, so it is confined to the hours in CRAWL_HOURS (a cron
    hour expression, e.g. '3-6') interpreted in SCHEDULER_TIMEZONE. The job
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

def test_task(func):
    @wraps(func)
    @scheduler.task(trigger='interval', id=f'test_{func.__name__}', seconds=10)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def hourly_task(minute=0):
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'hourly_{func.__name__}', minute=minute)
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
    def decorator(func):
        @wraps(func)
        @scheduler.task(trigger='cron', id=f'weekly_{func.__name__}', day_of_week=day_of_week, hour=hour, minute=minute)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator