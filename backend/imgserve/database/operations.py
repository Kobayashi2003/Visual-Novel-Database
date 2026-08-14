"""The image table: one row per mirrored file.

A row is only written after the file is on disk, so a row without a file should
not exist. Every function reports failure as None; the task layer distinguishes
the causes.
"""

from imgserve import db
from imgserve.utils import download_image_to_disk
from .models import IMAGE_MODEL, ImageType
from .common import save_db_operation

@save_db_operation
def exists(type: str, id: str) -> bool:
    model = IMAGE_MODEL[type]
    return db.session.get(model, id) is not None

@save_db_operation
def get(type: str, id: str) -> ImageType | None:
    model = IMAGE_MODEL[type]
    return db.session.get(model, id)

@save_db_operation
def create(type: str, id: str, *, fast: bool = False) -> ImageType | None:
    """Download the file to disk, then insert the DB row.

    Returns None if the row already exists or the download failed. The DB row
    is only written after a successful download — there should never be a row
    without a file on disk."""
    if exists(type, id):
        return None
    if not download_image_to_disk(type, id, fast=fast):
        return None
    model = IMAGE_MODEL[type]
    image = model(id=id)
    db.session.add(image)
    db.session.commit()
    return image

@save_db_operation
def update(type: str, id: str, *, fast: bool = False) -> ImageType | None:
    """Re-download the file and bump updated_at."""
    image = get(type, id)
    if not image:
        return None
    if not download_image_to_disk(type, id, fast=fast):
        return None
    db.session.add(image)
    db.session.commit()
    return image

@save_db_operation
def delete(type: str, id: str) -> ImageType | None:
    image = get(type, id)
    if not image:
        return None
    db.session.delete(image)
    db.session.commit()
    return image
