"""
SQLAlchemy models.

Column-for-column mirror of the tables created/altered in init_db.py.
init_db.py is the canonical schema bootstrap script (additive only —
no DROP/TRUNCATE, ever). Keep this file and init_db.py in sync by hand.
"""

from datetime import datetime
from app import db


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

    login_logs = db.relationship('AdminLoginLog', backref='admin', lazy='dynamic')

    @property
    def display_role(self):
        if self.role == 'developer':
            return 'Developer'
        if self.role == 'pastor':
            return 'Pastor'
        return 'Admin'

    # Flask-Login integration
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

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

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    testimony = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LiveStreamSetting(db.Model):
    __tablename__ = 'live_stream_settings'

    id = db.Column(db.Integer, primary_key=True)
    is_live = db.Column(db.Boolean, nullable=False, default=False)
    youtube_url = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    subject = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NewsletterSubscriber(db.Model):
    __tablename__ = 'newsletter_subscribers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)


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
