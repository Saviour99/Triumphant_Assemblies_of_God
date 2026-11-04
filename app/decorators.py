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
        if not current_user.is_active:
            return _signed_out_inactive_admin()
        return view_func(*args, **kwargs)
    return wrapped


def _signed_out_inactive_admin():
    """A deactivated admin still holding a session cookie is signed out on
    their next request (Flask-Login doesn't re-check is_active on session
    load, only at login_user())."""
    from flask import flash
    from flask_login import logout_user
    logout_user()
    flash('This account has been deactivated. Contact the developer.', 'danger')
    return redirect(url_for('admin.login'))


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
        if not current_user.is_active:
            return _signed_out_inactive_admin()
        return view_func(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Admin-only gate by role, e.g. @roles_required('developer', 'pastor').
    Section permissions don't matter here: an 'admin' account gets 403 even
    with every section ticked (used for site settings)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            from app.models import Admin
            if not current_user.is_authenticated:
                return redirect(url_for('admin.login'))
            if not isinstance(current_user, Admin) or current_user.role not in roles:
                abort(403)
            if not current_user.is_active:
                return _signed_out_inactive_admin()
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


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


def permission_required(section_key):
    """Section-level gate for admin routes. Implies @admin_required (anon ->
    admin login, non-Admin -> 403), then checks `current_user.can(key)`.
    Developer and pastor pass every section; role 'admin' passes only the
    sections in its permission list (see `Admin.can` in app/models.py).
    A denied admin is flashed and sent back to the dashboard (or gets a
    plain 403 on JSON endpoints under /admin/api/)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            from flask import flash, request
            from app.models import Admin
            if not current_user.is_authenticated:
                return redirect(url_for('admin.login'))
            if not isinstance(current_user, Admin):
                abort(403)
            if not current_user.is_active:
                return _signed_out_inactive_admin()
            if not current_user.can(section_key):
                if request.path.startswith('/admin/api/'):
                    abort(403)
                flash("You don't have access to that section.", 'danger')
                return redirect(url_for('admin.dashboard'))
            return view_func(*args, **kwargs)
        return wrapped
    return decorator
