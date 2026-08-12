"""Random-sampling fetch schedules - superseded by schedule/fetch.py.

These jobs pick random ids across the entire VNDB id range and fetch or
refresh them. They are kept for reference only: the import in vndb/__init__.py
is commented out, so they are no longer registered with the scheduler.
schedule/fetch.py replaces them with a deterministic, batched strategy.
"""

import time
import random

from .common import hourly_task
from vndb.search import search_remote, convert_remote_to_local
from vndb.database import MODEL_MAP, exists, create, update, updatable
from vndb.utils.ids import formatId

# (resource type, ids sampled per run) processed by random_fetch_schedule.
FETCH_COUNTS = [
    ('vn', 30),
    ('character', 30),
    # ('release', 30),
    # ('producer', 5),
    # ('staff', 5),
    # ('tag', 5),
    # ('trait', 5),
]

# (resource type, ids refreshed per run) processed by random_update_schedule.
UPDATE_COUNTS = [
    # ('vn', 3),
    # ('release', 3),
    # ('character', 3),
    # ('producer', 5),
    # ('staff', 5),
    # ('tag', 5),
    # ('trait', 5),
]

ID_DELAY = 10    # seconds between per-id API calls
TYPE_DELAY = 60  # seconds between resource types


@hourly_task()
def random_fetch_schedule():
    """Sample random ids per type: create the missing ones, refresh stale ones."""
    created = {}
    updated = {}

    def random_fetch(resource_type, fetch_count):
        total = search_remote(resource_type, {}, 'small', 1, 1, 'id', False, True)['count']
        ids = [formatId(resource_type, i) for i in random.sample(range(1, total + 1), fetch_count)]
        for resource_id in ids:
            try:
                if not exists(resource_type, resource_id):
                    if results := search_remote(resource_type, {'id': resource_id}, 'large')['results']:
                        # Remote payloads must be converted to the local schema
                        # before storage (drops relation/role/spoiler/... fields).
                        data = convert_remote_to_local(resource_type, results[0])
                        created[resource_id] = create(resource_type, resource_id, data) is not None
                    else:
                        created[resource_id] = False
                elif updatable(resource_type, resource_id):
                    if results := search_remote(resource_type, {'id': resource_id}, 'large')['results']:
                        data = convert_remote_to_local(resource_type, results[0])
                        updated[resource_id] = update(resource_type, resource_id, data) is not None
                    else:
                        updated[resource_id] = False
                else:
                    updated[resource_id] = False
                time.sleep(ID_DELAY)
            except Exception as e:
                print(f"Error fetching {resource_type} {resource_id}: {e}")

    for resource_type, fetch_count in FETCH_COUNTS:
        try:
            random_fetch(resource_type, fetch_count)
            time.sleep(TYPE_DELAY)
        except Exception as e:
            print(f"Error fetching {resource_type}: {e}")

    print({'created': created, 'updated': updated})


@hourly_task()
def random_update_schedule():
    """Refresh the lowest-id stale entries of each configured type."""
    updated = {}

    def random_update(resource_type, update_count):
        model = MODEL_MAP[resource_type]
        ids = [
            row.id for row in model.query
            .filter(model.deleted_at == None)
            .order_by(model.id)
            .limit(update_count)
            .all()
        ]
        for resource_id in ids:
            try:
                if updatable(resource_type, resource_id):
                    if results := search_remote(resource_type, {'id': resource_id}, 'large')['results']:
                        data = convert_remote_to_local(resource_type, results[0])
                        updated[resource_id] = update(resource_type, resource_id, data) is not None
                    else:
                        updated[resource_id] = False
                else:
                    updated[resource_id] = False
                time.sleep(ID_DELAY)
            except Exception as e:
                print(f"Error updating {resource_type} {resource_id}: {e}")

    for resource_type, update_count in UPDATE_COUNTS:
        try:
            random_update(resource_type, update_count)
            time.sleep(TYPE_DELAY)
        except Exception as e:
            print(f"Error updating {resource_type}: {e}")

    print({'updated': updated})
