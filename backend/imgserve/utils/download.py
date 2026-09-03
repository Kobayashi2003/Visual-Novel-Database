"""Fetching image bytes from t.vndb.org.

Retries with a backoff, since a failed image is worth one more try before a
visitor sees a broken card. Writes go through a temp file and a rename, so a
half-downloaded file can never be found on disk and mistaken for a cache hit: the
file's existence is the cache.

`fast=True` is the user-facing path, with fewer retries and a shorter timeout,
because someone is waiting on it.
"""

from typing import Optional, List, Dict

import httpx
import re
import os
import time
import uuid
from io import BytesIO
from functools import wraps

from imgserve.logger import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

from .path import get_image_path

# Request-path downloads (cache miss serving a live user) get a tight budget
# so a slow / dead upstream can't pin a Waitress worker for tens of seconds.
# Crawler / explicit POST-PUT downloads keep the original lenient settings.
FAST_TIMEOUT = 5.0
FAST_RETRIES = 1
FAST_RETRY_DELAY = 0.5

SLOW_TIMEOUT = 10.0
SLOW_RETRIES = 3
SLOW_RETRY_DELAY = 2.0


def _retry(max_retries, delay):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    if attempt == max_retries:
                        logger.warning(f"Giving up on {func.__name__} after "
                                       f"{max_retries} attempts: {e}")
                        return None
                    logger.info(f"Attempt {attempt} failed, retrying in {delay}s: {e}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


def _fetch(type: str, id: int, *, timeout: float) -> Optional[BytesIO]:
    if id < 1:
        raise ValueError("Invalid ID")
    dir = str(id).zfill(2)[-2:]
    url = f"https://t.vndb.org/{type}/{dir}/{id}.jpg"
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    # One line per image, so it is only worth having when something is being
    # traced — at INFO it buried every other line the service wrote.
    logger.debug(f"Downloaded image {url}")
    return BytesIO(response.content)


def download_image(type: str, id: int) -> Optional[BytesIO]:
    """Slow / lenient fetch. Used by the crawler and explicit POST/PUT paths."""
    @_retry(SLOW_RETRIES, SLOW_RETRY_DELAY)
    def go():
        return _fetch(type, id, timeout=SLOW_TIMEOUT)
    return go()


def _atomic_write(path: str, data: bytes) -> None:
    """Write data to path via temp file + rename so concurrent readers never
    see a half-written file. Same directory keeps the rename in-FS, hence
    atomic on every common OS."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def download_image_to_disk(type: str, id: int, *, fast: bool = False) -> bool:
    """Fetch (type, id) from t.vndb.org and store it atomically at
    get_image_path(type, id). `fast=True` is the request-path budget;
    `fast=False` is the lenient background budget."""
    path = get_image_path(type, id)
    # Cheap short-circuit: another worker may have just written this file
    # while we were on the way in. Avoids a wasted upstream fetch.
    if os.path.exists(path):
        return True

    if fast:
        retries, delay, timeout = FAST_RETRIES, FAST_RETRY_DELAY, FAST_TIMEOUT
    else:
        retries, delay, timeout = SLOW_RETRIES, SLOW_RETRY_DELAY, SLOW_TIMEOUT

    @_retry(retries, delay)
    def go():
        return _fetch(type, id, timeout=timeout)

    data = go()
    if data is None:
        return False
    try:
        _atomic_write(path, data.getvalue())
        return True
    except Exception as exc:
        logger.exception(f"Could not write image {type}/{id}: {exc}")
        return False


def download_and_save_image(url: str, folder: str) -> bool:
    url_pattern = r"https://t\.vndb\.org/(?P<type>(?:sf|sf\.t|ch|cv|cv\.t))/(?P<dir>\d{2})/(?P<id>\d*?(?P=dir)|\d)\.jpg"
    match = re.match(url_pattern, url)
    if not match:
        return False
    type = match.group('type')
    dir = match.group('dir')
    id = int(match.group('id'))

    try:
        image_path = os.path.join(folder, type, dir, f"{id}.jpg")
        if os.path.exists(image_path):
            return True
        image_data = download_image(type, id)
        if image_data is None:
            return False
        _atomic_write(image_path, image_data.getvalue())
        return True
    except Exception as exc:
        logger.exception(f"Could not download image {url}: {exc}")
        return False


def download_images(urls: List[str], folder: str) -> Dict[str, bool]:
    download_status = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(download_and_save_image, url, folder): url for url in urls}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                success = future.result()
                download_status[url] = success
            except Exception as exc:
                download_status[url] = False

    return download_status
