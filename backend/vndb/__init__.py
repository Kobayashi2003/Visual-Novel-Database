from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.exceptions import HTTPException
from .config import Config
from .errors import http_error_code
from .extensions import (
    ExtSQLAchemy, ExtCache, ExtCelery, ExtAPScheduler
)


def create_app(config_class=Config, enable_scheduler=True):
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    global db
    global migrate
    global cache
    global scheduler
    global celery

    CORS(app, resources={r"/*": {
        "origins": app.config.get('CORS_ORIGINS', '*'),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type", "X-CSRFToken"],
        "max_age": 600
    }})

    db = ExtSQLAchemy(app)
    migrate = Migrate(app, db)
    cache = ExtCache(app)
    celery = ExtCelery(app)

    if enable_scheduler:
        scheduler = ExtAPScheduler(app)
        # Importing registers the jobs on the scheduler.
        from .schedule.simple import simple_schedule
        from .schedule.backup import backup_database_schedule
        from .schedule.fetch import fetch_new_schedule, fetch_backfill_schedule
    else:
        scheduler = None

    @app.errorhandler(Exception)
    def handle_exception(e):
        # A handler for Exception also catches HTTPException, which would turn
        # routing-level errors (404, 405, ...) into a 500.
        if isinstance(e, HTTPException):
            return jsonify(error=http_error_code(e.code), message=e.description), e.code
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify(error="internal_error", message="Internal server error"), 500

    from .routes import api_bp
    from .routes.admin import admin_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    from .database.commands import register_commands
    register_commands(app)

    return app
