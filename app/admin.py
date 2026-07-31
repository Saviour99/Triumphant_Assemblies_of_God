"""
Admin dashboard blueprint: super-admin auth, member management, sermon
management, devotion management, live-stream toggle, giving overview,
dashboard stats.
"""

import os
import uuid
from datetime import date, datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    jsonify, current_app, session
)
from flask_login import login_user, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app import db, cache, limiter
from app.decorators import admin_required, developer_required
from app.email_utils import send_email
from app.forms import (
    AdminLoginForm, AdminForgotPasswordForm, AdminResetPasswordForm, AdminProfileForm,
    AdminAccountManageForm, AdminMemberForm, VideoSermonForm, AudioSermonForm,
    AudioSermonEditForm, DevotionForm, LiveStreamForm, EbookForm
)
from app.models import (
    Admin, Member, VideoSermon, AudioSermon, Devotion, LiveStreamSetting, Giving, AdminLoginLog,
    PrayerRequest, ContactMessage, NewsletterSubscriber, Ebook
)
from app.utils import (
    sanitize_text, sanitize_multiline_text, is_valid_audio_file, is_valid_image_file, is_valid_pdf_file,
    get_ebooks_by_category
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

RESET_SALT = 'admin-password-reset'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# ============ AUTH ============

@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return redirect(url_for('admin.dashboard'))

    form = AdminLoginForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(email=form.email.data.lower().strip()).first()
        if admin and admin.check_password(form.password.data):
            login_user(admin)
            admin.last_login_at = datetime.utcnow()
            db.session.add(AdminLoginLog(admin_id=admin.id, ip_address=request.remote_addr))
            db.session.commit()
            session['admin_last_seen'] = datetime.utcnow().timestamp()
            next_url = request.args.get('next')
            return redirect(next_url or url_for('admin.dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('admin/login.html', form=form)


@admin_bp.route('/logout')
@admin_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin.login'))


@admin_bp.route('/profile', methods=['GET', 'POST'])
@developer_required
def profile():
    form = AdminProfileForm()
    if form.validate_on_submit():
        if form.avatar.data:
            if not is_valid_image_file(form.avatar.data):
                flash('That file does not look like a valid image.', 'danger')
                return render_template('admin/profile.html', form=form)

            filename = secure_filename(form.avatar.data.filename)
            stored_name = f"{uuid.uuid4().hex}_{filename}"
            dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(dest_dir, exist_ok=True)
            form.avatar.data.save(os.path.join(dest_dir, stored_name))
            current_user.avatar_filename = f"uploads/avatars/{stored_name}"

        if form.new_password.data:
            current_user.set_password(form.new_password.data)

        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('admin.profile'))

    return render_template('admin/profile.html', form=form)


# ============ ACCOUNT MANAGEMENT (developer-only) ============
# The developer is the sole party who can reset another admin's password —
# if the admin forgets theirs or it needs to change, the developer does it
# here rather than the admin self-servicing it.

@admin_bp.route('/accounts')
@developer_required
def accounts_list():
    accounts = Admin.query.order_by(Admin.role.desc(), Admin.username.asc()).all()
    return render_template('admin/accounts_list.html', accounts=accounts)


@admin_bp.route('/accounts/<int:account_id>/edit', methods=['GET', 'POST'])
@developer_required
def account_edit(account_id):
    account = Admin.query.get_or_404(account_id)
    form = AdminAccountManageForm(obj=account)

    if form.validate_on_submit():
        existing = Admin.query.filter(
            Admin.id != account.id,
            (Admin.username == form.username.data) | (Admin.email == form.email.data.lower().strip())
        ).first()
        if existing:
            flash('Another account already uses that username or email.', 'danger')
            return render_template('admin/account_form.html', form=form, account=account)

        if form.avatar.data:
            if not is_valid_image_file(form.avatar.data):
                flash('That file does not look like a valid image.', 'danger')
                return render_template('admin/account_form.html', form=form, account=account)

            filename = secure_filename(form.avatar.data.filename)
            stored_name = f"{uuid.uuid4().hex}_{filename}"
            dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(dest_dir, exist_ok=True)
            form.avatar.data.save(os.path.join(dest_dir, stored_name))
            account.avatar_filename = f"uploads/avatars/{stored_name}"

        account.username = sanitize_text(form.username.data)
        account.email = form.email.data.lower().strip()
        if form.new_password.data:
            account.set_password(form.new_password.data)

        db.session.commit()
        flash(f"{account.display_role} account updated.", 'success')
        return redirect(url_for('admin.accounts_list'))

    return render_template('admin/account_form.html', form=form, account=account)


@admin_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def forgot_password():
    form = AdminForgotPasswordForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(email=form.email.data.lower().strip()).first()
        if admin:
            token = _serializer().dumps({'admin_id': admin.id}, salt=RESET_SALT)
            reset_url = url_for('admin.reset_password', token=token, _external=True)
            send_email(
                admin.email,
                'Reset your TAG admin password',
                f'Click the link to reset your admin password (valid for 1 hour): {reset_url}'
            )
        flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('admin.login'))
    return render_template('admin/forgot_password.html', form=form)


@admin_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        data = _serializer().loads(token, salt=RESET_SALT, max_age=3600)
    except (BadSignature, SignatureExpired):
        flash('That reset link is invalid or has expired.', 'danger')
        return redirect(url_for('admin.forgot_password'))

    admin = db.session.get(Admin, data.get('admin_id'))
    if not admin:
        flash('That reset link is invalid.', 'danger')
        return redirect(url_for('admin.forgot_password'))

    form = AdminResetPasswordForm()
    if form.validate_on_submit():
        admin.set_password(form.password.data)
        db.session.commit()
        flash('Password reset. Please log in.', 'success')
        return redirect(url_for('admin.login'))

    return render_template('admin/reset_password.html', form=form)


# ============ DASHBOARD ============

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    total_members = Member.query.filter_by(is_active_member=True).count()
    total_donations = db.session.query(func.sum(Giving.amount)).filter(
        Giving.status == 'completed'
    ).scalar() or 0
    total_prayer_requests = PrayerRequest.query.count()
    total_messages = ContactMessage.query.count()
    total_newsletter_subscribers = NewsletterSubscriber.query.count()
    total_devotions = Devotion.query.count()
    is_live = LiveStreamSetting.query.get(1)
    is_live = bool(is_live and is_live.is_live)

    recent_registrations = Member.query.order_by(Member.created_at.desc()).limit(5).all()
    recent_donations = Giving.query.filter_by(status='completed').order_by(
        Giving.created_at.desc()
    ).limit(5).all()

    # Login-audit visibility is developer-only (see class docstring on
    # AdminLoginLog) — plain admins don't see who logged in when.
    recent_logins = None
    if current_user.role == 'developer':
        recent_logins = AdminLoginLog.query.order_by(AdminLoginLog.login_at.desc()).limit(5).all()

    return render_template(
        'admin/dashboard.html',
        total_members=total_members,
        total_donations=total_donations,
        total_prayer_requests=total_prayer_requests,
        total_messages=total_messages,
        total_newsletter_subscribers=total_newsletter_subscribers,
        total_devotions=total_devotions,
        is_live=is_live,
        recent_registrations=recent_registrations,
        recent_donations=recent_donations,
        recent_logins=recent_logins
    )


@admin_bp.route('/login-history')
@developer_required
def login_history():
    """Login audit trail — the dashboard panel only shows the latest 5;
    this shows the latest 100."""
    logins = AdminLoginLog.query.order_by(AdminLoginLog.login_at.desc()).limit(100).all()
    return render_template('admin/login_history.html', logins=logins)


@admin_bp.route('/api/chart-data')
@admin_required
@cache.cached(timeout=60)
def chart_data():
    donation_trend = db.session.query(
        func.date_format(Giving.created_at, '%Y-%m').label('month'),
        func.sum(Giving.amount)
    ).filter(Giving.status == 'completed').group_by('month').order_by('month').all()

    member_growth = db.session.query(
        func.date_format(Member.created_at, '%Y-%m').label('month'),
        func.count(Member.id)
    ).group_by('month').order_by('month').all()

    return jsonify({
        'donation_trend': {
            'labels': [row[0] for row in donation_trend],
            'values': [float(row[1]) for row in donation_trend]
        },
        'member_growth': {
            'labels': [row[0] for row in member_growth],
            'values': [row[1] for row in member_growth]
        }
    })


# ============ LIVE STREAM ============

@admin_bp.route('/live-stream', methods=['GET', 'POST'])
@admin_required
def live_stream():
    setting = LiveStreamSetting.query.get(1)
    form = LiveStreamForm(obj=setting)
    if form.validate_on_submit():
        setting.is_live = form.is_live.data
        setting.youtube_url = form.youtube_url.data.strip() if form.youtube_url.data else None
        db.session.commit()
        flash('Live stream settings updated.', 'success')
        return redirect(url_for('admin.live_stream'))
    return render_template('admin/live_stream.html', form=form, setting=setting)


# ============ MEMBERS ============

@admin_bp.route('/members')
@admin_required
def members_list():
    members = Member.query.order_by(Member.created_at.desc()).all()
    return render_template('admin/members_list.html', members=members)


@admin_bp.route('/members/add', methods=['GET', 'POST'])
@admin_required
def member_add():
    form = AdminMemberForm()
    if form.validate_on_submit():
        if Member.query.filter_by(email=form.email.data.lower().strip()).first():
            flash('A member with that email already exists.', 'danger')
        else:
            member = Member(
                full_name=sanitize_text(form.full_name.data),
                email=form.email.data.lower().strip(),
                phone=form.phone.data.strip() if form.phone.data else None,
                is_active_member=form.is_active_member.data
            )
            member.set_password(form.password.data or uuid.uuid4().hex)
            db.session.add(member)
            db.session.commit()
            flash('Member added.', 'success')
            return redirect(url_for('admin.members_list'))
    return render_template('admin/member_form.html', form=form, member=None)


@admin_bp.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@admin_required
def member_edit(member_id):
    member = Member.query.get_or_404(member_id)
    form = AdminMemberForm(obj=member)
    if form.validate_on_submit():
        member.full_name = sanitize_text(form.full_name.data)
        member.email = form.email.data.lower().strip()
        member.phone = form.phone.data.strip() if form.phone.data else None
        member.is_active_member = form.is_active_member.data
        if form.password.data:
            member.set_password(form.password.data)
        db.session.commit()
        flash('Member updated.', 'success')
        return redirect(url_for('admin.members_list'))
    return render_template('admin/member_form.html', form=form, member=member)


@admin_bp.route('/members/<int:member_id>/delete', methods=['POST'])
@admin_required
def member_delete(member_id):
    """Soft delete only — never a hard DELETE, per the data-safety rule."""
    member = Member.query.get_or_404(member_id)
    member.is_active_member = False
    db.session.commit()
    flash('Member deactivated.', 'success')
    return redirect(url_for('admin.members_list'))


@admin_bp.route('/members/<int:member_id>')
@admin_required
def member_profile(member_id):
    member = Member.query.get_or_404(member_id)
    donations = member.donations.order_by(Giving.created_at.desc()).all()
    return render_template('admin/member_profile.html', member=member, donations=donations)


# ============ VIDEO SERMONS ============

@admin_bp.route('/sermons/video')
@admin_required
def video_sermons_list():
    sermons = VideoSermon.query.order_by(VideoSermon.sermon_date.desc()).all()
    return render_template('admin/sermons_video_list.html', sermons=sermons)


@admin_bp.route('/sermons/video/add', methods=['GET', 'POST'])
@admin_required
def video_sermon_add():
    form = VideoSermonForm()
    if form.validate_on_submit():
        sermon = VideoSermon(
            title=sanitize_text(form.title.data),
            preacher=sanitize_text(form.preacher.data),
            youtube_url=form.youtube_url.data.strip(),
            message=sanitize_text(form.message.data),
            sermon_date=form.sermon_date.data
        )
        db.session.add(sermon)
        db.session.commit()
        flash('Video sermon added.', 'success')
        return redirect(url_for('admin.video_sermons_list'))
    return render_template('admin/sermon_video_form.html', form=form)


@admin_bp.route('/sermons/video/<int:sermon_id>/edit', methods=['GET', 'POST'])
@admin_required
def video_sermon_edit(sermon_id):
    sermon = VideoSermon.query.get_or_404(sermon_id)
    form = VideoSermonForm(obj=sermon)
    if form.validate_on_submit():
        sermon.title = sanitize_text(form.title.data)
        sermon.preacher = sanitize_text(form.preacher.data)
        sermon.youtube_url = form.youtube_url.data.strip()
        sermon.message = sanitize_text(form.message.data)
        sermon.sermon_date = form.sermon_date.data
        db.session.commit()
        flash('Video sermon updated.', 'success')
        return redirect(url_for('admin.video_sermons_list'))
    return render_template('admin/sermon_video_form.html', form=form, sermon=sermon)


@admin_bp.route('/sermons/video/<int:sermon_id>/delete', methods=['POST'])
@admin_required
def video_sermon_delete(sermon_id):
    sermon = VideoSermon.query.get_or_404(sermon_id)
    db.session.delete(sermon)
    db.session.commit()
    flash('Video sermon deleted.', 'success')
    return redirect(url_for('admin.video_sermons_list'))


# ============ AUDIO SERMONS ============

@admin_bp.route('/sermons/audio')
@admin_required
def audio_sermons_list():
    sermons = AudioSermon.query.order_by(AudioSermon.sermon_date.desc()).all()
    return render_template('admin/sermons_audio_list.html', sermons=sermons)


@admin_bp.route('/sermons/audio/add', methods=['GET', 'POST'])
@admin_required
def audio_sermon_add():
    form = AudioSermonForm()
    if form.validate_on_submit():
        audio_file = form.audio_file.data

        # FileAllowed only checks the filename extension, which can be
        # spoofed by renaming an arbitrary file — verify the actual file
        # content looks like real MP3/MP4 audio before accepting it.
        if not is_valid_audio_file(audio_file):
            flash('That file does not look like a valid audio file.', 'danger')
            return render_template('admin/sermon_audio_form.html', form=form)

        filename = secure_filename(audio_file.filename)
        stored_name = f"{uuid.uuid4().hex}_{filename}"
        dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'audio')
        os.makedirs(dest_dir, exist_ok=True)
        audio_file.save(os.path.join(dest_dir, stored_name))

        sermon = AudioSermon(
            title=sanitize_text(form.title.data),
            preacher=sanitize_text(form.preacher.data),
            audio_path=f"uploads/audio/{stored_name}",
            message=sanitize_text(form.message.data),
            sermon_date=form.sermon_date.data
        )
        db.session.add(sermon)
        db.session.commit()
        flash('Audio sermon uploaded.', 'success')
        return redirect(url_for('admin.audio_sermons_list'))
    return render_template('admin/sermon_audio_form.html', form=form)


