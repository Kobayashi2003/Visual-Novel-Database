from flask import Flask, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate
from .config import Config
from .errors import http_error_code
from .extensions import (
    ExtSQLAchemy, ExtJWT, ExtAPScheduler, ExtLimiter, ExtRedis
)

import os
import secrets
import string


def create_app(config_class=Config, enable_scheduler=True):
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    global db
    global migrate
    global jwt
    global limiter
    global redis_client
    global scheduler

    CORS(app, resources={r"/*": {
        "origins": app.config['CORS_ORIGINS'],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-CSRF-TOKEN"],
        "expose_headers": ["Content-Type"],
        "max_age": 600
    }}, supports_credentials=True)

    db = ExtSQLAchemy(app)
    migrate = Migrate(app, db)
    jwt = ExtJWT(app)
    limiter = ExtLimiter(app)

    # Ephemeral store for email verification codes (TTL handles expiry) and the
    # JWT blocklist. Strings auto-decoded.
    redis_client = ExtRedis(app)

    if enable_scheduler:
        scheduler = ExtAPScheduler(app)
        # Importing registers the job on the scheduler.
        from .schedule import backup_database_schedule
    else:
        scheduler = None

    # ----------------------------------------
    # Authentication failures
    # ----------------------------------------

    from .operations import is_token_invalidated

    # Rejects tokens revoked by logout, or issued before a password change.
    @jwt.token_in_blocklist_loader
    def _token_revoked(jwt_header, jwt_payload):
        return is_token_invalidated(jwt_payload)

    # flask-jwt-extended answers with its own `{"msg": ...}` shape. These
    # loaders bring it onto the `{error, message}` contract shared by every
    # service, so a client can read an auth failure the same way as any other.
    def _auth_error(code, message, status=401):
        return jsonify(error=code, message=message), status

    @jwt.unauthorized_loader
    def _missing_token(reason):
        return _auth_error("unauthorized", "Not signed in.")

    @jwt.invalid_token_loader
    def _invalid_token(reason):
        return _auth_error("invalid_token", "The session token is malformed.")

    @jwt.expired_token_loader
    def _expired_token(jwt_header, jwt_payload):
        return _auth_error("token_expired", "The session has expired; sign in again.")

    @jwt.revoked_token_loader
    def _revoked_token(jwt_header, jwt_payload):
        return _auth_error("token_revoked", "The session has been revoked; sign in again.")

    @jwt.needs_fresh_token_loader
    def _stale_token(jwt_header, jwt_payload):
        return _auth_error("fresh_token_required", "This action requires a recent sign-in.")

    # ----------------------------------------
    # Admin password
    # ----------------------------------------

    admin_password = os.environ.get('ADMIN_PASSWORD')
    if not admin_password:
        alphabet = string.ascii_letters + string.digits
        admin_password = ''.join(secrets.choice(alphabet) for i in range(16))
    app.config['ADMIN_PASSWORD'] = admin_password
    app.logger.info(f"Admin password configured (auto-generated: {os.environ.get('ADMIN_PASSWORD') is None})")

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
    app.add_url_rule('/test', 'test', lambda: render_template('test.html'), methods=['GET'])

    from .cli import register_commands
    register_commands(app)

    return app
