"""Accounts, sessions, collections and ratings: every database operation.

Client-facing failures are raised as `ValidationError` subclasses, each carrying
the error code and status the route layer reports. `save_db_operation` re-raises
those and swallows everything else, so an unexpected failure becomes None and a
logged traceback rather than a leaked message.

Also owns the session state that is not in Postgres: the JWT revocation blocklist
and the emailed verification codes, both in Redis with a TTL doing the expiry.
"""

import re
import hashlib
import secrets
from typing import List, Dict, Callable
from functools import wraps
from operator import itemgetter
from datetime import datetime, timezone

from flask import current_app

from userserve import db, redis_client
from .logger import logger
from .models import User, CATEGORY_MODEL, CategoryType, Rating

class ValidationError(Exception):
    """Base for input-validation failures meant to be reported to the client.

    Each subclass carries a stable `error_code` (so the frontend can branch on
    it) and a human-readable `message`. `save_db_operation` re-raises these
    instead of swallowing them, and `routes` turns them into a structured 4xx
    JSON response.
    """
    error_code = "validation_error"
    message = "Invalid input."
    http_status = 400


class UserNotFoundError(Exception):
    pass

class UserNotAdminError(Exception):
    pass


class InvalidPasswordError(ValidationError):
    error_code = "invalid_password"
    message = "Invalid password."

class InvalidAdminPasswordError(InvalidPasswordError):
    error_code = "invalid_admin_password"
    message = "Invalid admin password."

class InvalidOldPasswordError(InvalidPasswordError):
    error_code = "invalid_old_password"
    message = "The current password is incorrect."

class PasswordTooShortError(InvalidPasswordError):
    error_code = "password_too_short"
    message = "Password must be at least 8 characters."

class PasswordTooLongError(InvalidPasswordError):
    error_code = "password_too_long"
    message = "Password must be at most 128 characters."


class InvalidUsernameError(ValidationError):
    error_code = "invalid_username"
    message = "Invalid username."

class UsernameAlreadyExistsError(InvalidUsernameError):
    error_code = "username_taken"
    message = "This username is already taken."
    http_status = 409

class EmptyUsernameError(InvalidUsernameError):
    error_code = "username_empty"
    message = "Username cannot be empty."

class UsernameTooShortError(InvalidUsernameError):
    error_code = "username_too_short"
    message = "Username must be at least 3 characters."

class UsernameTooLongError(InvalidUsernameError):
    error_code = "username_too_long"
    message = "Username must be at most 32 characters."


class InvalidEmailError(ValidationError):
    error_code = "invalid_email"
    message = "Invalid email address."

class EmailAlreadyExistsError(InvalidEmailError):
    error_code = "email_taken"
    message = "This email is already registered."
    http_status = 409

class EmptyEmailError(InvalidEmailError):
    error_code = "email_empty"
    message = "Email cannot be empty."

class InvalidEmailFormatError(InvalidEmailError):
    error_code = "email_invalid_format"
    message = "Please enter a valid email address."


class InvalidVerificationCodeError(ValidationError):
    error_code = "invalid_verification_code"
    message = "The verification code is invalid or has expired."


class InvalidInvitationCodeError(ValidationError):
    error_code = "invalid_invitation_code"
    message = "The invitation code is invalid."


class CategoryNotFoundError(Exception):
    pass

class InvalidCategoryTypeError(Exception):
    pass

class InvalidCategoryNameError(Exception):
    pass

class CategoryNameTooLongError(InvalidCategoryNameError):
    pass

class AttemptToDeleteDefaultCategoryError(Exception):
    pass


class InvalidRatingError(ValidationError):
    error_code = "invalid_rating"
    message = "Rating must be an integer between 1 and 5."


def check_username(username: str) -> bool:
    username = username.strip()
    if not username:
        raise EmptyUsernameError
    if len(username) < 3:
        raise UsernameTooShortError
    if len(username) > 32:
        raise UsernameTooLongError
    user = get_user_by_username(username)
    if user:
        raise UsernameAlreadyExistsError
    return True

def check_password(password: str) -> bool:
    # Length is the only hard rule; symbols are allowed (and encouraged).
    if len(password) < 8:
        raise PasswordTooShortError
    if len(password) > 128:
        raise PasswordTooLongError
    return True

EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def check_email(email: str) -> bool:
    email = email.strip().lower()
    if not email:
        raise EmptyEmailError
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        raise InvalidEmailFormatError
    if get_user_by_email(email):
        raise EmailAlreadyExistsError
    return True

def check_category_name(category_name: str) -> bool:
    if len(category_name) > 32:
        raise CategoryNameTooLongError
    return True

def _code_key(email: str) -> str:
    return f"userserve:verify:{email.strip().lower()}"

def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()

def create_verification_code(email: str) -> str:
    """Generate a fresh 6-digit code for `email`, store it (hashed) in Redis
    with a TTL, and return it in plaintext so the caller can email it. A new
    code overwrites any previous one for the same email."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    redis_client.setex(
        _code_key(email),
        current_app.config['VERIFICATION_CODE_MAX_AGE'],
        _hash_code(code),
    )
    return code

def verify_email_code(email: str, code: str) -> bool:
    """Raise InvalidVerificationCodeError unless `code` matches the active code
    stored for `email`. Expiry is handled by the Redis key's TTL."""
    stored = redis_client.get(_code_key(email))
    if not stored or stored != _hash_code(code):
        raise InvalidVerificationCodeError
    return True

def verify_invitation_code(invitation_code: str) -> bool:
    """Raise InvalidInvitationCodeError unless `invitation_code` matches the
    code configured via INVITATION_CODE. An empty INVITATION_CODE disables the
    invite gate, so any value (including none) passes."""
    expected = current_app.config.get('INVITATION_CODE', '')
    if not expected:
        return True
    if not secrets.compare_digest((invitation_code or '').strip(), expected):
        raise InvalidInvitationCodeError
    return True

