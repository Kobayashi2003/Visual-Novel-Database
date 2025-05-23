from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token 

api_bp = Blueprint('api', __name__, url_prefix='/')

@api_bp.errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e.description)), 400

@api_bp.errorhandler(404)
def not_found(e):
    return jsonify(error="Resource not found"), 404

@api_bp.errorhandler(500)
def server_error(e):
    return jsonify(error="An unexpected error occurred"), 500

@api_bp.route('', methods=['GET', 'TRACE'])
def hello_world():
    return jsonify({"message": "USERSERVE"})


from .operations import (
    get_user, create_user, update_user, delete_user, change_password, get_user_by_username,
    get_category, create_category, update_category, delete_category, clear_category, search_categories,
    get_categories_by_mark, contains_mark, is_marked, are_marked,
    add_mark_to_category, remove_mark_from_category,
    add_marks_to_category, remove_marks_from_category,
    move_marks_to_category, get_marks_from_category,
    get_marks_from_category_without_pagination, 
)


@api_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username'].strip()
    password = data['password']
    user = get_user_by_username(username)
    if user and user.check_password(password):
        access_token = create_access_token(identity=user.id)
        return jsonify({
            'access_token':access_token,
            'username': username 
        }), 200
    return jsonify(error="Invalid username or password"), 401

@api_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    user = create_user(data['username'], data['password'])
    if user:
        access_token = create_access_token(identity=user.id)
        return jsonify({
            'access_token':access_token,
            'username': data['username']
        }), 201
    return jsonify(error="Username already exists"), 400


@api_bp.route('/u<username>', methods=['GET'])
@jwt_required()
def get_user_route(username):
    current_user_id = get_jwt_identity()
    user = get_user_by_username(username)
    if not user:
        return jsonify(error="User not found"), 404
    if current_user_id != user.id:
        return jsonify(error="Unauthorized"), 403
    return jsonify(dict(user)), 200

@api_bp.route('/u<username>', methods=['PUT'])
@jwt_required()
def update_user_route(username):
    current_user_id = get_jwt_identity()
    user = get_user_by_username(username)
    if not user:
        return jsonify(error="User not found"), 404
    if current_user_id != user.id:
        return jsonify(error="Unauthorized"), 403
    data = request.json
    user = update_user(user.id, username=data.get('username'))
    if not user:
        return jsonify(error="Update failed"), 400
    return jsonify(dict(user)), 200

@api_bp.route('/u<username>', methods=['DELETE'])
@jwt_required()
def delete_user_route(username):
    current_user_id = get_jwt_identity()
    user = get_user_by_username(username)
    if not user:
        return jsonify(error="User not found"), 404
    if current_user_id != user.id:
        return jsonify(error="Unauthorized"), 403
    if not delete_user(user.id):
        return jsonify(message="Delete failed"), 400
    return jsonify(message="User deleted"), 200

@api_bp.route('/change_password', methods=['POST'])
@jwt_required()
def change_password_route():
    user_id = get_jwt_identity()
    user = get_user(user_id)
    if not user:
        return jsonify(error="User not found"), 400
    data = request.json
    user = change_password(user_id, data['old_password'], data['new_password'])
    if not user:
        return jsonify(error="Invalid old password"), 400
    return jsonify(message="Password changed successfully"), 200


@api_bp.route('/<string:type>/c', methods=['GET'])
@jwt_required()
def get_categories_route(type):
    user_id = get_jwt_identity()
    categories = search_categories(user_id, type, '')
    categories = [dict(c) for c in categories]
    return jsonify(categories), 200

@api_bp.route('/<string:type>/c', methods=['POST'])
@jwt_required()
def create_category_route(type):
    user_id = get_jwt_identity()
    data = request.json
    category = create_category(user_id, type, data['category_name'])
    if category:
        return jsonify(dict(category)), 201
    return jsonify(error="Failed to create category"), 400

@api_bp.route('/<string:type>/c<int:category_id>', methods=['GET'])
@jwt_required()
def get_category_route(type, category_id):
    user_id = get_jwt_identity()
    category = get_category(user_id, category_id, type)
    if category:
        return jsonify(dict(category)), 200
    return jsonify(error="Category not found"), 404

@api_bp.route('/<string:type>/c<int:category_id>', methods=['PUT'])
@jwt_required()
def update_category_route(type, category_id):
    user_id = get_jwt_identity()
    data = request.json
    category = update_category(user_id, category_id, type, data.get('category_name'))
    if category:
        return jsonify(dict(category)), 200
    return jsonify(error="Category not found"), 404

