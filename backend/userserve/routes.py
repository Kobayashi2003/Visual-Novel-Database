"""The HTTP surface. Request and response shapes are in docs/api/userserve.yaml.

Unlike the other services this one authenticates, so every route is scoped to the
caller: reading or writing another user's record is 403, not 404.

`/auth/verify` is not for clients. It is the probe the Caddy edge runs against
every gated request for every other service, and the only place the caller's id
and admin flag are told to anything downstream.
"""

from flask import Blueprint, jsonify, make_response, request, current_app
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt,
    create_access_token, create_refresh_token, decode_token,
    set_access_cookies, set_refresh_cookies, unset_jwt_cookies,
)

from userserve import limiter
from .operations import (
    ValidationError,
    get_user, create_user, update_user, delete_user, change_password, change_email,
    get_user_by_username, get_user_by_username_or_email,
    get_user_by_email, reset_user_password, check_email, create_verification_code,
    revoke_token, revoke_all_user_tokens,
    get_category, create_category, update_category, delete_category, clear_category,
    search_categories,
    get_categories_by_mark, contains_mark, is_marked, are_marked,
    add_mark_to_category, remove_mark_from_category,
    add_marks_to_category, remove_marks_from_category,
    move_marks_to_category, get_marks_from_category,
    get_marks_from_category_without_pagination,
    get_marks_for_user,
    get_ratings_for_user, get_rating, set_rating, delete_rating,
)
from .security import generate_reset_token, verify_reset_token, password_fingerprint
from .mail import send_password_reset_email, send_verification_code_email

api_bp = Blueprint('api', __name__, url_prefix='/')

# 400/404/500 are left to the app-level handler in __init__.py, which puts every
# HTTPException on the shared {error, message} shape. Only the two cases needing
# more than the default wording are handled here.

@api_bp.errorhandler(429)
def ratelimit_exceeded(e):
    return jsonify(error="rate_limited", message="Too many requests. Please slow down and try again shortly."), 429

@api_bp.errorhandler(ValidationError)
def handle_validation_error(e):
    """Turn a validation failure into a structured 4xx response."""
    return jsonify(error=e.error_code, message=e.message), e.http_status

@api_bp.route('', methods=['GET', 'TRACE'])
def hello_world():
    return jsonify({"message": "USERSERVE"})


# ----------------------------------------
# Sessions
# ----------------------------------------

def _access_token(user_id, is_admin: bool):
    """The admin flag rides in the token so `/auth/verify` — which the edge runs
    on every gated request, including every image — stays a pure token check
    with no database lookup. The cost is that a change to the flag only takes
    effect when the access token next rotates."""
    return create_access_token(identity=user_id, additional_claims={'adm': bool(is_admin)})


def _issue_token_cookies(response, user):
    """Attach a fresh access + refresh cookie pair (and their CSRF tokens) to a
    response, starting an authenticated session for the given user."""
    set_access_cookies(response, _access_token(user.id, user.is_admin))
    set_refresh_cookies(response, create_refresh_token(identity=user.id))
    return response


@api_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    # The `username` field accepts either a username or an email address.
    identifier = data.get('username')
    password = data.get('password')
    if not isinstance(identifier, str) or not isinstance(password, str):
        return jsonify(error="missing_fields", message="Username (or email) and password are required."), 400
    user = get_user_by_username_or_email(identifier.strip())
    if user and user.check_password(password):
        return _issue_token_cookies(jsonify(username=user.username), user), 200
    return jsonify(error="invalid_credentials", message="Invalid username/email or password."), 401

@api_bp.route('/send_verification_code', methods=['POST'])
@limiter.limit("5 per hour")
def send_verification_code_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    email = data.get('email')
    if not isinstance(email, str):
        return jsonify(error="missing_fields", message="Email is required."), 400
    # Raises ValidationError for a bad format or an already-registered email.
    check_email(email)
    code = create_verification_code(email)
    send_verification_code_email(email, code)
    return jsonify(message="A verification code has been sent to your email."), 200

@api_bp.route('/register', methods=['POST'])
@limiter.limit("10 per hour")
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    code = data.get('code')
    invitation_code = data.get('invitation_code')
    if (not isinstance(username, str) or not isinstance(email, str)
            or not isinstance(password, str) or not isinstance(code, str)
            or not isinstance(invitation_code, str)):
        return jsonify(error="missing_fields", message="Username, email, password, verification code and invitation code are required."), 400
    # check_* helpers / verify_email_code / verify_invitation_code raise
    # ValidationError (handled above); a None return therefore means an
    # unexpected DB-level failure.
    user = create_user(username, email, password, code, invitation_code)
    if not user:
        return jsonify(error="registration_failed", message="Registration failed. Please try again."), 500
    return _issue_token_cookies(jsonify(username=user.username), user), 201

