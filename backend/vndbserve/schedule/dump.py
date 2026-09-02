"""Daily pull of the published dumps.

VNDB republishes them around 08:00 UTC — 16:00 in Asia/Shanghai — so this runs
after that, and the ingest itself is a no-op when the file has not actually
changed since the last run.
"""

from .common import daily_task
from vndbserve.tasks.dump import ARCHIVE_SOURCES, SOURCES, ingest_dump_task


@daily_task(hour=17, minute=0)
def dump_ingest_schedule():
    # Queued rather than run here: a whole snapshot takes long enough that the
    # scheduler thread should not be holding it.
    for resource_type in (*SOURCES, *ARCHIVE_SOURCES):
        ingest_dump_task.delay(resource_type)