@admin_bp.route('/sermons/audio/<int:sermon_id>/edit', methods=['GET', 'POST'])
@admin_required
def audio_sermon_edit(sermon_id):
    sermon = AudioSermon.query.get_or_404(sermon_id)
    form = AudioSermonEditForm(obj=sermon)
    if form.validate_on_submit():
        if form.audio_file.data:
            audio_file = form.audio_file.data
            if not is_valid_audio_file(audio_file):
                flash('That file does not look like a valid audio file.', 'danger')
                return render_template('admin/sermon_audio_form.html', form=form, sermon=sermon)

            filename = secure_filename(audio_file.filename)
            stored_name = f"{uuid.uuid4().hex}_{filename}"
            dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'audio')
            os.makedirs(dest_dir, exist_ok=True)
            audio_file.save(os.path.join(dest_dir, stored_name))

            old_absolute_path = os.path.join(current_app.root_path, 'static', sermon.audio_path)
            try:
                if os.path.exists(old_absolute_path):
                    os.remove(old_absolute_path)
            except OSError:
                current_app.logger.warning(f'Could not remove old audio file: {old_absolute_path}')

            sermon.audio_path = f"uploads/audio/{stored_name}"

        sermon.title = sanitize_text(form.title.data)
        sermon.preacher = sanitize_text(form.preacher.data)
        sermon.message = sanitize_text(form.message.data)
        sermon.sermon_date = form.sermon_date.data
        db.session.commit()
        flash('Audio sermon updated.', 'success')
        return redirect(url_for('admin.audio_sermons_list'))
    return render_template('admin/sermon_audio_form.html', form=form, sermon=sermon)


