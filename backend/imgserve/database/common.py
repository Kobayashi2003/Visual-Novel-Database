from typing import Callable
from functools import wraps
from imgserve import db
from imgserve.logger import logger
from .models import IMAGE_MODEL

def save_db_operation(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(type: str, *args, **kwargs):
        if type not in IMAGE_MODEL:
            return None
        try:
            return func(type, *args, **kwargs)
        except Exception:
            db.session.rollback()
            logger.exception(f"{func.__name__} failed")
            return None
    return wrapper