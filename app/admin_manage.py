"""
Admin dashboard: account management (create / access / activate),
testimonies manager and events manager.

Routes register onto the existing `admin_bp` (endpoint names are
`admin.<function>`, URLs under /admin) — this module is imported at the
bottom of app/admin.py so the routes exist before the blueprint is
registered. Kept in its own file so account-permission and content work
doesn't collide with the auth/password code in app/admin.py.
"""

import os
import uuid
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from werkzeug.utils import secure_filename
from wtforms import (
    StringField, PasswordField, TextAreaField, BooleanField, SelectField, DateTimeLocalField
)
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, URL, ValidationError

from app import db, cache
from app.admin import admin_bp, _paginate
from app.decorators import developer_required, permission_required
from app.models import (
    Admin, AdminAccountLog, Testimony, Event,
    ADMIN_SECTION_GROUPS, ADMIN_SECTION_KEYS, ADMIN_SECTION_LABELS, DEFAULT_NEW_ADMIN_SECTIONS
)
from app.utils import sanitize_text, is_valid_image_file, is_valid_photo_file, get_testimonies
from app.testimony_submit import (
    photo_field, save_testimony_photo, remove_testimony_photo, TESTIMONY_MAX_CHARS
)


ROLE_CHOICES = [('admin', 'Admin'), ('pastor', 'Pastor'), ('developer', 'Developer')]
FULL_ACCESS_ROLES = ('developer', 'pastor')

# Templates read the section grouping (sidebar order) from this global.
admin_bp.add_app_template_global(ADMIN_SECTION_GROUPS, 'admin_section_groups')
admin_bp.add_app_template_global(ADMIN_SECTION_LABELS, 'admin_section_labels')


# ============ FORMS ============

class AdminAccountCreateForm(FlaskForm):
    username = StringField('Name / username', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField('Role', choices=ROLE_CHOICES, default='admin')
    password = PasswordField('Temporary password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')]
    )
    is_active = BooleanField('Active (can sign in)', default=True)


class TestimonyForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=255)])
    testimony = TextAreaField('Testimony', validators=[DataRequired(), Length(max=TESTIMONY_MAX_CHARS)])
    photo = photo_field('Photo')
    remove_photo = BooleanField('Remove current photo')


class EventForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    description = TextAreaField('Description', validators=[Optional()])
    start_at = DateTimeLocalField('Starts', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    end_at = DateTimeLocalField('Ends', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    location = StringField('Location', validators=[Optional(), Length(max=255)])
    image = FileField('Image', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only (jpg, png, gif).'),
        FileSize(max_size=2 * 1024 * 1024, message='Image must be 2MB or smaller.')
    ], description='JPG, PNG or GIF, up to 2 MB.')
    remove_image = BooleanField('Remove current image')
    is_published = BooleanField('Published on the website', default=True)

    def validate_end_at(self, field):
        if field.data and self.start_at.data and field.data < self.start_at.data:
            raise ValidationError('The end must be after the start.')


# ============ ACCOUNT HELPERS ============

def _posted_sections():
    wanted = set(request.form.getlist('permissions'))
    return [k for k in ADMIN_SECTION_KEYS if k in wanted]


def _lockout_problem(account, new_role, new_active):
    """Return an error message if this change would lock the developer out,
    else None. Rules: you can't demote or deactivate yourself, and at least
    one active developer must always remain."""
    if account.id == current_user.id and (new_role != 'developer' or not new_active):
        return "You can't deactivate your own account or change your own role."
    was_active_dev = account.role == 'developer' and account.is_active_account
    stays_active_dev = new_role == 'developer' and new_active
    if was_active_dev and not stays_active_dev:
        others = Admin.query.filter(
            Admin.id != account.id,
            Admin.role == 'developer',
            Admin.is_active_account.is_(True),
        ).count()
        if others == 0:
            return 'There must always be at least one active developer account.'
    return None


def _log_account_change(account, action, details=None):
    db.session.add(AdminAccountLog(
        admin_id=account.id,
        changed_by_id=current_user.id,
        action=action,
        details=details,
    ))


def _describe_sections(keys):
    return ', '.join(ADMIN_SECTION_LABELS[k] for k in keys) or 'none'


# ============ ACCOUNT MANAGEMENT (developer-only) ============

@admin_bp.route('/accounts/add', methods=['GET', 'POST'])
@developer_required
def account_add():
    form = AdminAccountCreateForm()
    selected = list(DEFAULT_NEW_ADMIN_SECTIONS)
    if form.validate_on_submit():
        selected = _posted_sections()
        email = form.email.data.lower().strip()
        username = sanitize_text(form.username.data)
        if Admin.query.filter((Admin.username == username) | (Admin.email == email)).first():
            flash('Another account already uses that username or email.', 'danger')
            return render_template('admin/account_add.html', form=form, selected=selected)

        account = Admin(username=username, email=email, role=form.role.data,
                        is_active_account=bool(form.is_active.data))
        account.set_password(form.password.data)
        if account.role == 'admin':
            account.set_permissions(selected)
        else:
            account.permissions = None  # full access by role
        db.session.add(account)
        db.session.flush()  # need account.id for the log row

        details = f"Role: {account.display_role}. Sections: " + (
            'all (by role)' if account.role in FULL_ACCESS_ROLES else _describe_sections(account.permission_list)
        )
        if not account.is_active_account:
            details += '. Created inactive.'
        _log_account_change(account, 'created', details)
        db.session.commit()
        flash(f'{account.display_role} account for {account.username} created. '
              'Give them the temporary password in person.', 'success')
        return redirect(url_for('admin.account_edit', account_id=account.id))
    elif request.method == 'POST':
        selected = _posted_sections()

    return render_template('admin/account_add.html', form=form, selected=selected)


@admin_bp.route('/accounts/<int:account_id>/access', methods=['POST'])
@developer_required
def account_access(account_id):
    """Role, active flag and section permissions for one account (the
    'Access' panel on the account edit page)."""
    account = Admin.query.get_or_404(account_id)
    new_role = request.form.get('role', account.role)
    if new_role not in dict(ROLE_CHOICES):
        flash('Unknown role.', 'danger')
        return redirect(url_for('admin.account_edit', account_id=account.id))
    new_active = request.form.get('is_active') == 'y'

    problem = _lockout_problem(account, new_role, new_active)
    if problem:
        flash(problem, 'danger')
        return redirect(url_for('admin.account_edit', account_id=account.id))

    changes = []
    old_role_label = account.display_role
    old_sections = account.permission_list
    old_active = account.is_active_account

    if new_role != account.role:
        account.role = new_role
        changes.append(('role_changed', f'Role: {old_role_label} → {account.display_role}'))

    if new_role in FULL_ACCESS_ROLES:
        account.permissions = None
    else:
        account.set_permissions(_posted_sections())
    new_sections = account.permission_list
    if new_sections != old_sections:
        added = [k for k in new_sections if k not in old_sections]
        removed = [k for k in old_sections if k not in new_sections]
        parts = []
        if added:
            parts.append('added ' + _describe_sections(added))
        if removed:
            parts.append('removed ' + _describe_sections(removed))
        changes.append(('permissions_changed', 'Sections ' + '; '.join(parts)))

    if new_active != old_active:
        account.is_active_account = new_active
        changes.append(('activated' if new_active else 'deactivated', None))

    if not changes:
        flash('No access changes to save.', 'info')
        return redirect(url_for('admin.account_edit', account_id=account.id))

    for action, details in changes:
        _log_account_change(account, action, details)
    db.session.commit()
    flash(f'Access for {account.username} updated.', 'success')
    return redirect(url_for('admin.account_edit', account_id=account.id))


@admin_bp.route('/accounts/<int:account_id>/toggle-active', methods=['POST'])
@developer_required
def account_toggle_active(account_id):
    """Soft activate/deactivate. Admin rows are never deleted (they own
    login-log and account-log history)."""
    account = Admin.query.get_or_404(account_id)
    new_active = not account.is_active_account
    problem = _lockout_problem(account, account.role, new_active)
    if problem:
        flash(problem, 'danger')
        return redirect(url_for('admin.accounts_list'))
    account.is_active_account = new_active
    _log_account_change(account, 'activated' if new_active else 'deactivated')
    db.session.commit()
    flash(f"{account.username} {'reactivated' if new_active else 'deactivated'}.", 'success')
    return redirect(url_for('admin.accounts_list'))


# ============ TESTIMONIES ============
# Moderation: member submissions arrive as 'pending' (app/testimony_submit.py)
# and only 'approved' rows are public. Admin-added testimonies are approved
# immediately.

TESTIMONY_STATUSES = ('pending', 'approved', 'rejected')


def _clear_testimony_cache():
    cache.delete_memoized(get_testimonies)
    cache.delete('blog_category_counts')


def _pending_testimony_count():
    try:
        return Testimony.query.filter_by(status='pending').count()
    except Exception:
        return 0


# Sidebar badge on the Testimonies link (admin/base.html).
admin_bp.add_app_template_global(_pending_testimony_count, 'pending_testimony_count')


def _apply_testimony_photo(testimony, form):
    """Handle the add/replace/remove photo controls. Returns False (after
    flashing) when the upload isn't a real image."""
    if form.photo.data:
        if not is_valid_photo_file(form.photo.data):
            flash('That file is not a JPG, PNG or WebP photo.', 'danger')
            return False
        previous = testimony.image_filename
        testimony.image_filename = save_testimony_photo(form.photo.data)
        testimony.image_url = None
        if previous:
            remove_testimony_photo(previous)
    elif form.remove_photo.data:
        remove_testimony_photo(testimony.image_filename)
        testimony.image_filename = None
        testimony.image_url = None
    return True


@admin_bp.route('/testimonies')
@permission_required('testimonies')
def testimonies_list():
    status_filter = request.args.get('status', '')
    if status_filter not in TESTIMONY_STATUSES:
        status_filter = ''
    query = Testimony.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    pagination = _paginate(query.order_by(Testimony.created_at.desc()))
    counts = {s: Testimony.query.filter_by(status=s).count() for s in TESTIMONY_STATUSES}
    return render_template('admin/testimonies_list.html', testimonies=pagination.items,
                           pagination=pagination, status_filter=status_filter, counts=counts)


@admin_bp.route('/testimonies/add', methods=['GET', 'POST'])
@permission_required('testimonies')
def testimony_add():
    form = TestimonyForm()
    if form.validate_on_submit():
        testimony = Testimony(
            name=sanitize_text(form.name.data),
            testimony=sanitize_text(form.testimony.data),
            status='approved',
            reviewed_at=datetime.utcnow(),
            reviewed_by_admin_id=current_user.id,
        )
        if _apply_testimony_photo(testimony, form):
            db.session.add(testimony)
            db.session.commit()
            _clear_testimony_cache()
            flash('Testimony added.', 'success')
            return redirect(url_for('admin.testimonies_list'))
    return render_template('admin/testimony_form.html', form=form, testimony=None)


@admin_bp.route('/testimonies/<int:testimony_id>/edit', methods=['GET', 'POST'])
@permission_required('testimonies')
def testimony_edit(testimony_id):
    testimony = Testimony.query.get_or_404(testimony_id)
    form = TestimonyForm(obj=testimony)
    if form.validate_on_submit():
        testimony.name = sanitize_text(form.name.data)
        testimony.testimony = sanitize_text(form.testimony.data)
        if _apply_testimony_photo(testimony, form):
            db.session.commit()
            _clear_testimony_cache()
            flash('Testimony updated.', 'success')
            return redirect(url_for('admin.testimonies_list', status=request.args.get('status') or None))
        db.session.rollback()
    return render_template('admin/testimony_form.html', form=form, testimony=testimony)


def _set_testimony_status(testimony_id, new_status, message):
    testimony = Testimony.query.get_or_404(testimony_id)
    testimony.status = new_status
    testimony.reviewed_at = datetime.utcnow()
    testimony.reviewed_by_admin_id = current_user.id
    db.session.commit()
    _clear_testimony_cache()
    flash(message.format(name=testimony.name), 'success')
    back = request.form.get('back_status', '')
    return redirect(url_for('admin.testimonies_list', status=back if back in TESTIMONY_STATUSES else None))


@admin_bp.route('/testimonies/<int:testimony_id>/approve', methods=['POST'])
@permission_required('testimonies')
def testimony_approve(testimony_id):
    return _set_testimony_status(testimony_id, 'approved', "{name}'s testimony is now on the website.")


@admin_bp.route('/testimonies/<int:testimony_id>/reject', methods=['POST'])
@permission_required('testimonies')
def testimony_reject(testimony_id):
    return _set_testimony_status(testimony_id, 'rejected', "{name}'s testimony was rejected. It stays off the website.")


@admin_bp.route('/testimonies/<int:testimony_id>/delete', methods=['POST'])
@permission_required('testimonies')
def testimony_delete(testimony_id):
    testimony = Testimony.query.get_or_404(testimony_id)  # single row, nothing references it
    photo = testimony.image_filename
    db.session.delete(testimony)
    db.session.commit()
    remove_testimony_photo(photo)
    _clear_testimony_cache()
    flash('Testimony deleted.', 'success')
    return redirect(url_for('admin.testimonies_list'))


# ============ EVENTS ============

def _save_event_image(file_storage):
    filename = secure_filename(file_storage.filename)
    stored_name = f"{uuid.uuid4().hex}_{filename}"
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'events')
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, stored_name))
    return f"uploads/events/{stored_name}"