@admin_bp.route('/sermons/audio/<int:sermon_id>/delete', methods=['POST'])
@admin_required
def audio_sermon_delete(sermon_id):
    sermon = AudioSermon.query.get_or_404(sermon_id)
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], '..', 'static', sermon.audio_path)
    absolute_path = os.path.join(current_app.root_path, 'static', sermon.audio_path)
    try:
        if os.path.exists(absolute_path):
            os.remove(absolute_path)
    except OSError:
        current_app.logger.warning(f'Could not remove audio file: {absolute_path}')
    db.session.delete(sermon)
    db.session.commit()
    flash('Audio sermon deleted.', 'success')
    return redirect(url_for('admin.audio_sermons_list'))


# ============ DEVOTIONS ============

@admin_bp.route('/devotions')
@admin_required
def devotions_list():
    devotions = Devotion.query.order_by(Devotion.devotion_date.desc()).all()
    return render_template('admin/devotions_list.html', devotions=devotions)


@admin_bp.route('/devotions/add', methods=['GET', 'POST'])
@admin_required
def devotion_add():
    today = date.today()
    already_posted = Devotion.query.filter_by(devotion_date=today).first()

    form = DevotionForm()
    if not already_posted and form.validate_on_submit():
        devotion = Devotion(
            title=sanitize_text(form.title.data),
            quote=sanitize_text(form.quote.data),
            quote_theme=sanitize_text(form.quote_theme.data),
            writer_name=sanitize_text(form.writer_name.data),
            reflection=sanitize_text(form.reflection.data),
            prayer_points=sanitize_multiline_text(form.prayer_points.data),
            declaration=sanitize_text(form.declaration.data),
            devotion_date=today
        )
        db.session.add(devotion)
        db.session.commit()

        # Keep only the latest MAX_DEVOTIONS rows — single bounded DELETE,
        # never a TRUNCATE, per the data-safety rule.
        max_devotions = current_app.config.get('MAX_DEVOTIONS', 60)
        total = Devotion.query.count()
        if total > max_devotions:
            excess = total - max_devotions
            stale_ids = [
                d.id for d in Devotion.query
                .order_by(Devotion.devotion_date.asc(), Devotion.id.asc())
                .limit(excess).all()
            ]
            Devotion.query.filter(Devotion.id.in_(stale_ids)).delete(synchronize_session=False)
            db.session.commit()

        flash('Devotion posted for today.', 'success')
        return redirect(url_for('admin.devotions_list'))

    return render_template(
        'admin/devotion_form.html', form=form, today=today, already_posted=already_posted
    )


