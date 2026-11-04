"""
Member testimony submissions + shared testimony-photo helpers.

Signed-in members share a testimony (with an optional photo) from
/blog/testimonies. Submissions are stored as status='pending' and are
never public until an admin approves them in /admin/testimonies (see
app/admin_manage.py, which reuses the photo helpers below).

Routes register onto `main_bp`; this module is imported at the bottom of
app/routes.py.
"""

import os
import uuid
from datetime import datetime

from flask import redirect, url_for, flash, current_app
from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from werkzeug.utils import secure_filename
from wtforms import TextAreaField, BooleanField
from wtforms.validators import DataRequired, Length, Optional

from app import db, limiter
from app.decorators import member_required
from app.models import Member, Testimony
from app.routes import main_bp
from app.utils import sanitize_text, is_valid_photo_file

PHOTO_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
PHOTO_MAX_BYTES = 3 * 1024 * 1024
PHOTO_SUBDIR = 'testimonies'
TESTIMONY_MIN_CHARS = 40
TESTIMONY_MAX_CHARS = 2000


def photo_field(label='Photo'):
    return FileField(label, validators=[
        Optional(),
        FileAllowed(PHOTO_EXTENSIONS, 'Photos only: JPG, PNG or WebP.'),
        FileSize(max_size=PHOTO_MAX_BYTES, message='Photo must be 3 MB or smaller.'),
    ])


class TestimonySubmitForm(FlaskForm):
    testimony = TextAreaField('Your testimony', validators=[
        DataRequired(message='Write your testimony before sending it.'),
        Length(min=TESTIMONY_MIN_CHARS, max=TESTIMONY_MAX_CHARS,
               message=f'Keep it between {TESTIMONY_MIN_CHARS} and {TESTIMONY_MAX_CHARS} characters.'),
    ])
    photo = photo_field('Your photo')
    consent = BooleanField(
        'I agree to my name, photo and testimony being shown on the church website.',
        validators=[DataRequired(message='Tick the box to agree to your testimony being published.')],
    )


# ============ Photo helpers (shared with the admin routes) ============

def save_testimony_photo(file_storage):
    """Save an already-validated upload under static/uploads/testimonies/
    with a random name. Returns the static/-relative path."""
    original = secure_filename(file_storage.filename or '')
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else 'jpg'
    if ext not in PHOTO_EXTENSIONS:
        ext = 'jpg'
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], PHOTO_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, stored_name))
    return f"uploads/{PHOTO_SUBDIR}/{stored_name}"


def remove_testimony_photo(relative_path):
    """Delete one stored testimony photo. Refuses anything outside
    static/uploads/testimonies/ (defence against a tampered path)."""
    if not relative_path or not relative_path.startswith(f'uploads/{PHOTO_SUBDIR}/'):
        return
    photos_dir = os.path.realpath(os.path.join(current_app.config['UPLOAD_FOLDER'], PHOTO_SUBDIR))
    target = os.path.realpath(os.path.join(current_app.static_folder, relative_path))
    if os.path.dirname(target) != photos_dir:
        return
    try:
        os.remove(target)
    except OSError:
        pass


def _member_rate_key():
    if current_user.is_authenticated and isinstance(current_user, Member):
        return f"testimony-member:{current_user.id}"
    from flask_limiter.util import get_remote_address
    return get_remote_address()


# ============ Routes ============

@main_bp.route('/blog/testimonies/share', methods=['POST'])
@member_required
@limiter.limit('3 per hour', key_func=_member_rate_key)
def testimony_submit():
    form = TestimonySubmitForm()
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for err in errors:
                flash(err if isinstance(err, str) else 'Check the form and try again.', 'danger')
        return redirect(url_for('main.blog_testimonies') + '#share')

    image_filename = None
    if form.photo.data:
        if not is_valid_photo_file(form.photo.data):
            flash('That file is not a JPG, PNG or WebP photo.', 'danger')
            return redirect(url_for('main.blog_testimonies') + '#share')
        image_filename = save_testimony_photo(form.photo.data)

    text = sanitize_text(form.testimony.data)
    if len(text) < TESTIMONY_MIN_CHARS:
        if image_filename:
            remove_testimony_photo(image_filename)
        flash(f'Keep it between {TESTIMONY_MIN_CHARS} and {TESTIMONY_MAX_CHARS} characters.', 'danger')
        return redirect(url_for('main.blog_testimonies') + '#share')

    now = datetime.utcnow()
    db.session.add(Testimony(
        name=sanitize_text(current_user.full_name)[:255] or 'Church member',
        testimony=text,
        image_filename=image_filename,
        status='pending',
        member_id=current_user.id,
        submitted_at=now,
        created_at=now,
    ))
    db.session.commit()
    flash('Thank you for sharing your testimony. The pastoral team will review it '
          'before it appears on the website.', 'success')
    return redirect(url_for('main.blog_testimonies') + '#share')


@main_bp.app_template_global('my_testimonies')
def my_testimonies():
    """The signed-in member's own submissions (any status), newest first.
    Used on the member profile page."""
    if not (current_user.is_authenticated and isinstance(current_user, Member)):
        return []
    return (Testimony.query.filter_by(member_id=current_user.id)
            .order_by(Testimony.created_at.desc()).limit(20).all())
