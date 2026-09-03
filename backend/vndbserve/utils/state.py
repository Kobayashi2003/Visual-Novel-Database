"""Small JSON files that outlive a run, such as the crawl cursors.

Written through a rename so a crash cannot leave one half-written: the reader
falls back to an empty state, and an empty state costs whatever the file was
tracking.
"""

import json
import os
import threading


def load_state(path: str) -> dict:
    """The saved state, or an empty one.

    A missing file is a first run. A file that will not parse is lost progress,
    which is reported rather than absorbed — whatever it was tracking starts
    over.
    """
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        from vndbserve.logger import logger
        logger.exception(f"State at {path} could not be read; it starts over")
        return {}


def save_state(path: str, state: dict) -> None:
    """Write it whole, or leave the previous one in place.

    Writing in place truncates first, so an interrupted run would leave a file
    that no longer parses. The rename is what makes the swap atomic.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Unique per writer: a fixed name would have two concurrent saves writing
    # the same file, and the rename would publish whichever half won.
    tmp = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        from vndbserve.logger import logger
        logger.exception(f"State could not be saved to {path}")
        try:
            os.remove(tmp)
        except OSError:
            pass
