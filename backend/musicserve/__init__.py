"""musicserve — VN theme-music file service.

Serves audio files (and their cover art) for visual novels out of a single
user-managed directory (MUSICSERVE_MUSIC_FOLDER). Files are named by vnid
("v17.mp3" or "17.mp3"); covers are sibling images with the same stem, with
embedded album art (ID3 APIC / MP4 covr / FLAC picture / Vorbis comment) as
the fallback. No database, no Celery — the directory IS the state.
"""

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from .errors import http_error_code

from .config import Config


def create_app(config_class=Config, enable_scheduler=True):
    # `enable_scheduler` is accepted for launcher-bootstrap symmetry with the
    # other services; musicserve has no scheduled jobs.
    app = Flask(__name__)

    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    CORS(app, resources={r"/*": {
        "origins": app.config.get('CORS_ORIGINS', '*'),
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"],
        "max_age": 600
    }})

    @app.errorhandler(Exception)
    def handle_exception(e):
        # Let routing-level HTTP errors (404 on unknown URLs, 405, ...) keep
        # their status as JSON instead of collapsing into a 500.
        if isinstance(e, HTTPException):
            return jsonify(error=http_error_code(e.code), message=e.description), e.code
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify(error="internal_error", message="Internal server error"), 500

    from .routes import api_bp
    app.register_blueprint(api_bp)

    return app
