"""One task per image operation.

Each asks `exists()` before acting so its outcome says which of the several things
went wrong: the data layer reports every failure as None. See tasks/common for the
outcome vocabulary.
"""

import os
from typing import Dict, List, Any
from flask import current_app
from imgserve import celery
from imgserve.database import exists, create, update, delete
from imgserve.utils import download_image_to_disk, download_images, get_image_path
from imgserve.logger import logger
from .common import SUCCESS, NOT_FOUND, CONFLICT, UNAVAILABLE, ERROR


# create()/update()/delete() all report failure as None, which conflates several
# causes. Each task below asks exists() first, so the outcome it returns says
# which one actually happened.


@celery.task
def ensure_image_task(type: str, id: int) -> Dict[str, str]:
    """Make sure both the file and the DB row for (type, id) are present.

    Three cases:
      file present                -> SUCCESS (no-op)
      file missing, row present   -> re-download the file
      file missing, row missing   -> create() (downloads then inserts row)
    """
    try:
        if os.path.exists(get_image_path(type, id)):
            return SUCCESS
        if exists(type, id):
            return SUCCESS if download_image_to_disk(type, id) else UNAVAILABLE
        return SUCCESS if create(type, id) else UNAVAILABLE
    except Exception:
        logger.exception(f"ensure_image_task failed for {type}/{id}")
        return ERROR


@celery.task
def create_image_task(type: str, id: int) -> Dict[str, str]:
    try:
        if exists(type, id):
            return CONFLICT
        return SUCCESS if create(type, id) else UNAVAILABLE
    except Exception:
        logger.exception(f"create_image_task failed for {type}/{id}")
        return ERROR


@celery.task
def update_image_task(type: str, id: int) -> Dict[str, str]:
    try:
        if not exists(type, id):
            return NOT_FOUND
        return SUCCESS if update(type, id) else UNAVAILABLE
    except Exception:
        logger.exception(f"update_image_task failed for {type}/{id}")
        return ERROR


@celery.task
def delete_image_task(type: str, id: int) -> Dict[str, str]:
    try:
        return SUCCESS if delete(type, id) else NOT_FOUND
    except Exception:
        logger.exception(f"delete_image_task failed for {type}/{id}")
        return ERROR


@celery.task
def download_images_task(urls: List[str]) -> Dict[str, Any]:
    try:
        image_folder = current_app.config['IMAGE_FOLDER']
        results = download_images(urls, image_folder)
    except Exception:
        logger.exception(f"download_images_task failed for {len(urls)} url(s)")
        return ERROR
    return {'status': 'SUCCESS', 'results': results}