@admin_bp.route('/devotions/<int:devotion_id>/edit', methods=['GET', 'POST'])
@admin_required
def devotion_edit(devotion_id):
    """Fix a typo/mistake in an already-posted devotion. The date is never
    editable here either — same rule as when it's first created."""
    devotion = Devotion.query.get_or_404(devotion_id)
    form = DevotionForm(obj=devotion)
    if form.validate_on_submit():
        devotion.title = sanitize_text(form.title.data)
        devotion.quote = sanitize_text(form.quote.data)
        devotion.quote_theme = sanitize_text(form.quote_theme.data)
        devotion.writer_name = sanitize_text(form.writer_name.data)
        devotion.reflection = sanitize_text(form.reflection.data)
        devotion.prayer_points = sanitize_multiline_text(form.prayer_points.data)
        devotion.declaration = sanitize_text(form.declaration.data)
        db.session.commit()
        flash('Devotion updated.', 'success')
        return redirect(url_for('admin.devotions_list'))
    return render_template('admin/devotion_form.html', form=form, devotion=devotion)


# ============ E-BOOKS (Worship / Leadership reading lists) ============

@admin_bp.route('/ebooks')
@admin_required
def ebooks_list():
    ebooks = Ebook.query.order_by(Ebook.category.asc(), Ebook.title.asc()).all()
    return render_template('admin/ebooks_list.html', ebooks=ebooks)


