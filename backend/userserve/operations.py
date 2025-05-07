from typing import List, Dict, Callable
from functools import wraps
from operator import itemgetter
from datetime import datetime, timezone

from flask import current_app

from userserve import db
from .models import User, CATEGORY_MODEL, CategoryType

class UserNotFoundError(Exception):
    pass

class UserNotAdminError(Exception):
    pass

class InvalidPasswordError(Exception):
    pass

class InvalidAdminPasswordError(InvalidPasswordError):
    pass

class InvalidOldPasswordError(InvalidPasswordError):
    pass

class PasswordTooShortError(InvalidPasswordError):
    pass

class PasswordTooLongError(InvalidPasswordError):
    pass

class PasswordNotAlphanumericError(InvalidPasswordError):
    pass

class InvalidUsernameError(Exception):
    pass

class UsernameAlreadyExistsError(InvalidUsernameError):
    pass

class EmptyUsernameError(InvalidUsernameError):
    pass

class UsernameTooShortError(InvalidUsernameError):
    pass

class UsernameTooLongError(InvalidUsernameError):
    pass


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
    if len(password) < 8:
        raise PasswordTooShortError
    if len(password) > 128:
        raise PasswordTooLongError
    if not password.isalnum():
        raise PasswordNotAlphanumericError
    return True

def check_category_name(category_name: str) -> bool:
    if len(category_name) > 32:
        raise CategoryNameTooLongError
    return True

def save_db_operation(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            db.session.rollback()
            print(f"Error in {func.__name__}: {str(e)}")
            return None
    return wrapper


@save_db_operation
def get_user(user_id: int) -> User | None:
    return User.query.get(user_id)

@save_db_operation
def get_user_by_username(username: str) -> User | None:
    return User.query.filter_by(username=username).first()

@save_db_operation
def create_user(username: str, password: str) -> User | None:
    check_username(username)
    check_password(password)
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.commit()
    return user

@save_db_operation
def create_admin(username: str, password: str, admin_password: str) -> User | None:
    if admin_password != current_app.config['ADMIN_PASSWORD']:
        raise InvalidAdminPasswordError
    check_username(username)
    check_password(password)
    user = User(username=username, is_admin=True)
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
def delete_user(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        raise UserNotFoundError
    db.session.delete(user)
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
    
    # Paginate the marks
    paginated_marks = sorted_marks[start:end]
    
    # Extract required fields
    results = [{"id": str(mark['id']), "marked_at": mark['marked_at']} for mark in paginated_marks]
    
    # Check if there are more results
    more = end < total
    
    return {'results': results, 'more': more, 'count': total} if count else {'results': results, 'more': more}

@save_db_operation
def get_marks_from_category_without_pagination(user_id: int, category_id: int, category_type: str) -> List[Dict] | None:
    category = get_category(user_id, category_id, category_type)
    if not category:
        raise CategoryNotFoundError
    # return category.marks
    return {'results': category.marks, 'more': False, 'count': len(category.marks)}

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
        mark_id: is_marked(user_id, category_type, mark_id)
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