@api_bp.route('/refresh', methods=['POST'])
@limiter.limit("30 per minute")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    # The refresh token carries no admin flag, so the new access token has to
    # get it from the row. Once per rotation, not once per request.
    user = get_user(user_id)
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    response = jsonify(message="Access token refreshed")
    set_access_cookies(response, _access_token(user_id, user.is_admin))
    return response, 200

@api_bp.route('/logout', methods=['POST'])
@jwt_required(verify_type=False)
def logout():
    # Revoke the token used for this request (access or refresh)...
    revoke_token(get_jwt())
    # ...and the paired refresh token, decoded straight from its cookie.
    refresh_cookie = request.cookies.get(
        current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token_cookie')
    )
    if refresh_cookie:
        try:
            revoke_token(decode_token(refresh_cookie))
        except Exception:
            pass
    response = jsonify(message="Logged out")
    unset_jwt_cookies(response)
    return response, 200

@api_bp.route('/auth/verify', methods=['GET'])
@jwt_required()
def verify():
    """Auth probe for the edge's `forward_auth`: 204 = live session, 401 = reject.

    No DB lookup — this runs once per image and per audio range request, and the
    JWT (plus the blocklist loader) already answers the only question asked.
    """
    response = make_response('', 204)
    response.headers['X-User-Id'] = str(get_jwt_identity())
    # Copied upstream by the edge, so a service can gate an admin-only route
    # without holding any auth code of its own.
    response.headers['X-Is-Admin'] = 'true' if get_jwt().get('adm') else 'false'
    return response

# ----------------------------------------
# Accounts
# ----------------------------------------

@api_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user = get_user(get_jwt_identity())
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    return jsonify(dict(user)), 200


@api_bp.route('/u<username>', methods=['GET'])
@jwt_required()
def get_user_route(username):
    current_user_id = get_jwt_identity()
    user = get_user_by_username(username)
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    if current_user_id != user.id:
        return jsonify(error="unauthorized", message="You can only access your own account."), 403
    return jsonify(dict(user)), 200

@api_bp.route('/u<username>', methods=['PUT'])
@jwt_required()
def update_user_route(username):
    current_user_id = get_jwt_identity()
    user = get_user_by_username(username)
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    if current_user_id != user.id:
        return jsonify(error="unauthorized", message="You can only modify your own account."), 403
    data = request.json
    user = update_user(user.id, username=data.get('username'))
    if not user:
        return jsonify(error="update_failed", message="Could not update the profile."), 400
    return jsonify(dict(user)), 200

@api_bp.route('/u<username>', methods=['DELETE'])
@limiter.limit("10 per hour")
@jwt_required()
def delete_user_route(username):
    current_user_id = get_jwt_identity()
    user = get_user_by_username(username)
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    if current_user_id != user.id:
        return jsonify(error="unauthorized", message="You can only delete your own account."), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    password = data.get('password')
    if not isinstance(password, str) or not password:
        return jsonify(error="missing_fields", message="Current password is required to delete the account."), 400
    # A wrong password raises ValidationError (handled above); a None return
    # therefore means an unexpected DB-level failure.
    if not delete_user(user.id, password):
        return jsonify(error="delete_failed", message="Account deletion failed."), 500
    # The user row is gone — clear the auth cookies so the (now-orphaned) JWTs
    # don't keep a 404'ing session hanging around in the browser.
    response = jsonify(message="Account deleted")
    unset_jwt_cookies(response)
    return response, 200

@api_bp.route('/change_password', methods=['POST'])
@limiter.limit("20 per hour")
@jwt_required()
def change_password_route():
    user_id = get_jwt_identity()
    user = get_user(user_id)
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    if not isinstance(old_password, str) or not isinstance(new_password, str):
        return jsonify(error="missing_fields", message="Old and new passwords are required."), 400
    # An invalid old password / weak new password raises ValidationError;
    # a None return means an unexpected DB-level failure.
    updated = change_password(user_id, old_password, new_password)
    if not updated:
        return jsonify(error="password_change_failed", message="Password change failed."), 500
    # Invalidate every existing session, then re-issue cookies so this device
    # stays signed in.
    revoke_all_user_tokens(user_id)
    return _issue_token_cookies(jsonify(message="Password changed successfully"), user), 200