def _save_ebook_file(file_storage):
    filename = secure_filename(file_storage.filename)
    stored_name = f"{uuid.uuid4().hex}_{filename}"
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'ebooks')
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, stored_name))
    return f"uploads/ebooks/{stored_name}"


def _save_ebook_thumbnail(file_storage):
    filename = secure_filename(file_storage.filename)
    stored_name = f"{uuid.uuid4().hex}_{filename}"
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'ebook_thumbnails')
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, stored_name))
    return f"uploads/ebook_thumbnails/{stored_name}"


def _remove_static_file(relative_path):
    """Best-effort delete of a file under app/static/, used when replacing
    or removing an ebook's PDF/thumbnail."""
    if not relative_path:
        return
    absolute_path = os.path.join(current_app.root_path, 'static', relative_path)
    try:
        if os.path.exists(absolute_path):
            os.remove(absolute_path)
    except OSError:
        current_app.logger.warning(f'Could not remove file: {absolute_path}')


@admin_bp.route('/ebooks/add', methods=['GET', 'POST'])
@admin_required
def ebook_add():
    form = EbookForm()
    if form.validate_on_submit():
        file_path = None
        if form.file.data:
            if not is_valid_pdf_file(form.file.data):
                flash('That file does not look like a valid PDF.', 'danger')
                return render_template('admin/ebook_form.html', form=form)
            file_path = _save_ebook_file(form.file.data)

        thumbnail_filename = None
        if form.thumbnail.data:
            if not is_valid_image_file(form.thumbnail.data):
                flash('That thumbnail does not look like a valid image.', 'danger')
                return render_template('admin/ebook_form.html', form=form)
            thumbnail_filename = _save_ebook_thumbnail(form.thumbnail.data)

        ebook = Ebook(
            title=sanitize_text(form.title.data),
            author=sanitize_text(form.author.data),
            category=form.category.data,
            summary=sanitize_text(form.summary.data),
            file_path=file_path,
            thumbnail_filename=thumbnail_filename
        )
        db.session.add(ebook)
        db.session.commit()
        cache.delete_memoized(get_ebooks_by_category, ebook.category)
        flash('E-book added.', 'success')
        return redirect(url_for('admin.ebooks_list'))
    return render_template('admin/ebook_form.html', form=form)


