import time
import random
from .common import hourly_task
from vndb.search import search_remote
from vndb.database import MODEL_MAP, formatId, exists, create, update, updatable 

@hourly_task()
def random_fetch_schedule():

    created = {}
    updated = {}

    def random_fetch(type: str, fetch_count: int = 5):
        count = search_remote(type, {}, 'small', 1, 1, 'id', False, True)['count']
        ids = [formatId(type, id) for id in random.sample(range(1, count + 1), fetch_count)]
        for id in ids:
            try:
                if not exists(type, id):
                    if remote_results := search_remote(type, {'id':id}, 'large')['results']:
                        created[id] = (create(type, id, remote_results[0]) is not None)
                    else:
                        created[id] = False
                elif updatable(type, id):
                    if remote_results := search_remote(type, {'id':id}, 'large')['results']:
                        updated[id] = (update(type, id, remote_results[0]) is not None)
                    else:
                        updated[id] = False
                else:
                    updated[id] = False
                time.sleep(10)
            except Exception as e:
                print(f"Error fetching {type} {id}: {e}")
    
    for type, fetch_count in [
        ('vn', 10), 
        ('release', 10), 
        ('character', 10), 
        # ('producer', 5), 
        # ('staff', 5), 
        # ('tag', 5), 
        # ('trait', 5)
    ]:
        try:
            random_fetch(type, fetch_count)
            time.sleep(60)
        except Exception as e:
            print(f"Error fetching {type}: {e}")
    
    print({'created': created, 'updated': updated})

@hourly_task()
def random_update_schedule():

    updated = {}

    def random_update(type: str, update_count: int = 5):
        model = MODEL_MAP[type]
        ids = [vn.id for vn in model.query.filter(model.deleted_at == None).order_by(model.id).limit(update_count).all()]
        for id in ids:
            try:
                if updatable(type, id):
                    if remote_results := search_remote(type, {'id':id}, 'large')['results']:
                        updated[id] = (update(type, id, remote_results[0]) is not None)
                    else:
                        updated[id] = False
                else:
                    updated[id] = False
                time.sleep(10)
            except Exception as e:
                print(f"Error updating {type} {id}: {e}")

    for type, update_count in [
        ('vn', 10), 
        ('release', 10), 
        ('character', 10), 
        # ('producer', 5), 
        # ('staff', 5), 
        # ('tag', 5), 
        # ('trait', 5)
    ]:
        try:
            random_update(type, update_count)
            time.sleep(60)
        except Exception as e:
            print(f"Error updating {type}: {e}")

    print({'updated': updated})