@api_bp.route('/change_email', methods=['POST'])
@limiter.limit("10 per hour")
@jwt_required()
def change_email_route():
    user_id = get_jwt_identity()
    user = get_user(user_id)
    if not user:
        return jsonify(error="user_not_found", message="User not found."), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    new_email = data.get('new_email')
    code = data.get('code')
    password = data.get('password')
    if not isinstance(new_email, str) or not isinstance(code, str) or not isinstance(password, str):
        return jsonify(error="missing_fields", message="New email, verification code and current password are required."), 400
    # A wrong password / taken email / bad code raises ValidationError (handled
    # above); a None return therefore means an unexpected DB-level failure.
    updated = change_email(user_id, new_email, code, password)
    if not updated:
        return jsonify(error="email_change_failed", message="Email change failed. Please try again."), 500
    return jsonify(email=updated.email), 200

@api_bp.route('/forgot_password', methods=['POST'])
@limiter.limit("5 per hour")
def forgot_password_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    email = data.get('email')
    if not isinstance(email, str):
        return jsonify(error="missing_fields", message="Email is required."), 400
    user = get_user_by_email(email)
    if user:
        reset_url = f"{current_app.config['FRONTEND_BASE_URL']}/reset-password?token={generate_reset_token(user)}"
        send_password_reset_email(user, reset_url)
    # Always 200 — never reveal whether an email is registered.
    return jsonify(message="If that email is registered, a reset link has been sent."), 200

@api_bp.route('/reset_password', methods=['POST'])
@limiter.limit("10 per hour")
def reset_password_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="Request body must be JSON."), 400
    token = data.get('token')
    new_password = data.get('new_password')
    if not isinstance(token, str) or not isinstance(new_password, str):
        return jsonify(error="missing_fields", message="Token and new password are required."), 400
    payload = verify_reset_token(token, current_app.config['RESET_TOKEN_MAX_AGE'])
    user = get_user(payload['uid']) if payload else None
    # The fingerprint check rejects links that were already used (the password,
    # and therefore the fingerprint, has since changed).
    if not user or password_fingerprint(user) != payload.get('fp'):
        return jsonify(error="invalid_reset_token", message="This reset link is invalid or has expired."), 400
    # check_password raises ValidationError (handled above); None means DB failure.
    updated = reset_user_password(user.id, new_password)
    if not updated:
        return jsonify(error="password_reset_failed", message="Password reset failed."), 500
    revoke_all_user_tokens(user.id)
    return jsonify(message="Your password has been reset. Please log in with your new password."), 200


# ----------------------------------------
# Categories — named collections of entities
# ----------------------------------------

@api_bp.route('/<string:type>/c', methods=['GET'])
@jwt_required()
def get_categories_for_user_route(type):
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
    return jsonify(error="category_create_failed", message="Could not create the category."), 400

@api_bp.route('/<string:type>/c<int:category_id>', methods=['GET'])
@jwt_required()
def get_category_route(type, category_id):
    user_id = get_jwt_identity()
    category = get_category(user_id, category_id, type)
    if category:
        return jsonify(dict(category)), 200
    return jsonify(error="category_not_found", message="No such category."), 404

@api_bp.route('/<string:type>/c<int:category_id>', methods=['PUT'])
@jwt_required()
def update_category_route(type, category_id):
    user_id = get_jwt_identity()
    data = request.json
    category = update_category(user_id, category_id, type, data.get('category_name'))
    if category:
        return jsonify(dict(category)), 200
    return jsonify(error="category_not_found", message="No such category."), 404

@api_bp.route('/<string:type>/c<int:category_id>', methods=['DELETE'])
@jwt_required()
def delete_category_route(type, category_id):
    user_id = get_jwt_identity()
    if delete_category(user_id, category_id, type):
        return jsonify(message="Category deleted"), 200
    return jsonify(error="category_not_found", message="No such category."), 404

@api_bp.route('/<string:type>/c<int:category_id>/clear', methods=['POST'])
@jwt_required()
def clear_category_route(type, category_id):
    user_id = get_jwt_identity()
    category = clear_category(user_id, category_id, type)
    if category:
        return jsonify(message="Category cleared"), 200
    return jsonify(error="category_not_found", message="No such category."), 404


# ----------------------------------------
# Marks — entities inside a collection
# ----------------------------------------

@api_bp.route('/<string:type>/c<int:category_id>/m<int:mark_id>', methods=['GET'])
@jwt_required()
def contains_mark_route(type, category_id, mark_id):
    user_id = get_jwt_identity()
    containsMark = contains_mark(user_id, type, category_id, mark_id)
    return jsonify(containsMark=containsMark), 200

@api_bp.route('/<string:type>/c<int:category_id>/m', methods=['POST'])
@jwt_required()
def add_mark_to_category_route(type, category_id):
    user_id = get_jwt_identity()
    data = request.json
    if 'mark_ids' in data:
        category = add_marks_to_category(user_id, category_id, type, data['mark_ids'])
    else:
        category = add_mark_to_category(user_id, category_id, type, data['mark_id'])
    if category:
        return jsonify(dict(category)), 201
    return jsonify(error="mark_update_failed", message="Could not add the mark to this category."), 400