@api_bp.route('/<string:type>/c<int:category_id>', methods=['DELETE'])
@jwt_required()
def delete_category_route(type, category_id):
    user_id = get_jwt_identity()
    if delete_category(user_id, category_id, type):
        return jsonify(message="Category deleted"), 200
    return jsonify(error="Category not found"), 404

@api_bp.route('/<string:type>/c<int:category_id>/clear', methods=['POST'])
@jwt_required()
def clear_category_route(type, category_id):
    user_id = get_jwt_identity()
    category = clear_category(user_id, category_id, type)
    if category:
        return jsonify(message="Category cleared"), 200
    return jsonify(error="Category not found"), 404

@api_bp.route('/<string:type>/c<int:category_id>/m<int:mark_id>', methods=['GET'])
@jwt_required()
def contains_mark_route(type, category_id, mark_id):
    user_id = get_jwt_identity()
    containsMark = contains_mark(user_id, type, category_id, mark_id)
    return jsonify(containsMark=containsMark), 200

@api_bp.route('/<string:type>/c<int:category_id>/m', methods=['POST'])
@jwt_required()
def add_mark_route(type, category_id):
    user_id = get_jwt_identity()
    data = request.json
    if 'mark_ids' in data:
        category = add_marks_to_category(user_id, category_id, type, data['mark_ids'])
    else:
        category = add_mark_to_category(user_id, category_id, type, data['mark_id'])
    if category:
        return jsonify(dict(category)), 201
    return jsonify(error="Failed to add mark"), 400

@api_bp.route('/<string:type>/c<int:category_id>/m', methods=['DELETE'])
@jwt_required()
def remove_mark_route(type, category_id):
    user_id = get_jwt_identity()
    data = request.json
    if 'mark_ids' in data:
        category = remove_marks_from_category(user_id, category_id, type, data['mark_ids'])
    else:
        category = remove_mark_from_category(user_id, category_id, type, data['mark_id'])
    if category:
        return jsonify(dict(category)), 200
    return jsonify(error="Failed to remove mark"), 400

@api_bp.route('/<string:type>/c<int:category_id>/m', methods=['GET'])
@jwt_required()
def get_marks_route(type, category_id):
    user_id = get_jwt_identity()
    marks = get_marks_from_category_without_pagination(user_id, category_id, type)
    return jsonify(marks), 200

@api_bp.route('/<string:type>/c/m', methods=['PUT'])
@jwt_required()
def move_marks_route(type):
    user_id = get_jwt_identity()
    data = request.json
    category_from_id = data['category_from_id']
    category_to_id = data['category_to_id']
    if category_from_id == category_to_id:
        return jsonify(error="Category from and to are the same"), 400
    category_from, category_to = move_marks_to_category(user_id, category_from_id, category_to_id, type, data['mark_ids'])
    if category_from and category_to:
        return jsonify({'category_from': dict(category_from), 'category_to': dict(category_to)}), 200
    return jsonify(error="Failed to move marks"), 400


@api_bp.route('/<string:type>/m/is_marked', methods=['POST'])
@jwt_required()
def is_marked_route(type):
    user_id = get_jwt_identity()
    data = request.json
    markId = data['mark_id']
    isMarked = is_marked(user_id, type, markId)
    return jsonify(isMarked=isMarked), 200

@api_bp.route('/<string:type>/m/are_marked', methods=['POST'])
@jwt_required()
def are_marked_route(type):
    user_id = get_jwt_identity()
    data = request.json
    markIds = data['mark_ids']
    isMarked = are_marked(user_id, type, markIds)
    return jsonify(isMarked=isMarked), 200

@api_bp.route('/<string:type>/m<int:mark_id>/c', methods=['GET'])
@jwt_required()
def get_categories_by_mark_route(type, mark_id):
    user_id = get_jwt_identity()
    categoryIds = get_categories_by_mark(user_id, type, mark_id)
    return jsonify(categoryIds=categoryIds), 200

@api_bp.route('/<string:type>/m/c', methods=['POST'])
@jwt_required()
def get_categories_by_marks_route(type):
    user_id = get_jwt_identity()
    data = request.json
    markIds = data['mark_ids']
    categoryIds = {}
    for mark_id in markIds:
        categoryIds[mark_id] = get_categories_by_mark(user_id, type, mark_id)
    return jsonify(categoryIds=categoryIds), 200