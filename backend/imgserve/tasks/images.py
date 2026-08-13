import os
from typing import Dict, List, Any
from flask import current_app
from imgserve import celery
from imgserve.database import exists, create, update, delete
from imgserve.utils import download_image_to_disk, download_images, get_image_path
from imgserve.logger import logger
from .common import SUCCESS, FAILED, ERROR


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
            ok = download_image_to_disk(type, id)
            return SUCCESS if ok else FAILED
        result = create(type, id)
    except Exception:
        logger.exception(f"ensure_image_task failed for {type}/{id}")
        return ERROR
    return SUCCESS if result else FAILED


@celery.task
def create_image_task(type: str, id: int) -> Dict[str, str]:
    try:
        result = create(type, id)
    except Exception:
        logger.exception(f"create_image_task failed for {type}/{id}")
        return ERROR
    if not result:
        return FAILED
    return SUCCESS


@celery.task
def update_image_task(type: str, id: int) -> Dict[str, str]:
    try:
        result = update(type, id)
    except Exception:
        logger.exception(f"update_image_task failed for {type}/{id}")
        return ERROR
    if not result:
        return FAILED
    return SUCCESS


@celery.task
def delete_image_task(type: str, id: int) -> Dict[str, str]:
    try:
        result = delete(type, id)
    except Exception:
        logger.exception(f"delete_image_task failed for {type}/{id}")
        return ERROR
    if not result:
        return FAILED
    return SUCCESS


@celery.task
def download_images_task(urls: List[str]) -> Dict[str, Any]:
    try:
        image_folder = current_app.config['IMAGE_FOLDER']
        results = download_images(urls, image_folder)
    except Exception:
        logger.exception(f"download_images_task failed for {len(urls)} url(s)")
        return ERROR
    return {'status': 'SUCCESS', 'results': results}
