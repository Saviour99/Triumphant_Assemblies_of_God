from functools import wraps

from flask import redirect, url_for, abort
from flask_login import current_user


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        from app.models import Admin
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login'))
        if not isinstance(current_user, Admin):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def developer_required(view_func):
    """Stricter than @admin_required: only the developer role may proceed.
    Used for account management (editing/resetting other admins' passwords)
    and the login-audit log — the plain 'admin' role should not see either."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        from app.models import Admin
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login'))
        if not isinstance(current_user, Admin) or current_user.role != 'developer':
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def member_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        from app.models import Member
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not isinstance(current_user, Member):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped
