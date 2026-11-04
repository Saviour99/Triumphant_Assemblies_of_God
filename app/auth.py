"""
Member-facing authentication blueprint: register / login / logout /
profile / password reset for the public site.
"""

import os
import uuid

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.utils import secure_filename

from app import db, limiter
from app.decorators import member_required
from app.email_utils import send_password_reset
from app.forms import (
    MemberRegisterForm, MemberLoginForm,
    MemberForgotPasswordForm, MemberResetPasswordForm, MemberAvatarForm
)
from app.models import Member, Giving
from app.security import (
    safe_next_url, external_url, password_fingerprint, fingerprints_match,
    burn_password_check, bind_session_to_password
)
from app.utils import sanitize_text, is_valid_image_file

auth_bp = Blueprint('auth', __name__, url_prefix='/members')

RESET_SALT = 'member-password-reset'
RESET_TOKEN_MAX_AGE = 1800  # seconds (30 minutes)


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _remove_old_avatar(relative_path):
    """Delete a previously uploaded avatar under static/uploads/avatars/.
    Refuses anything outside that folder (defence against a tampered path)."""
    if not relative_path or not relative_path.startswith('uploads/avatars/'):
        return
    avatars_dir = os.path.realpath(os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars'))
    target = os.path.realpath(os.path.join(current_app.static_folder, relative_path))
    if os.path.dirname(target) != avatars_dir:
        return
    try:
        os.remove(target)
    except OSError:
        pass


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def register():
    # Only redirect if they're already logged in as a Member — an
    # authenticated Admin/Developer browsing the public site should still
    # be able to view this page instead of being bounced to a 403.
    if current_user.is_authenticated and isinstance(current_user, Member):
        return redirect(url_for('auth.profile'))

    form = MemberRegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if not Member.query.filter_by(email=email).first():
            member = Member(
                full_name=sanitize_text(form.full_name.data),
                email=email,
                phone=form.phone.data.strip() if form.phone.data else None
            )
            member.set_password(form.password.data)
            db.session.add(member)
            db.session.commit()
        # Same response whether or not the email was already registered, so
        # the form can't be used to discover who has an account.
        flash('Registration received. Please log in. If you already had an account '
              'with this email, use "Forgot password" to regain access.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute;50 per hour', methods=['POST'])
def login():
    if current_user.is_authenticated and isinstance(current_user, Member):
        return redirect(url_for('auth.profile'))

    form = MemberLoginForm()
    if form.validate_on_submit():
        member = Member.query.filter_by(email=form.email.data.lower().strip()).first()
        if member is None:
            burn_password_check(form.password.data)  # equalise timing
        elif member.check_password(form.password.data):
            if not member.is_active_member:
                flash('This account has been deactivated. Contact the church office.', 'danger')
                return render_template('auth/login.html', form=form)
            login_user(member)
            bind_session_to_password(member)
            next_url = safe_next_url(request.args.get('next'))
            return redirect(next_url or url_for('auth.profile'))
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
def logout():
    # POST-only (CSRF-protected by Flask-WTF's global CSRFProtect) so a
    # third-party page can't log members out with an <img src=...>.
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@member_required
def profile():
    form = MemberAvatarForm()
    if form.validate_on_submit():
        if form.avatar.data:
            if not is_valid_image_file(form.avatar.data):
                flash('That file does not look like a valid image.', 'danger')
                return redirect(url_for('auth.profile'))

            filename = secure_filename(form.avatar.data.filename)
            stored_name = f"{uuid.uuid4().hex}_{filename}"
            dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(dest_dir, exist_ok=True)
            form.avatar.data.save(os.path.join(dest_dir, stored_name))
            previous = current_user.avatar_filename
            current_user.avatar_filename = f"uploads/avatars/{stored_name}"
            db.session.commit()
            _remove_old_avatar(previous)
            flash('Profile photo updated.', 'success')
        return redirect(url_for('auth.profile'))
    elif request.method == 'POST' and form.errors:
        for errors in form.errors.values():
            for err in errors:
                flash(err, 'danger')
        return redirect(url_for('auth.profile'))

    page = request.args.get('page', 1, type=int)
    pagination = current_user.donations.order_by(Giving.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template(
        'auth/profile.html', member=current_user, form=form,
        pagination=pagination, donations=pagination.items
    )


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def forgot_password():
    form = MemberForgotPasswordForm()
    if form.validate_on_submit():
        member = Member.query.filter_by(email=form.email.data.lower().strip()).first()
        if member and member.is_active_member:
            # The token carries a fingerprint of the current password hash,
            # so it stops working as soon as the password is changed (single
            # use) — see reset_password().
            token = _serializer().dumps(
                {'member_id': member.id, 'fp': password_fingerprint(member.password_hash)},
                salt=RESET_SALT
            )
            # Built from SITE_URL, never the request's Host header.
            reset_url = external_url('auth.reset_password', token=token)
            # Result deliberately ignored: the response is identical
            # whether or not the email went out (no enumeration).
            send_password_reset(
                member.email, reset_url, RESET_TOKEN_MAX_AGE // 60,
                audience='member', key_parts=(token,),
            )
        flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def reset_password(token):
    try:
        data = _serializer().loads(token, salt=RESET_SALT, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        flash('That reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    member = db.session.get(Member, data.get('member_id')) if isinstance(data, dict) else None
    if not member or not fingerprints_match(data.get('fp'), member.password_hash):
        flash('That reset link is invalid or has already been used.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = MemberResetPasswordForm()
    if form.validate_on_submit():
        member.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)