@admin_bp.route('/ebooks/<int:ebook_id>/edit', methods=['GET', 'POST'])
@admin_required
def ebook_edit(ebook_id):
    ebook = Ebook.query.get_or_404(ebook_id)
    form = EbookForm(obj=ebook)
    old_category = ebook.category
    if form.validate_on_submit():
        if form.file.data:
            if not is_valid_pdf_file(form.file.data):
                flash('That file does not look like a valid PDF.', 'danger')
                return render_template('admin/ebook_form.html', form=form, ebook=ebook)

            _remove_static_file(ebook.file_path)
            ebook.file_path = _save_ebook_file(form.file.data)

        if form.thumbnail.data:
            if not is_valid_image_file(form.thumbnail.data):
                flash('That thumbnail does not look like a valid image.', 'danger')
                return render_template('admin/ebook_form.html', form=form, ebook=ebook)

            _remove_static_file(ebook.thumbnail_filename)
            ebook.thumbnail_filename = _save_ebook_thumbnail(form.thumbnail.data)

        ebook.title = sanitize_text(form.title.data)
        ebook.author = sanitize_text(form.author.data)
        ebook.category = form.category.data
        ebook.summary = sanitize_text(form.summary.data)
        db.session.commit()
        cache.delete_memoized(get_ebooks_by_category, old_category)
        if ebook.category != old_category:
            cache.delete_memoized(get_ebooks_by_category, ebook.category)
        flash('E-book updated.', 'success')
        return redirect(url_for('admin.ebooks_list'))
    return render_template('admin/ebook_form.html', form=form, ebook=ebook)


