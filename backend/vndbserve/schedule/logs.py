"""Keeping the `logs` table to a size worth reading.

Every search writes a row here (see search/common.py), so the table grows with
traffic and nothing ever removed anything: it had reached 608,000 rows and
515 MB, of which 599,000 were more than a month old.

Two windows rather than one, because the rows are not equally useful. Almost all
of them record a search that went fine, and a month of those is already more
than anyone reads; the few that record a failure are the ones worth having when
a problem is noticed weeks later, and keeping them costs nothing — they were
0.07% of the table.
"""

from datetime import datetime, timedelta, timezone

from flask import current_app

from vndbserve.database.logs import ROUTINE_LEVELS, delete_log_entries_before
from vndbserve.logger import logger
from .common import daily_task


@daily_task(hour=4, minute=30)
def prune_logs_schedule():
    """Drop log rows past their retention window.

    Runs after the crawl window (CRAWL_HOURS, 3-6 by default) has had its first
    hours, and well before the weekly backup, so the two never overlap on the
    same table. A window of zero or less keeps everything, which is how the
    pruning is turned off.
    """
    routine_days = current_app.config['LOG_RETENTION_DAYS']
    failure_days = current_app.config['LOG_FAILURE_RETENTION_DAYS']
    now = datetime.now(timezone.utc)
    removed = 0
    if routine_days > 0:
        removed += delete_log_entries_before(now - timedelta(days=routine_days),
                                             levels=ROUTINE_LEVELS)
    if failure_days > 0:
        removed += delete_log_entries_before(now - timedelta(days=failure_days))

    if removed:
        logger.info(f"[VNDB] prune_logs removed {removed} log entries "
                    f"(routine kept {routine_days}d, failures {failure_days}d)")
