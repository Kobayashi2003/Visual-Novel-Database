from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__, url_prefix='/')

# Errors are left to the app-level handler in vndbserve/__init__.py, which puts every
# HTTPException on the shared {error, message} shape.

@api_bp.route('', methods=['GET', 'TRACE'])
def hello_world():
    return jsonify({"message": "VNDB"})

from .resources import (
    vn_bp, staff_bp, tag_bp, trait_bp,
    character_bp, producer_bp, release_bp,
)
api_bp.register_blueprint(vn_bp)
api_bp.register_blueprint(character_bp)
api_bp.register_blueprint(producer_bp)
api_bp.register_blueprint(staff_bp)
api_bp.register_blueprint(tag_bp)
api_bp.register_blueprint(trait_bp)
api_bp.register_blueprint(release_bp)

from .tasks import task_bp
api_bp.register_blueprint(task_bp)

from .query import query_bp
api_bp.register_blueprint(query_bp)