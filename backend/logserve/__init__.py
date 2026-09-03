"""logserve — developer-facing diagnostics over the vndbserve `logs` table.

The vndbserve local/remote search backends persist an entry per query into the
`logs` table (see vndbserve.search.common.log_search). logserve is a small,
read/prune-side Flask API over that same table: it lets a developer query,
filter, inspect, delete and *replay* those recorded searches.

It is intentionally a dev tool: it connects to the vndbserve database directly and
is NOT published through the Caddy edge (../../Caddyfile.snippet has no route for
it), so it is only reachable on its loopback dev port.
"""

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import ExtSQLAlchemy


def create_app(config_class=Config, enable_scheduler=True):
    # `enable_scheduler` is accepted for launcher-bootstrap symmetry with the
    # other services; logserve has no scheduled jobs.
    app = Flask(__name__)

    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    # Global variable declaration (mirrors the other services' db exposure so
    # `from logserve import db` works in models/operations/replay).
    global db

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
    db = ExtSQLAlchemy(app)

    # Register the model on the metadata. No create_all(): the `logs` table is
    # owned by vndbserve's migrations; logserve only reads/prunes it.
    from . import models  # noqa: F401  (registers LogEntry on db.metadata)

    @app.errorhandler(Exception)
    def handle_exception(e):
        # Let routing-level HTTP errors keep their status as JSON.
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify(error="Internal server error"), 500

    from .routes import api_bp
    app.register_blueprint(api_bp)

    return app