@api_bp.route('/<string:type>/c<int:category_id>/m', methods=['DELETE'])
@jwt_required()
def remove_mark_from_category_route(type, category_id):
    user_id = get_jwt_identity()
    data = request.json
    if 'mark_ids' in data:
        category = remove_marks_from_category(user_id, category_id, type, data['mark_ids'])
    else:
        category = remove_mark_from_category(user_id, category_id, type, data['mark_id'])
    if category:
        return jsonify(dict(category)), 200
    return jsonify(error="mark_update_failed", message="Could not remove the mark from this category."), 400

@api_bp.route('/<string:type>/c<int:category_id>/m', methods=['GET'])
@jwt_required()
def get_marks_from_category_route(type, category_id):
    user_id = get_jwt_identity()
    marks = get_marks_from_category_without_pagination(user_id, category_id, type)
    return jsonify(marks), 200

@api_bp.route('/<string:type>/c/m', methods=['GET'])
@jwt_required()
def get_marks_for_user_route(type):
    user_id = get_jwt_identity()
    args = request.args
    cid_raw = args.get('cid', 'all')
    sort = args.get('sort', 'marked_at')
    try:
        page = max(1, int(args.get('page', 1)))
        limit = max(1, min(int(args.get('limit', 24)), 100))
        category_id = None if cid_raw == 'all' else int(cid_raw)
    except (TypeError, ValueError):
        return jsonify(error="invalid_request", message="page, limit and cid must be integers."), 400
    if sort not in ('id', 'marked_at'):
        return jsonify(error="invalid_request", message="sort must be one of: id, marked_at."), 400

    reverse = args.get('reverse', 'true').lower() == 'true'
    count = args.get('count', 'true').lower() == 'true'
    result = get_marks_for_user(
        user_id, type, category_id,
        page=page, limit=limit, sort=sort, reverse=reverse, count=count,
    )
    if result is None:
        return jsonify(error="not_found", message="No such category."), 404
    return jsonify(result), 200

@api_bp.route('/<string:type>/c/m', methods=['PUT'])
@jwt_required()
def move_marks_to_category_route(type):
    user_id = get_jwt_identity()
    data = request.json
    category_from_id = data['category_from_id']
    category_to_id = data['category_to_id']
    if category_from_id == category_to_id:
        return jsonify(error="invalid_request", message="Source and destination categories are the same."), 400
    category_from, category_to = move_marks_to_category(user_id, category_from_id, category_to_id, type, data['mark_ids'])
    if category_from and category_to:
        return jsonify({'category_from': dict(category_from), 'category_to': dict(category_to)}), 200
    return jsonify(error="mark_update_failed", message="Could not move the marks."), 400


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


# ----------------------------------------
# Ratings
# ----------------------------------------

@api_bp.route('/<string:type>/r', methods=['GET'])
@jwt_required()
def get_ratings_for_user_route(type):
    user_id = get_jwt_identity()
    ratings = get_ratings_for_user(user_id, type)
    if ratings is None:
        return jsonify(error="invalid_type", message="Unknown collection type."), 400
    # JSON object keys are serialised as strings; the frontend parses them back.
    return jsonify(ratings), 200

@api_bp.route('/<string:type>/r<int:mark_id>', methods=['GET'])
@jwt_required()
def get_rating_route(type, mark_id):
    user_id = get_jwt_identity()
    rating = get_rating(user_id, type, mark_id)
    if rating is None:
        return jsonify(error="invalid_type", message="Unknown collection type."), 400
    return jsonify(rating=rating), 200

@api_bp.route('/<string:type>/r<int:mark_id>', methods=['PUT'])
@jwt_required()
def set_rating_route(type, mark_id):
    user_id = get_jwt_identity()
    data = request.json
    # An out-of-range rating raises ValidationError (handled above); a None
    # return therefore means an unexpected DB-level failure.
    rating = set_rating(user_id, type, mark_id, data.get('rating'))
    if rating:
        return jsonify(dict(rating)), 200
    return jsonify(error="rating_update_failed", message="Could not set the rating."), 400

@api_bp.route('/<string:type>/r<int:mark_id>', methods=['DELETE'])
@jwt_required()
def delete_rating_route(type, mark_id):
    user_id = get_jwt_identity()
    if delete_rating(user_id, type, mark_id):
        return jsonify(message="Rating removed"), 200
    return jsonify(error="rating_update_failed", message="Could not remove the rating."), 400