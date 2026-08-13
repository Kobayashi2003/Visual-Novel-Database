from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate
from .config import Config
from .errors import http_error_code
from .extensions import ExtSQLAchemy, ExtAPScheduler

def create_app(config_class=Config, enable_scheduler=True):
    app = Flask(__name__)

    # ---------------------------
    # Load configuration
    # ---------------------------
    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    # Global variable declarations
    global db
    global migrate
    global scheduler

    # ----------------------------------------
    # Cors Initialization
    # ----------------------------------------
    CORS(app, resources={r"/*": {
        "origins": app.config.get('CORS_ORIGINS', '*'),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "max_age": 600
    }})

    # ----------------------------------------
    # Database Initialization
    # ----------------------------------------
    db = ExtSQLAchemy(app)

    # Register the model on the metadata and ensure its table exists. The other
    # services import their models only lazily (via routes), so their startup
    # create_all() is a no-op and they depend on migrations; transserve has a
    # single simple table, so we create it on boot to be usable immediately.
    from . import models  # noqa: F401  (registers DictionaryEntry on db.metadata)
    with app.app_context():
        db.create_all()

    # ----------------------------------------
    # Migrate Initialization
    # ----------------------------------------
    migrate = Migrate(app, db)

    # ----------------------------------------
    # Scheduler Initialization (reserved; no jobs registered yet)
    # ----------------------------------------
    if enable_scheduler:
        scheduler = ExtAPScheduler(app)
    else:
        scheduler = None

    # ----------------------------------------
    # Blueprint Registration
    # ----------------------------------------
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

    # ----------------------------------------
    # CLI Command Registration
    # ----------------------------------------
    from .cli import register_commands

    register_commands(app)

    return app
