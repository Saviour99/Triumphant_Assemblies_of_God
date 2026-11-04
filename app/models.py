"""
SQLAlchemy models.

Column-for-column mirror of the tables created/altered in init_db.py.
init_db.py is the canonical schema bootstrap script (additive only —
no DROP/TRUNCATE, ever). Keep this file and init_db.py in sync by hand.
"""

from datetime import datetime
from app import db


# Admin dashboard sections, grouped exactly like the sidebar. Keys are what
# `@permission_required(...)` and `Admin.can(...)` take.
ADMIN_SECTION_GROUPS = [
    ('Overview', [
        ('dashboard', 'Dashboard'),
        ('giving', 'Giving'),
        ('live_stream', 'Live stream'),
    ]),
    ('People', [
        ('members', 'Members'),
        ('prayer_requests', 'Prayer requests'),
        ('messages', 'Messages'),
        ('newsletter', 'Newsletter'),
    ]),
    ('Content', [
        ('video_sermons', 'Video sermons'),
        ('audio_sermons', 'Audio sermons'),
        ('devotions', 'Devotions'),
        ('ebooks', 'E-books'),
        ('testimonies', 'Testimonies'),
        ('events', 'Events'),
    ]),
]
ADMIN_SECTION_KEYS = [key for _, items in ADMIN_SECTION_GROUPS for key, _ in items]
ADMIN_SECTION_LABELS = {key: label for _, items in ADMIN_SECTION_GROUPS for key, label in items}
DEFAULT_NEW_ADMIN_SECTIONS = ['dashboard']


class Admin(db.Model):
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')  # 'admin' | 'developer' | 'pastor'
    avatar_filename = db.Column(db.String(255), nullable=True)
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # JSON list of section keys (see ADMIN_SECTION_KEYS). NULL = role default:
    # developer/pastor always get everything; a legacy 'admin' row with NULL
    # keeps the full access it had before permissions existed.
    permissions = db.Column(db.Text, nullable=True)
    # Soft deactivation — admins with login logs are never hard-deleted.
    is_active_account = db.Column('is_active', db.Boolean, nullable=False, default=True)

    login_logs = db.relationship('AdminLoginLog', backref='admin', lazy='dynamic')

    @property
    def display_role(self):
        if self.role == 'developer':
            return 'Developer'
        if self.role == 'pastor':
            return 'Pastor'
        return 'Admin'

    # ---- Section permissions ----
    @property
    def has_all_sections(self):
        return self.role in ('developer', 'pastor') or self.permissions is None

    @property
    def permission_list(self):
        """Effective section keys this account may use, in sidebar order."""
        if self.has_all_sections:
            return list(ADMIN_SECTION_KEYS)
        import json
        try:
            stored = json.loads(self.permissions) or []
        except (TypeError, ValueError):
            stored = []
        return [k for k in ADMIN_SECTION_KEYS if k in stored]

    def set_permissions(self, keys):
        import json
        wanted = set(keys or [])
        self.permissions = json.dumps([k for k in ADMIN_SECTION_KEYS if k in wanted])

    def can(self, section_key):
        return section_key in self.permission_list

    # Flask-Login integration
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        # Deactivated admins can't log in (login_user refuses inactive users)
        # and are signed out by the admin decorators on their next request.
        return self.is_active_account is not False

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return f"admin:{self.id}"

    def set_password(self, raw_password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, raw_password)


class AdminLoginLog(db.Model):
    """One row per successful admin/developer login — an audit trail,
    distinct from Admin.last_login_at which only tracks the most recent."""
    __tablename__ = 'admin_login_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=False)
    login_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(64), nullable=True)


class AdminAccountLog(db.Model):
    """Audit trail of account-management changes made by the developer:
    account created, role/permissions changed, activated/deactivated."""
    __tablename__ = 'admin_account_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=False)       # whose account
    changed_by_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)   # who did it
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('Admin', foreign_keys=[admin_id],
                            backref=db.backref('account_logs', lazy='dynamic',
                                               order_by='AdminAccountLog.changed_at.desc()'))
    changed_by = db.relationship('Admin', foreign_keys=[changed_by_id])


