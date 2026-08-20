from datetime import datetime, timezone
from flask import current_app

from .common import test_task
from vndbserve.logger import logger

# @test_task
def simple_schedule():
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    message = f"This is a simple scheduled print task. Current time: {current_time}"
    logger.info(message)
    current_app.logger.info(message)