def save_db_operation(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError:
            # Validation failures are surfaced to the client, not swallowed.
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            logger.exception(f"{func.__name__} failed")
            return None
    return wrapper


@save_db_operation
def get_user(user_id: int) -> User | None:
    return User.query.get(user_id)

@save_db_operation
def get_user_by_username(username: str) -> User | None:
    return User.query.filter_by(username=username).first()

@save_db_operation
def get_user_by_email(email: str) -> User | None:
    return User.query.filter_by(email=email.strip().lower()).first()

@save_db_operation
def get_user_by_username_or_email(identifier: str) -> User | None:
    """Resolve a login identifier that may be either a username or an email.
    The username is tried first; an email fallback lets users sign in with
    whichever they remember."""
    identifier = identifier.strip()
    if not identifier:
        return None
    user = User.query.filter_by(username=identifier).first()
    if user:
        return user
    return User.query.filter_by(email=identifier.lower()).first()

@save_db_operation
def create_user(username: str, email: str, password: str, code: str, invitation_code: str = "") -> User | None:
    username = username.strip()
    email = email.strip().lower()
    verify_invitation_code(invitation_code)
    check_username(username)
    check_email(email)
    check_password(password)
    verify_email_code(email, code)
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def create_admin(username: str, email: str, password: str, admin_password: str) -> User | None:
    if admin_password != current_app.config['ADMIN_PASSWORD']:
        raise InvalidAdminPasswordError
    username = username.strip()
    email = email.strip().lower()
    check_username(username)
    check_email(email)
    check_password(password)
    user = User(username=username, email=email, is_admin=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def grant_admin_privileges(user_id: int, admin_password: str) -> User | None:
    if admin_password != current_app.config['ADMIN_PASSWORD']:
        raise InvalidAdminPasswordError
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    user.is_admin = True
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def revoke_admin_privileges(user_id: int, admin_password: str) -> User | None:
    if admin_password != current_app.config['ADMIN_PASSWORD']:
        raise InvalidAdminPasswordError
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    user.is_admin = False
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def update_user(user_id: int, username: str = None) -> User | None:
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    if username:
        username = username.strip()
        check_username(username)
        user.username = username
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def change_password(user_id: int, old_password: str, new_password: str) -> User | None:
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    if not user.check_password(old_password):
        raise InvalidOldPasswordError
    check_password(new_password)
    user.set_password(new_password)
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def change_email(user_id: int, new_email: str, code: str, password: str) -> User | None:
    """Rebind a user's email address. The current `password` authorises the
    change, and the verification `code` (sent to `new_email` beforehand) proves
    the new address belongs to the user."""
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    if not user.check_password(password):
        raise InvalidOldPasswordError
    new_email = new_email.strip().lower()
    # check_email enforces both the format rule and uniqueness; verify_email_code
    # confirms ownership of the new address.
    check_email(new_email)
    verify_email_code(new_email, code)
    user.email = new_email
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def reset_user_password(user_id: int, new_password: str) -> User | None:
    """Set a new password without verifying the old one — used by the email
    password-reset flow, where the user proves identity via the reset token."""
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    check_password(new_password)
    user.set_password(new_password)
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def delete_user(user_id: int, password: str) -> bool:
    """Permanently remove a user. The current `password` authorises the action —
    a missing or incorrect password raises InvalidOldPasswordError before any
    rows are touched."""
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    if not isinstance(password, str) or not user.check_password(password):
        raise InvalidOldPasswordError
    db.session.delete(user)
    db.session.flush()
    db.session.commit()
    return True


def _blocklist_key(jti: str) -> str:
    return f"userserve:jwt:blocked:{jti}"

def is_token_invalidated(jwt_payload: dict) -> bool:
    """Blocklist check for the JWT loader: True if the token's `jti` has been
    explicitly revoked (Redis), or if it was issued before the owning user's
    revocation cut-off (set on password change). Not wrapped by
    `save_db_operation` — a swallowed error must never make a revoked token
    look valid."""
    jti = jwt_payload.get('jti')
    if jti and redis_client.exists(_blocklist_key(jti)):
        return True
    user_id = jwt_payload.get('sub')
    issued_at = jwt_payload.get('iat')
    if user_id is not None and issued_at is not None:
        user = User.query.get(user_id)
        if user and user.tokens_revoked_at and issued_at < int(user.tokens_revoked_at.timestamp()):
            return True
    return False

def revoke_token(jwt_payload: dict) -> bool:
    """Add a decoded token's `jti` to the Redis blocklist. The entry's TTL is
    the token's remaining lifetime, so expired tokens drop out on their own —
    no scheduled cleanup needed. Idempotent: re-revoking just refreshes the
    same key."""
    jti = jwt_payload.get('jti')
    if not jti:
        return False
    exp = jwt_payload.get('exp')
    now = int(datetime.now(timezone.utc).timestamp())
    # Fall back to the longest possible token lifetime if `exp` is missing, so
    # we don't accidentally store a permanent entry.
    if exp is None:
        ttl = int(current_app.config['JWT_REFRESH_TOKEN_EXPIRES'].total_seconds())
    else:
        ttl = int(exp) - now
    if ttl <= 0:
        # Token already expired — JWT validation would reject it anyway.
        return True
    redis_client.setex(_blocklist_key(jti), ttl, "1")
    return True

@save_db_operation
def revoke_all_user_tokens(user_id: int) -> bool:
    """Invalidate every token previously issued to a user by advancing their
    revocation cut-off to now."""
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    user.tokens_revoked_at = datetime.now(timezone.utc)
    db.session.flush()
    db.session.commit()
    return True


@save_db_operation
def get_category(user_id: int, category_id: int, category_type: str) -> CategoryType | None:
    category_class = CATEGORY_MODEL.get(category_type)
    if not category_class:
        raise InvalidCategoryTypeError
    return category_class.query.filter_by(id=category_id, user_id=user_id).first()

@save_db_operation
def create_category(user_id: int, category_type: str, category_name: str) -> CategoryType | None:
    category_class = CATEGORY_MODEL.get(category_type)
    if not category_class:
        raise InvalidCategoryTypeError
    check_category_name(category_name)
    category = category_class(user_id=user_id, category_name=category_name)
    db.session.add(category)
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def update_category(user_id: int, category_id: int, category_type: str, category_name: str = None) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    if category_name:
        check_category_name(category_name)
        category.category_name = category_name
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def delete_category(user_id: int, category_id: int, category_type: str) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    if category.category_name == 'Default':
        raise AttemptToDeleteDefaultCategoryError
    db.session.delete(category)
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def clear_category(user_id: int, category_id: int, category_type: str) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    category.marks = []
    db.session.flush()
    db.session.commit()
    return category


@save_db_operation
def contains_mark(user_id: int, category_type: str, category_id: int, mark_id: int) -> bool:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    return any(mark['id'] == mark_id for mark in category.marks)

@save_db_operation
def add_mark_to_category(user_id: int, category_id: int, category_type: str, mark_id: int) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    new_mark = {"id": mark_id, "marked_at": datetime.now(timezone.utc).isoformat()}
    category.marks.append(new_mark)
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def add_marks_to_category(user_id: int, category_id: int, category_type: str, mark_ids: list[int]) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    new_marks = [{"id": mark_id, "marked_at": datetime.now(timezone.utc).isoformat()} for mark_id in mark_ids]
    category.marks.extend(new_marks)
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def remove_mark_from_category(user_id: int, category_id: int, category_type: str, mark_id: int) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    category.marks = [mark for mark in category.marks if mark['id'] != mark_id]
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def remove_marks_from_category(user_id: int, category_id: int, category_type: str, mark_ids: list[int]) -> CategoryType | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    category.marks = [mark for mark in category.marks if mark['id'] not in mark_ids]
    db.session.flush()
    db.session.commit()
    return category

@save_db_operation
def move_marks_to_category(user_id: int, category_id_from: int, category_id_to: int, category_type: str, mark_ids: list[int] = None) -> tuple[CategoryType, CategoryType] | None:
    category_from = get_category(user_id, category_id_from, category_type)
    if not category_from:
        raise CategoryNotFoundError
    category_to = get_category(user_id, category_id_to, category_type)
    if not category_to:
        raise CategoryNotFoundError
    if mark_ids:
        category_to.marks.extend([mark for mark in category_from.marks if mark['id'] in mark_ids])
        category_from.marks = [mark for mark in category_from.marks if mark['id'] not in mark_ids]
    else:
        category_to.marks.extend(category_from.marks)
        category_from.marks = []
    db.session.flush()
    db.session.commit()
    return category_from, category_to

@save_db_operation
def get_marks_from_category(user_id: int, category_id: int, category_type: str,
                            page: int = 1, limit: int = 100, sort: str = 'id',
                            reverse: bool = False, count: bool = True) -> List[Dict] | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError

    # Sort marks by the specified field
    sorted_marks = sorted(category.marks, key=itemgetter(sort), reverse=reverse)

    # Calculate pagination
    total = len(sorted_marks)
    start = (page - 1) * limit
    end = start + limit

    paginated_marks = sorted_marks[start:end]
    results = [{"id": str(mark['id']), "marked_at": mark['marked_at']} for mark in paginated_marks]
    more = end < total

    return {'results': results, 'more': more, 'count': total} if count else {'results': results, 'more': more}

@save_db_operation
def get_marks_from_category_without_pagination(user_id: int, category_id: int, category_type: str) -> Dict | None:
    """Every mark in one category. Keeps the paginated shape so callers can read
    it the same way as `get_marks_for_user`; `more` is always False."""
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    return {'results': category.marks, 'more': False, 'count': len(category.marks)}

@save_db_operation
def get_marks_for_user(user_id: int, category_type: str, category_id: int | None,
                       page: int = 1, limit: int = 24, sort: str = 'marked_at',
                       reverse: bool = True, count: bool = True) -> Dict | None:
    """
    Paginate marks for a user.

    `category_id` is None  → aggregate across all categories of `category_type`,
                             deduping by mark id and keeping the latest marked_at.
    `category_id` is int   → paginate within that single category.
    """
    if sort not in ('id', 'marked_at'):
        raise ValueError(f"Invalid sort field: {sort}")

    if category_id is not None:
        category = get_category(user_id, category_id, category_type)
        if not category:
            raise CategoryNotFoundError
        marks = list(category.marks)
    else:
        category_class = CATEGORY_MODEL.get(category_type)
        if not category_class:
            raise InvalidCategoryTypeError
        categories = category_class.query.filter_by(user_id=user_id).all()
        latest_by_id: Dict[int, Dict] = {}
        for cat in categories:
            for mark in cat.marks:
                existing = latest_by_id.get(mark['id'])
                if existing is None or mark['marked_at'] > existing['marked_at']:
                    latest_by_id[mark['id']] = mark
        marks = list(latest_by_id.values())

    sorted_marks = sorted(marks, key=itemgetter(sort), reverse=reverse)
    total = len(sorted_marks)
    page = max(1, page or 1)
    limit = max(1, limit or 24)
    start = (page - 1) * limit
    end = start + limit
    paginated = sorted_marks[start:end]
    results = [{"id": mark['id'], "marked_at": mark['marked_at']} for mark in paginated]
    more = end < total

    if count:
        return {'results': results, 'more': more, 'count': total}
    return {'results': results, 'more': more}

@save_db_operation
def get_categories_for_user(user_id: int, category_type: str) -> List[CategoryType] | None:
    category_class = CATEGORY_MODEL.get(category_type)
    if not category_class:
        raise InvalidCategoryTypeError
    return category_class.query.filter_by(user_id=user_id).all()

@save_db_operation
def search_categories(user_id: int, category_type: str, query: str) -> List[CategoryType] | None:
    category_class = CATEGORY_MODEL.get(category_type)
    if not category_class:
        raise InvalidCategoryTypeError
    return category_class.query.filter(
        category_class.user_id == user_id,
        category_class.category_name.ilike(f"%{query}%")
    ).all()


@save_db_operation
def is_marked(user_id: int, category_type: str, mark_id: int) -> bool:
    category_class = CATEGORY_MODEL.get(category_type)
    if not category_class:
        raise InvalidCategoryTypeError
    categories = category_class.query.filter_by(user_id=user_id).all()
    for category in categories:
        if any(mark['id'] == mark_id for mark in category.marks):
            return True
    return False

@save_db_operation
def are_marked(user_id: int, category_type: str, mark_ids: list[int]) -> dict[int, bool]:
    records = {
        mark_id: is_marked(user_id, category_type, mark_id) or False
        for mark_id in mark_ids
    }
    return records

@save_db_operation
def get_categories_by_mark(user_id: int, category_type: str, mark_id: int) -> List[int] | None:
    category_class = CATEGORY_MODEL.get(category_type)
    if not category_class:
        raise InvalidCategoryTypeError

    categories = category_class.query.filter_by(user_id=user_id).all()

    marked_categories = []

    for category in categories:
        if any(mark['id'] == mark_id for mark in category.marks):
            marked_categories.append(category.id)

    return marked_categories


@save_db_operation
def get_ratings_for_user(user_id: int, category_type: str) -> Dict[int, int] | None:
    if category_type not in CATEGORY_MODEL:
        raise InvalidCategoryTypeError
    ratings = Rating.query.filter_by(user_id=user_id, type=category_type).all()
    return {r.mark_id: r.rating for r in ratings}

@save_db_operation
def get_rating(user_id: int, category_type: str, mark_id: int) -> int | None:
    """Return the user's rating for a single mark, or 0 when unrated.
    A None return signals an operation failure (e.g. invalid type)."""
    if category_type not in CATEGORY_MODEL:
        raise InvalidCategoryTypeError
    rating = Rating.query.filter_by(user_id=user_id, type=category_type, mark_id=mark_id).first()
    return rating.rating if rating else 0

@save_db_operation
def set_rating(user_id: int, category_type: str, mark_id: int, rating: int) -> Rating | None:
    if category_type not in CATEGORY_MODEL:
        raise InvalidCategoryTypeError
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        raise InvalidRatingError
    record = Rating.query.filter_by(user_id=user_id, type=category_type, mark_id=mark_id).first()
    if record:
        record.rating = rating
    else:
        record = Rating(user_id=user_id, type=category_type, mark_id=mark_id, rating=rating)
        db.session.add(record)
    db.session.flush()
    db.session.commit()
    return record

@save_db_operation
def delete_rating(user_id: int, category_type: str, mark_id: int) -> bool | None:
    """Remove a rating (back to unrated). Idempotent — succeeds even if no
    rating existed."""
    if category_type not in CATEGORY_MODEL:
        raise InvalidCategoryTypeError
    record = Rating.query.filter_by(user_id=user_id, type=category_type, mark_id=mark_id).first()
    if record:
        db.session.delete(record)
        db.session.flush()
        db.session.commit()
    return True