class Member(db.Model):
    __tablename__ = 'members'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active_member = db.Column('is_active', db.Boolean, nullable=False, default=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    donations = db.relationship('Giving', backref='member', lazy='dynamic')

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        # Flask-Login's "can this account log in" flag; soft-deleted
        # members (is_active_member=False) cannot authenticate.
        return self.is_active_member

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return f"member:{self.id}"

    def set_password(self, raw_password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, raw_password)


class VideoSermon(db.Model):
    __tablename__ = 'video_sermons'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    preacher = db.Column(db.String(255), nullable=False)
    youtube_url = db.Column(db.String(500), nullable=False)
    message = db.Column(db.Text, nullable=True)
    sermon_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AudioSermon(db.Model):
    __tablename__ = 'audio_sermons'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    preacher = db.Column(db.String(255), nullable=False)
    audio_path = db.Column(db.String(500), nullable=False)
    message = db.Column(db.Text, nullable=True)
    sermon_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Devotion(db.Model):
    __tablename__ = 'devotions'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    quote = db.Column(db.String(500), nullable=True)
    quote_theme = db.Column(db.String(500), nullable=False)  # the "Theme" field
    writer_name = db.Column(db.String(255), nullable=False)
    reflection = db.Column(db.Text, nullable=False)
    prayer_points = db.Column(db.Text, nullable=True)  # one point per line
    declaration = db.Column(db.Text, nullable=False)
    devotion_date = db.Column(db.Date, unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Ebook(db.Model):
    """Worship/Leadership reading-list entries. file_path is nullable —
    the download button only appears once an admin has actually uploaded
    a file they have the rights to distribute (see CLAUDE.md / no fabricated
    copyrighted downloads)."""
    __tablename__ = 'ebooks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # 'worship' | 'leadership'
    summary = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(500), nullable=True)
    thumbnail_filename = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Testimony(db.Model):
    __tablename__ = 'testimonies'
    __table_args__ = (db.Index('idx_testimonies_status', 'status', 'created_at'),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    testimony = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)  # legacy external link; uploads use image_filename
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Uploaded photo, relative to static/ (e.g. uploads/testimonies/x.jpg).
    image_filename = db.Column(db.String(500), nullable=True)
    # Moderation: only 'approved' rows are public. Defaults to approved so
    # admin-added and pre-existing rows stay visible; member submissions
    # are created as 'pending'.
    status = db.Column(db.String(20), nullable=False, default='approved', server_default='approved')
    member_id = db.Column(db.Integer, nullable=True)  # submitting member, if any
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_admin_id = db.Column(db.Integer, nullable=True)

    @property
    def initials(self):
        """One or two letters for the no-photo monogram avatar."""
        parts = [p for p in (self.name or '').split() if p[:1].isalpha()]
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][0].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Event(db.Model):
    """Church events shown on the public /events page. Only is_published
    rows are public; past/upcoming split is by start_at vs. now."""
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    image_filename = db.Column(db.String(500), nullable=True)  # relative to static/, e.g. uploads/events/x.jpg
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LiveStreamSetting(db.Model):
    __tablename__ = 'live_stream_settings'

    id = db.Column(db.Integer, primary_key=True)
    is_live = db.Column(db.Boolean, nullable=False, default=False)
    youtube_url = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SiteSetting(db.Model):
    """Editable site information (phone, email, service times, socials...),
    one row per key, value JSON-encoded. Missing keys fall back to
    app/site_settings.py::DEFAULTS. Edited by developer/pastor only."""
    __tablename__ = 'site_settings'

    setting_key = db.Column(db.String(64), primary_key=True)
    setting_value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)


class SiteSettingsLog(db.Model):
    """Audit trail of site-settings saves: who, when, which fields."""
    __tablename__ = 'site_settings_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    changed_fields = db.Column(db.Text, nullable=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('Admin')


class IntegrationSetting(db.Model):
    """Developer-editable integration credentials (Resend API key, mail
    addresses...). Every value is Fernet-encrypted — read via
    app/integrations.py::get_integration(), never directly."""
    __tablename__ = 'integration_settings'

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(64), unique=True, nullable=False)
    value_encrypted = db.Column(db.Text, nullable=True)
    is_secret = db.Column(db.Boolean, nullable=False, default=False)
    updated_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class IntegrationSettingLog(db.Model):
    """Audit trail of integration-setting changes: key name, action, who,
    when. Never the value."""
    __tablename__ = 'integration_setting_logs'

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(20), nullable=False)   # saved | removed | test_sent | test_failed
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('Admin')


class PrayerRequest(db.Model):
    __tablename__ = 'prayer_requests'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ContactMessage(db.Model):
    __tablename__ = 'contact_messages'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    subject = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NewsletterSubscriber(db.Model):
    __tablename__ = 'newsletter_subscribers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)


class NewsletterCampaign(db.Model):
    """A newsletter written in the admin and sent through Mailchimp
    (app/admin_newsletter.py). status: draft | sending | sent | failed —
    only ever advanced with a conditional UPDATE so a double-click can't
    send twice."""
    __tablename__ = 'newsletter_campaigns'

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(150), nullable=False)
    preview_text = db.Column(db.String(150), nullable=True)
    body_text = db.Column(db.Text, nullable=False)
    cta_label = db.Column(db.String(40), nullable=True)
    cta_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='draft')
    mailchimp_campaign_id = db.Column(db.String(64), nullable=True)  # legacy, unused (now Resend)
    author_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    recipient_count = db.Column(db.Integer, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)
    provider = db.Column(db.String(20), nullable=True)               # 'resend'
    provider_message_id = db.Column(db.String(64), nullable=True)    # Resend broadcast id
    sending_started_at = db.Column(db.DateTime, nullable=True)       # for the stuck-send reset

    author = db.relationship('Admin')


class Giving(db.Model):
    __tablename__ = 'giving'

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    giving_type = db.Column(db.String(100), nullable=False)
    donor_name = db.Column(db.String(255), nullable=False)
    donor_email = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paystack_reference = db.Column(db.String(255), unique=True, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending|completed|failed
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=True)


# Secondary indexes for list/dashboard sorting and filtering — created
# additively by init_db.py (PERFORMANCE_INDEXES); keep names in sync.
db.Index('ix_giving_status_created_at', Giving.status, Giving.created_at)
db.Index('ix_members_created_at', Member.created_at)
db.Index('ix_contact_messages_created_at', ContactMessage.created_at)
db.Index('ix_prayer_requests_created_at', PrayerRequest.created_at)
db.Index('ix_newsletter_subscribers_subscribed_at', NewsletterSubscriber.subscribed_at)
db.Index('ix_admin_login_logs_login_at', AdminLoginLog.login_at)
db.Index('ix_video_sermons_sermon_date', VideoSermon.sermon_date)
db.Index('ix_audio_sermons_sermon_date', AudioSermon.sermon_date)