def _remove_event_image(relative_path):
    if not relative_path:
        return
    absolute_path = os.path.join(current_app.root_path, 'static', relative_path)
    try:
        if os.path.exists(absolute_path):
            os.remove(absolute_path)
    except OSError:
        current_app.logger.warning(f'Could not remove file: {absolute_path}')


def _apply_event_form(event, form):
    event.title = sanitize_text(form.title.data)
    event.description = sanitize_text(form.description.data) or None
    event.start_at = form.start_at.data
    event.end_at = form.end_at.data or None
    event.location = sanitize_text(form.location.data) or None
    event.is_published = bool(form.is_published.data)


@admin_bp.route('/events')
@permission_required('events')
def events_list():
    from datetime import datetime
    now = datetime.now()
    upcoming_page = _paginate(Event.query.filter(Event.start_at >= now).order_by(Event.start_at.asc()), param='upcoming_page')
    past_page = _paginate(Event.query.filter(Event.start_at < now).order_by(Event.start_at.desc()), param='page')
    return render_template('admin/events_list.html', upcoming=upcoming_page.items, past=past_page.items,
                           upcoming_page=upcoming_page, past_page=past_page)


@admin_bp.route('/events/add', methods=['GET', 'POST'])
@permission_required('events')
def event_add():
    form = EventForm()
    if form.validate_on_submit():
        event = Event()
        if form.image.data:
            if not is_valid_image_file(form.image.data):
                flash('That file does not look like a valid image.', 'danger')
                return render_template('admin/event_form.html', form=form, event=None)
            event.image_filename = _save_event_image(form.image.data)
        _apply_event_form(event, form)
        db.session.add(event)
        db.session.commit()
        flash('Event added.', 'success')
        return redirect(url_for('admin.events_list'))
    return render_template('admin/event_form.html', form=form, event=None)


@admin_bp.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@permission_required('events')
def event_edit(event_id):
    event = Event.query.get_or_404(event_id)
    form = EventForm(obj=event)
    if form.validate_on_submit():
        if form.image.data:
            if not is_valid_image_file(form.image.data):
                flash('That file does not look like a valid image.', 'danger')
                return render_template('admin/event_form.html', form=form, event=event)
            _remove_event_image(event.image_filename)
            event.image_filename = _save_event_image(form.image.data)
        elif form.remove_image.data and event.image_filename:
            _remove_event_image(event.image_filename)
            event.image_filename = None
        _apply_event_form(event, form)
        db.session.commit()
        flash('Event updated.', 'success')
        return redirect(url_for('admin.events_list'))
    return render_template('admin/event_form.html', form=form, event=event)


@admin_bp.route('/events/<int:event_id>/delete', methods=['POST'])
@permission_required('events')
def event_delete(event_id):
    event = Event.query.get_or_404(event_id)  # single row, nothing references it
    image = event.image_filename
    db.session.delete(event)
    db.session.commit()
    _remove_event_image(image)
    flash('Event deleted.', 'success')
    return redirect(url_for('admin.events_list'))
