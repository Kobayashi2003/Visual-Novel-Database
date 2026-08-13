from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate
from .config import Config
from .errors import http_error_code
from .extensions import ExtSQLAchemy, ExtAPScheduler


def create_app(config_class=Config, enable_scheduler=True):
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    global db
    global migrate
    global scheduler

    CORS(app, resources={r"/*": {
        "origins": app.config.get('CORS_ORIGINS', '*'),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "max_age": 600
    }})

    db = ExtSQLAchemy(app)

    # Two simple tables, so they are created on boot rather than through
    # migrations — the service is usable immediately after a fresh start. The
    # import is what registers them on db.metadata.
    from . import models  # noqa: F401
    with app.app_context():
        db.create_all()

    migrate = Migrate(app, db)

    # Reserved; no jobs registered yet.
    scheduler = ExtAPScheduler(app) if enable_scheduler else None

    @app.errorhandler(Exception)
    def handle_exception(e):
        # A handler for Exception also catches HTTPException, which would turn
        # routing-level errors (404, 405, ...) into a 500.
        if isinstance(e, HTTPException):
            return jsonify(error=http_error_code(e.code), message=e.description), e.code
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify(error="internal_error", message="Internal server error"), 500

    from .routes import api_bp
    app.register_blueprint(api_bp)

    from .cli import register_commands
    register_commands(app)

    return app
