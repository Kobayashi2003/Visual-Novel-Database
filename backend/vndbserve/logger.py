import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(name, log_file, level=logging.INFO):
    """Logger writing to a rotating file at `level`, and to the console at ERROR
    only — the console is shared with every other service under the launcher, so
    routine INFO would drown it."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 5, backupCount=5)  # 5 MB x 5
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Anchored to this file rather than the cwd, so every service's log lands in the
# same repo-root logs/ dir regardless of where it was launched from.
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'logs',
)
logger = setup_logger('logger', os.path.join(_LOG_DIR, 'vndbserve.log'))