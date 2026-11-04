import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

# Development-only fallback. ProductionConfig.init_app() refuses to start
# if SECRET_KEY is unset, still this value, or too short.
DEV_SECRET_KEY_FALLBACK = 'tag-church-secret-key-2024'


def _env_flag(name):
    return os.getenv(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY') or DEV_SECRET_KEY_FALLBACK
    DEBUG = False
    TESTING = False
    
    # MySQL Configuration
    MYSQL_CURSORCLASS = 'DictCursor'
    MYSQL_AUTOCOMMIT = False

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Caching
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300

    # Rate limiting
    RATELIMIT_STORAGE_URI = 'memory://'
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    ADMIN_SESSION_LIFETIME = timedelta(minutes=30)        # idle timeout
    ADMIN_ABSOLUTE_SESSION_LIFETIME = timedelta(hours=8)  # hard cap since login
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Security
    FORCE_HTTPS = False
    # TRUST_PROXY=1: the app sits behind exactly one reverse proxy (nginx,
    # a PaaS router, Cloudflare...) that sets X-Forwarded-For/-Proto —
    # enables werkzeug's ProxyFix(x_for=1, x_proto=1). Leave off when
    # gunicorn is exposed directly, or clients could spoof their IP.
    TRUST_PROXY = _env_flag('TRUST_PROXY')
    # CLOUDFLARE_PROXY=1: traffic arrives via Cloudflare, so rate limits and
    # the admin login log key on the CF-Connecting-IP header. Only safe if
    # the origin server accepts connections from Cloudflare IPs alone.
    CLOUDFLARE_PROXY = _env_flag('CLOUDFLARE_PROXY')
    # Host-header allow-list (Flask >= 3.1). None = accept any Host (dev).
    TRUSTED_HOSTS = None

    @classmethod
    def init_app(cls, app):
        """Per-environment startup checks; called from create_app()."""

    # Paystack
    PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '')
    PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', '')

    # Mailchimp newsletter (app/mailchimp.py). Server prefix is derived from
    # the API key's "-usXX" suffix when left blank. SITE_URL is the absolute
    # public base URL used for image/links inside emails (never request.host).
    MAILCHIMP_API_KEY = os.getenv('MAILCHIMP_API_KEY', '')
    MAILCHIMP_SERVER_PREFIX = os.getenv('MAILCHIMP_SERVER_PREFIX', '')
    MAILCHIMP_AUDIENCE_ID = os.getenv('MAILCHIMP_AUDIENCE_ID', '')
    MAILCHIMP_FROM_NAME = os.getenv('MAILCHIMP_FROM_NAME', '') or 'Triumphant Assemblies of God'
    MAILCHIMP_REPLY_TO = os.getenv('MAILCHIMP_REPLY_TO', '')
    SITE_URL = os.getenv('SITE_URL', '')

    # Transactional email (app/email_utils.py, app/resend_client.py).
    # RESEND_API_KEY set -> Resend; else SMTP_HOST -> SMTP; else logged only.
    # Read at call time via app/integrations.py (admin-saved values win).
    RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
    MAIL_FROM = os.getenv('MAIL_FROM', '')            # on a Resend-verified domain
    MAIL_REPLY_TO = os.getenv('MAIL_REPLY_TO', '')    # optional
    MAIL_NOTIFY_TO = os.getenv('MAIL_NOTIFY_TO', '')  # optional church inbox alerts

    # Devotions
    MAX_DEVOTIONS = 60
    
    # Compression
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    
    # File uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'app/static/uploads')
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp3', 'mp4'}
    
    # Pagination
    ITEMS_PER_PAGE = 12

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_DB = os.getenv('MYSQL_DB', 'triumphant')
    SQLALCHEMY_DATABASE_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    CACHE_TYPE = 'SimpleCache'
    SESSION_COOKIE_SECURE = False
    FORCE_HTTPS = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    MYSQL_HOST = os.getenv('MYSQL_HOST')
    MYSQL_USER = os.getenv('MYSQL_USER')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
    MYSQL_DB = os.getenv('MYSQL_DB')
    SQLALCHEMY_DATABASE_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"
    SESSION_COOKIE_SECURE = True
    FORCE_HTTPS = True
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(days=30)
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CACHE_DEFAULT_TIMEOUT = 3600  # 1 hour
    RATELIMIT_STORAGE_URI = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    @classmethod
    def init_app(cls, app):
        """Refuse to boot production with an unsafe configuration."""
        from urllib.parse import urlparse

        secret = app.config.get('SECRET_KEY') or ''
        if not secret or secret == DEV_SECRET_KEY_FALLBACK or len(secret) < 32:
            raise RuntimeError(
                'SECRET_KEY must be set to a long random value (>= 32 chars) in '
                'production, e.g. python -c "import secrets; print(secrets.token_hex(32))"'
            )

        site_url = (app.config.get('SITE_URL') or '').rstrip('/')
        parsed = urlparse(site_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise RuntimeError(
                'SITE_URL must be set in production to the public base URL, '
                'e.g. https://www.example.org — it is used for reset links, '
                'sitemap/robots and the Host-header allow-list.'
            )
        app.config['SITE_URL'] = site_url

        # Only accept requests whose Host header is the real site (plus the
        # bare/www twin and any extra hosts listed in ALLOWED_HOSTS).
        if not app.config.get('TRUSTED_HOSTS'):
            host = parsed.hostname.lower()
            hosts = {host, host[4:] if host.startswith('www.') else f'www.{host}'}
            extra = os.getenv('ALLOWED_HOSTS', '')
            hosts.update(h.strip().lower() for h in extra.split(',') if h.strip())
            app.config['TRUSTED_HOSTS'] = sorted(hosts)


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    MYSQL_DB = 'tag_church_test'
    SQLALCHEMY_DATABASE_URI = f"mysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}/{MYSQL_DB}"  
    CACHE_TYPE = 'SimpleCache'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}