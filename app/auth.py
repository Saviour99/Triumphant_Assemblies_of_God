"""
Member-facing authentication blueprint: register / login / logout /
profile / password reset for the public site.
"""

import os
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.utils import secure_filename

from app import db
from app.decorators import member_required
from app.email_utils import send_email
from app.forms import (
    MemberRegisterForm, MemberLoginForm,
    MemberForgotPasswordForm, MemberResetPasswordForm, MemberAvatarForm
)
from app.models import Member, Giving
from app.utils import sanitize_text, is_valid_image_file

auth_bp = Blueprint('auth', __name__, url_prefix='/members')

RESET_SALT = 'member-password-reset'


def _serializer():
    from flask import current_app
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Only redirect if they're already logged in as a Member — an
    # authenticated Admin/Developer browsing the public site should still
    # be able to view this page instead of being bounced to a 403.
    if current_user.is_authenticated and isinstance(current_user, Member):
        return redirect(url_for('auth.profile'))

    form = MemberRegisterForm()
    if form.validate_on_submit():
        if Member.query.filter_by(email=form.email.data.lower().strip()).first():
            flash('An account with that email already exists.', 'danger')
        else:
            member = Member(
                full_name=sanitize_text(form.full_name.data),
                email=form.email.data.lower().strip(),
                phone=form.phone.data.strip() if form.phone.data else None
            )
            member.set_password(form.password.data)
            db.session.add(member)
            db.session.commit()
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and isinstance(current_user, Member):
        return redirect(url_for('auth.profile'))

    form = MemberLoginForm()
    if form.validate_on_submit():
        member = Member.query.filter_by(email=form.email.data.lower().strip()).first()
        if member and member.check_password(form.password.data):
            if not member.is_active_member:
                flash('This account has been deactivated. Contact the church office.', 'danger')
                return render_template('auth/login.html', form=form)
            login_user(member)
            next_url = request.args.get('next')
            return redirect(next_url or url_for('auth.profile'))
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
def logout():
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
            current_user.avatar_filename = f"uploads/avatars/{stored_name}"
            db.session.commit()
            flash('Profile photo updated.', 'success')
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
def forgot_password():
    form = MemberForgotPasswordForm()
    if form.validate_on_submit():
        member = Member.query.filter_by(email=form.email.data.lower().strip()).first()
        if member:
            token = _serializer().dumps({'member_id': member.id}, salt=RESET_SALT)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            send_email(
                member.email,
                'Reset your Triumphant Assemblies of God password',
                f'Click the link to reset your password (valid for 1 hour): {reset_url}'
            )
        flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        data = _serializer().loads(token, salt=RESET_SALT, max_age=3600)
    except (BadSignature, SignatureExpired):
        flash('That reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    member = db.session.get(Member, data.get('member_id'))
    if not member:
        flash('That reset link is invalid.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = MemberResetPasswordForm()
    if form.validate_on_submit():
        member.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)