@admin_bp.route('/ebooks/<int:ebook_id>/delete', methods=['POST'])
@admin_required
def ebook_delete(ebook_id):
    ebook = Ebook.query.get_or_404(ebook_id)
    category = ebook.category
    _remove_static_file(ebook.file_path)
    _remove_static_file(ebook.thumbnail_filename)
    db.session.delete(ebook)
    db.session.commit()
    cache.delete_memoized(get_ebooks_by_category, category)
    flash('E-book deleted.', 'success')
    return redirect(url_for('admin.ebooks_list'))


# ============ GIVING ============

@admin_bp.route('/giving')
@admin_required
def giving_list():
    status_filter = request.args.get('status')
    type_filter = request.args.get('type')

    query = Giving.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(giving_type=type_filter)
    donations = query.order_by(Giving.created_at.desc()).all()
    filtered_total = sum((d.amount for d in donations), start=0)

    # Per-type breakdown of money actually received (completed only),
    # regardless of whatever filter is currently applied above — this is
    # the "how much has gone to Tithe / Offering / Missions" overview.
    type_totals = dict(
        db.session.query(Giving.giving_type, func.sum(Giving.amount))
        .filter(Giving.status == 'completed')
        .group_by(Giving.giving_type)
        .all()
    )
    giving_types = ['tithe', 'offering', 'missions', 'building_fund', 'other']

    return render_template(
        'admin/giving_list.html',
        donations=donations,
        status_filter=status_filter,
        type_filter=type_filter,
        filtered_total=filtered_total,
        type_totals=type_totals,
        giving_types=giving_types
    )


# ============ PRAYER REQUESTS / CONTACT MESSAGES / NEWSLETTER ============
# Read-only views of what the public site collects — previously had no
# admin visibility at all.

@admin_bp.route('/prayer-requests')
@admin_required
def prayer_requests_list():
    requests_ = PrayerRequest.query.order_by(PrayerRequest.created_at.desc()).all()
    return render_template('admin/prayer_requests_list.html', requests=requests_)


@admin_bp.route('/messages')
@admin_required
def messages_list():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template('admin/messages_list.html', messages=messages)


@admin_bp.route('/newsletter-subscribers')
@admin_required
def newsletter_subscribers_list():
    subscribers = NewsletterSubscriber.query.order_by(NewsletterSubscriber.subscribed_at.desc()).all()
    return render_template('admin/newsletter_subscribers_list.html', subscribers=subscribers)
