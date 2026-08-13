from flask import Flask, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate
from .config import Config
from .errors import http_error_code
from .extensions import (
    ExtSQLAchemy, ExtCache, ExtCelery, ExtAPScheduler, ExtRedis
)


def create_app(config_class=Config, enable_scheduler=True):
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    global db
    global migrate
    global cache
    global redis_client
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

    # Direct redis client for single-flight locking + the access ZSET. Its own
    # DB, so it never shares a keyspace with Flask-Caching.
    redis_client = ExtRedis(app)

    celery = ExtCelery(app)

    if enable_scheduler:
        scheduler = ExtAPScheduler(app)
        # Importing registers the jobs on the scheduler.
        from .schedule.backup import backup_database_schedule
        from .schedule.fetch import fetch_new_images_schedule, fetch_thumbnail_images_schedule
        from .schedule.access import flush_access_schedule
    else:
        scheduler = None

    @app.errorhandler(Exception)
    def handle_exception(e):
        # A handler for Exception also catches HTTPException, which would turn
        # every abort() — including serve_or_fetch_image's deliberate 503 — into
        # a 500.
        if isinstance(e, HTTPException):
            return jsonify(error=http_error_code(e.code), message=e.description), e.code
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify(error="internal_error", message="Internal server error"), 500

    from .routes import api_bp
    app.register_blueprint(api_bp)
    app.add_url_rule('/test', 'test', lambda: render_template('test.html'), methods=['GET'])

    from .database.commands import register_commands
    register_commands(app)

    return app
