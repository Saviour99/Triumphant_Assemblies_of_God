"""
Admin dashboard blueprint: super-admin auth, member management, sermon
management, devotion management, live-stream toggle, giving overview,
dashboard stats.
"""

import itertools
import os
import uuid
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    jsonify, current_app, session
)
from flask_login import login_user, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app import db, cache, limiter
from app.decorators import admin_required, developer_required, permission_required
from app.email_utils import send_password_reset
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
RESET_TOKEN_MAX_AGE = 1800  # seconds (30 minutes)


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


ADMIN_PAGE_SIZE = 25


def _paginate(query, param='page', per_page=ADMIN_PAGE_SIZE):
    """Paginate an admin list query from ?page=N (or another param name).
    Out-of-range pages give an empty page rather than a 404. Rendered with
    the `pager` macro in admin/_macros.html."""
    page = request.args.get(param, 1, type=int) or 1
    return query.paginate(page=max(page, 1), per_page=per_page, error_out=False)


from app.security import (  # noqa: E402  (kept beside the auth helpers)
    safe_next_url, external_url, client_ip, password_fingerprint,
    fingerprints_match, burn_password_check, bind_session_to_password
)
import time  # noqa: E402


# ============ AUTH ============

@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute;30 per hour', methods=['POST'])
def login():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return redirect(url_for('admin.dashboard'))

    form = AdminLoginForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(email=form.email.data.lower().strip()).first()
        if admin is None:
            burn_password_check(form.password.data)  # equalise timing
        elif admin.check_password(form.password.data):
            if not admin.is_active:
                # Correct password but deactivated: clear message, no
                # session, no login-log row.
                flash('This account has been deactivated. Contact the developer.', 'danger')
                return render_template('admin/login.html', form=form)
            login_user(admin)
            bind_session_to_password(admin)
            admin.last_login_at = datetime.utcnow()
            db.session.add(AdminLoginLog(admin_id=admin.id, ip_address=client_ip()))
            db.session.commit()
            now_ts = time.time()
            session['admin_last_seen'] = now_ts
            session['admin_login_at'] = now_ts
            next_url = safe_next_url(request.args.get('next'))
            return redirect(next_url or url_for('admin.dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('admin/login.html', form=form)


@admin_bp.route('/logout', methods=['POST'])
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
            previous_avatar = current_user.avatar_filename
            current_user.avatar_filename = f"uploads/avatars/{stored_name}"
            if previous_avatar and previous_avatar.startswith('uploads/avatars/'):
                _remove_static_file(previous_avatar)

        if form.new_password.data:
            current_user.set_password(form.new_password.data)

        db.session.commit()
        if form.new_password.data:
            # Keep THIS session valid; every other session for this account
            # is dropped by the password fingerprint check in user_loader.
            bind_session_to_password(current_user)
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
            previous_avatar = account.avatar_filename
            account.avatar_filename = f"uploads/avatars/{stored_name}"
            if previous_avatar and previous_avatar.startswith('uploads/avatars/'):
                _remove_static_file(previous_avatar)

        account.username = sanitize_text(form.username.data)
        account.email = form.email.data.lower().strip()
        if form.new_password.data:
            account.set_password(form.new_password.data)

        db.session.commit()
        if form.new_password.data and account.id == current_user.id:
            # Changing your own password here must not log you out (other
            # sessions for this account are still dropped by user_loader).
            bind_session_to_password(account)
        flash(f"{account.display_role} account updated.", 'success')
        return redirect(url_for('admin.accounts_list'))

    return render_template('admin/account_form.html', form=form, account=account)


@admin_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def forgot_password():
    form = AdminForgotPasswordForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(email=form.email.data.lower().strip()).first()
        if admin and admin.is_active:
            # Token is bound to the current password hash -> single use.
            token = _serializer().dumps(
                {'admin_id': admin.id, 'fp': password_fingerprint(admin.password_hash)},
                salt=RESET_SALT
            )
            # Built from SITE_URL, never the request's Host header.
            reset_url = external_url('admin.reset_password', token=token)
            # Result deliberately ignored: the response is identical
            # whether or not the email went out (no enumeration).
            send_password_reset(
                admin.email, reset_url, RESET_TOKEN_MAX_AGE // 60,
                audience='admin', key_parts=(token,),
            )
        flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('admin.login'))
    return render_template('admin/forgot_password.html', form=form)


@admin_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def reset_password(token):
    try:
        data = _serializer().loads(token, salt=RESET_SALT, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        flash('That reset link is invalid or has expired.', 'danger')
        return redirect(url_for('admin.forgot_password'))

    admin = db.session.get(Admin, data.get('admin_id')) if isinstance(data, dict) else None
    if not admin or not fingerprints_match(data.get('fp'), admin.password_hash):
        flash('That reset link is invalid or has already been used.', 'danger')
        return redirect(url_for('admin.forgot_password'))

    form = AdminResetPasswordForm()
    if form.validate_on_submit():
        admin.set_password(form.password.data)
        db.session.commit()
        flash('Password reset. Please log in.', 'success')
        return redirect(url_for('admin.login'))

    return render_template('admin/reset_password.html', form=form)


# ============ DASHBOARD ============

def _dashboard_stats():
    """Shared by the initial dashboard render and the /api/recent-activity
    polling endpoint, so the two can never drift out of sync. Only figures
    for sections the current admin may see are computed/returned."""
    can = current_user.can
    stats = {}
    if can('members'):
        stats['total_members'] = Member.query.filter_by(is_active_member=True).count()
    if can('giving'):
        stats['total_donations'] = float(db.session.query(func.sum(Giving.amount)).filter(
            Giving.status == 'completed'
        ).scalar() or 0)
    if can('prayer_requests'):
        stats['total_prayer_requests'] = PrayerRequest.query.count()
    if can('messages'):
        stats['total_messages'] = ContactMessage.query.count()
    if can('newsletter'):
        stats['total_newsletter_subscribers'] = NewsletterSubscriber.query.count()
    if can('devotions'):
        stats['total_devotions'] = Devotion.query.count()
    return stats


def _permission_cache_key(prefix):
    """Cache-key factory for per-user-visible JSON endpoints: the payload
    depends on which sections the admin may see, so admins with different
    permission sets must never share a cached response."""
    def make_key():
        return f"{prefix}:{','.join(current_user.permission_list)}"
    return make_key


def _recent_activity_feed(limit=5):
    """Merges the most-recent Member registrations and ContactMessage
    submissions into one reverse-chronological feed of at most `limit`
    items TOTAL — mirrors the existing 5-item convention used by every
    other dashboard panel. Normalized into a flat {type, id, title, detail}
    shape consumed identically by the server-rendered dashboard template
    and the /api/recent-activity JSON endpoint, so the two can never drift
    (same reasoning as _dashboard_stats()). `id` is namespaced by type
    ("registration-7" / "message-7") since Member.id and ContactMessage.id
    are independent sequences that can collide numerically."""
    registrations = (Member.query.order_by(Member.created_at.desc()).limit(limit).all()
                     if current_user.can('members') else [])
    messages = (ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(limit).all()
                if current_user.can('messages') else [])

    candidates = itertools.chain(
        (('registration', m.created_at, m) for m in registrations),
        (('message', c.created_at, c) for c in messages),
    )
    top = sorted(candidates, key=lambda row: row[1], reverse=True)[:limit]

    feed = []
    for kind, created_at, obj in top:
        if kind == 'registration':
            feed.append({
                'type': 'registration',
                'id': f'registration-{obj.id}',
                'title': obj.full_name,
                'detail': created_at.strftime('%d %b %Y'),
            })
        else:
            preview = obj.message.strip()
            if len(preview) > 60:
                preview = preview[:60].rstrip() + '…'
            feed.append({
                'type': 'message',
                'id': f'message-{obj.id}',
                'title': obj.email,
                'detail': preview,
            })
    return feed


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    # The dashboard is every admin's landing page, so the route itself stays
    # open to any active admin; the 'dashboard' permission controls whether
    # the overview (figures, charts, activity) is shown, and each figure is
    # further limited to the sections the admin may see.
    if not current_user.can('dashboard'):
        return render_template('admin/dashboard.html', show_overview=False,
                               is_live=False, recent_activity_feed=[],
                               recent_donations=[], recent_logins=None)

    stats = _dashboard_stats()
    is_live = LiveStreamSetting.query.get(1)
    is_live = bool(is_live and is_live.is_live)

    recent_activity_feed = _recent_activity_feed(limit=5)
    recent_donations = _recent_donations(limit=5)

    # Login-audit visibility is developer-only (see class docstring on
    # AdminLoginLog) — plain admins don't see who logged in when.
    recent_logins = None
    if current_user.role == 'developer':
        recent_logins = AdminLoginLog.query.order_by(AdminLoginLog.login_at.desc()).limit(5).all()

    return render_template(
        'admin/dashboard.html',
        show_overview=True,
        is_live=is_live,
        recent_activity_feed=recent_activity_feed,
        recent_donations=recent_donations,
        recent_logins=recent_logins,
        **stats
    )


@admin_bp.route('/api/recent-activity')
@permission_required('dashboard')
@limiter.exempt
@cache.cached(timeout=5, key_prefix=_permission_cache_key('recent-activity'))
def recent_activity():
    """Polled by the dashboard every 5s (see admin.js) so new donations,
    registrations, and contact messages show up without a manual refresh —
    regardless of whether a donation was completed via the client-side
    verify call or the Paystack webhook. Cached for 5s (matching the poll
    interval) via the same Flask-Caching/Redis `cache` object already used
    by /api/chart-data, so N concurrent admin tabs/sessions polling this
    endpoint cause at most one DB round-trip per 5s window instead of N.
    This is a deliberate tradeoff of up to ~5s staleness for materially
    less DB load under concurrent admin sessions — chosen over WebSockets
    (which would need a new Flask-SocketIO dependency, a gunicorn
    worker-class change, and Redis message-queue wiring across the 4
    gunicorn workers) since this is a single-developer project and the
    existing polling architecture is already proven. Exempt from the
    global rate limit since it's an authenticated admin polling loop, not
    public traffic."""
    stats = _dashboard_stats()

    activity_feed = _recent_activity_feed(limit=5)
    recent_donations = _recent_donations(limit=5)

    return jsonify({
        **stats,
        'recent_activity': activity_feed,
        'recent_donations': [
            {
                'id': d.id,
                'donor_name': d.donor_name,
                'giving_type': d.giving_type,
                'amount': float(d.amount),
            }
            for d in recent_donations
        ],
    })


@admin_bp.route('/login-history')
@developer_required
def login_history():
    """Login audit trail — the dashboard panel only shows the latest 5;
    this shows every sign-in, 25 per page."""
    pagination = _paginate(AdminLoginLog.query.order_by(AdminLoginLog.login_at.desc()))
    return render_template('admin/login_history.html', logins=pagination.items, pagination=pagination)


@admin_bp.route('/api/chart-data')
@permission_required('dashboard')
@cache.cached(timeout=60, key_prefix=_permission_cache_key('chart-data'))
def chart_data():
    """Each series is only computed/returned if the admin may see its
    section ('giving' -> donation_trend, 'members' -> member_growth)."""
    payload = {}
    if current_user.can('giving'):
        payload['donation_trend'] = _donation_trend_series()
    if current_user.can('members'):
        payload['member_growth'] = _member_growth_series()
    return jsonify(payload)


def _recent_donations(limit=5):
    if not current_user.can('giving'):
        return []
    return Giving.query.filter_by(status='completed').order_by(
        Giving.created_at.desc()
    ).limit(limit).all()


def _donation_trend_series():
    # Donation Trend: daily totals for a rolling 30-day window, zero-filled
    # so a day with no completed donations shows as an explicit dip to ₵0
    # rather than being skipped — that's what makes the line read as a
    # real day-to-day wave instead of a sparse, misleading one.
    window_start = date.today() - timedelta(days=29)  # 30 calendar days inclusive of today
    window_start_dt = datetime.combine(window_start, datetime.min.time())

    donation_rows = db.session.query(
        func.date(Giving.created_at).label('day'),
        func.sum(Giving.amount)
    ).filter(
        Giving.status == 'completed',
        Giving.created_at >= window_start_dt
    ).group_by('day').order_by('day').all()

    donation_by_day = {row[0]: float(row[1]) for row in donation_rows}

    donation_trend_labels = []
    donation_trend_values = []
    for i in range(30):
        day = window_start + timedelta(days=i)
        donation_trend_labels.append(day.strftime('%d %b'))
        donation_trend_values.append(donation_by_day.get(day, 0.0))

    return {'labels': donation_trend_labels, 'values': donation_trend_values}


def _member_growth_series():
    # Member Growth: cumulative running total of all-time registrations by
    # month, so the line is always non-decreasing (accumulated in Python —
    # at most a few dozen months, no need for a SQL window function).
    member_growth_rows = db.session.query(
        func.date_format(Member.created_at, '%Y-%m').label('month'),
        func.count(Member.id)
    ).group_by('month').order_by('month').all()

    member_growth_labels = []
    member_growth_values = []
    running_total = 0
    for month, count in member_growth_rows:
        running_total += count
        member_growth_labels.append(month)
        member_growth_values.append(running_total)

    return {'labels': member_growth_labels, 'values': member_growth_values}


# ============ LIVE STREAM ============

@admin_bp.route('/live-stream', methods=['GET', 'POST'])
@permission_required('live_stream')
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
@permission_required('members')
def members_list():
    pagination = _paginate(Member.query.order_by(Member.created_at.desc()))
    return render_template('admin/members_list.html', members=pagination.items, pagination=pagination)


@admin_bp.route('/members/add', methods=['GET', 'POST'])
@permission_required('members')
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
@permission_required('members')
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
@permission_required('members')
def member_delete(member_id):
    """Soft delete only — never a hard DELETE, per the data-safety rule."""
    member = Member.query.get_or_404(member_id)
    member.is_active_member = False
    db.session.commit()
    flash('Member deactivated.', 'success')
    return redirect(url_for('admin.members_list'))


@admin_bp.route('/members/<int:member_id>')
@permission_required('members')
def member_profile(member_id):
    member = Member.query.get_or_404(member_id)
    donations = member.donations.order_by(Giving.created_at.desc()).all()
    return render_template('admin/member_profile.html', member=member, donations=donations)


# ============ VIDEO SERMONS ============

@admin_bp.route('/sermons/video')
@permission_required('video_sermons')
def video_sermons_list():
    sermons = VideoSermon.query.order_by(VideoSermon.sermon_date.desc()).all()
    return render_template('admin/sermons_video_list.html', sermons=sermons)


@admin_bp.route('/sermons/video/add', methods=['GET', 'POST'])
@permission_required('video_sermons')
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
@permission_required('video_sermons')
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
@permission_required('video_sermons')
def video_sermon_delete(sermon_id):
    sermon = VideoSermon.query.get_or_404(sermon_id)
    db.session.delete(sermon)
    db.session.commit()
    flash('Video sermon deleted.', 'success')
    return redirect(url_for('admin.video_sermons_list'))


# ============ AUDIO SERMONS ============

@admin_bp.route('/sermons/audio')
@permission_required('audio_sermons')
def audio_sermons_list():
    sermons = AudioSermon.query.order_by(AudioSermon.sermon_date.desc()).all()
    return render_template('admin/sermons_audio_list.html', sermons=sermons)


@admin_bp.route('/sermons/audio/add', methods=['GET', 'POST'])
@permission_required('audio_sermons')
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
@permission_required('audio_sermons')
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
@permission_required('audio_sermons')
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
@permission_required('devotions')
def devotions_list():
    pagination = _paginate(Devotion.query.order_by(Devotion.devotion_date.desc()))
    return render_template('admin/devotions_list.html', devotions=pagination.items, pagination=pagination)


@admin_bp.route('/devotions/add', methods=['GET', 'POST'])
@permission_required('devotions')
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
        try:
            db.session.commit()
        except IntegrityError:
            # devotion_date is DB-level UNIQUE — this only fires if another
            # admin's request won the race between our "already posted?"
            # check above and this commit (e.g. two admins submitting the
            # form for today within moments of each other).
            db.session.rollback()
            flash(
                "Today's devotion was just posted by someone else. "
                "Please refresh the page before trying again.",
                'danger'
            )
            return redirect(url_for('admin.devotions_list'))

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
@permission_required('devotions')
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
@permission_required('ebooks')
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
@permission_required('ebooks')
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
@permission_required('ebooks')
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
@permission_required('ebooks')
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
@permission_required('giving')
def giving_list():
    status_filter = request.args.get('status')
    type_filter = request.args.get('type')

    query = Giving.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(giving_type=type_filter)
    # Total is over the whole filtered set, not just the page shown.
    filtered_total = query.with_entities(func.coalesce(func.sum(Giving.amount), 0)).scalar() or 0
    pagination = _paginate(query.order_by(Giving.created_at.desc()))
    donations = pagination.items

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
        pagination=pagination,
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
@permission_required('prayer_requests')
def prayer_requests_list():
    pagination = _paginate(PrayerRequest.query.order_by(PrayerRequest.created_at.desc()))
    return render_template('admin/prayer_requests_list.html', requests=pagination.items, pagination=pagination)


@admin_bp.route('/messages')
@permission_required('messages')
def messages_list():
    pagination = _paginate(ContactMessage.query.order_by(ContactMessage.created_at.desc()))
    return render_template('admin/messages_list.html', messages=pagination.items, pagination=pagination)


@admin_bp.route('/newsletter-subscribers')
@permission_required('newsletter')
def newsletter_subscribers_list():
    pagination = _paginate(NewsletterSubscriber.query.order_by(NewsletterSubscriber.subscribed_at.desc()))
    subscribers = pagination.items
    from app.admin_newsletter import recent_campaigns, newsletter_panel_context
    return render_template('admin/newsletter_subscribers_list.html', subscribers=subscribers,
                           pagination=pagination, campaigns=recent_campaigns(),
                           **newsletter_panel_context())


# Account management (add/access/activate), testimonies and events routes
# live in their own module but register on admin_bp; import last so admin_bp
# exists. Keep this at the bottom of the file.
from app import admin_manage  # noqa: E402,F401
from app import admin_newsletter  # noqa: E402,F401  (newsletter compose/send via Mailchimp)
from app import admin_site_settings  # noqa: E402,F401  (developer/pastor: public site info)
from app import admin_integrations  # noqa: E402,F401  (developer only: Resend/email credentials)
