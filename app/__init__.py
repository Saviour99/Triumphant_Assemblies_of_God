"""
Flask Application Factory
Initializes and configures the TAG Church website application
"""

import pymysql
pymysql.install_as_MySQLdb()  # Use pymysql as a drop-in

from flask import Flask, session, request as _request
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_compress import Compress
from flask_talisman import Talisman
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
from logging.handlers import RotatingFileHandler

# Initialize extensions
db = SQLAlchemy()
cache = Cache()
compress = Compress()
login_manager = LoginManager()
csrf = CSRFProtect()


def _rate_limit_key():
    """Client IP for rate limiting — CF-Connecting-IP when CLOUDFLARE_PROXY
    is on (otherwise every visitor would share Cloudflare's edge IP)."""
    from app.security import client_ip
    try:
        return client_ip()
    except RuntimeError:
        return get_remote_address()


# Generous default so normal browsing (page + assets) is never throttled;
# write/auth endpoints carry their own tighter limits. Static files exempt.
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=['600 per hour', '120 per minute'],
    default_limits_exempt_when=lambda: _request.endpoint == 'static',
)

def create_app(config_name='development'):
    """
    Application factory function
    Creates and configures the Flask application
    
    Args:
        config_name: Configuration environment (development, production, testing)
    
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    from config import config
    app.config.from_object(config[config_name])
    # Production refuses to start without a real SECRET_KEY / SITE_URL and
    # derives TRUSTED_HOSTS (Host-header allow-list) from SITE_URL.
    config[config_name].init_app(app)

    if app.config.get('TRUST_PROXY'):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Initialize extensions
    db.init_app(app)
    cache.init_app(app)
    compress.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.init_app(app)
    login_manager.session_protection = 'strong'

    @login_manager.user_loader
    def load_user(compound_id):
        from app.models import Admin, Member
        try:
            kind, raw_id = compound_id.split(':', 1)
        except ValueError:
            return None
        try:
            pk = int(raw_id)
        except ValueError:
            return None
        if kind == 'admin':
            user = db.session.get(Admin, pk)
        elif kind == 'member':
            user = db.session.get(Member, pk)
        else:
            return None
        # Drop the session if the account was deactivated, or if its
        # password changed since this session logged in (the session
        # carries a fingerprint of the password hash — see app/security.py).
        if user is None or not user.is_active:
            return None
        from app.security import fingerprints_match
        if not fingerprints_match(session.get('_pw_fp'), user.password_hash):
            return None
        return user

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request, redirect, url_for
        if request.path.startswith('/admin'):
            return redirect(url_for('admin.login', next=request.path))
        return redirect(url_for('auth.login', next=request.path))

    # Security headers with Talisman
    Talisman(app,
        force_https=app.config.get('FORCE_HTTPS', False),
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        content_security_policy={
            'default-src': "'self'",
            'object-src': "'none'",
            'base-uri': "'self'",
            'form-action': ["'self'", "checkout.paystack.com"],
            'frame-ancestors': "'self'",
            'media-src': "'self'",
            'script-src': ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "www.youtube.com", "s.ytimg.com", "js.paystack.co"],
            'style-src': ["'self'", "'unsafe-inline'", "fonts.googleapis.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"],
            'font-src': ["'self'", "fonts.gstatic.com", "cdnjs.cloudflare.com"],
            'img-src': ["'self'", "data:", "https:", "source.unsplash.com"],
            'frame-src': ["'self'", "www.youtube.com", "www.google.com", "maps.google.com", "checkout.paystack.com"],
            'connect-src': ["'self'", "api.paystack.co", "checkout.paystack.com"],
        }
    )

    # Register blueprints
    from app.routes import main_bp, api_bp
    from app.admin import admin_bp
    from app.auth import auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)

    # Uploaded audio lives under this folder; created idempotently (never
    # removed/recreated destructively) since it isn't checked into git.
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audio'), exist_ok=True)

    # Admin sessions get a shorter idle timeout than the general 7-day
    # "remember me" style session used elsewhere, plus an absolute cap.
    # Background polling (dashboard auto-refresh) must not count as
    # activity, or an unattended dashboard tab would never time out.
    BACKGROUND_POLL_ENDPOINTS = {'admin.recent_activity', 'admin.chart_data'}

    @app.before_request
    def enforce_admin_session_timeout():
        from flask import request
        from flask_login import current_user, logout_user
        import time
        if not request.path.startswith('/admin'):
            return
        from app.models import Admin
        if current_user.is_authenticated and isinstance(current_user, Admin):
            now = time.time()
            last_seen = session.get('admin_last_seen')
            login_at = session.get('admin_login_at')
            if login_at is None:
                # Session from before the absolute cap existed — start it now.
                login_at = session['admin_login_at'] = now
            idle_timeout = app.config['ADMIN_SESSION_LIFETIME'].total_seconds()
            absolute_timeout = app.config['ADMIN_ABSOLUTE_SESSION_LIFETIME'].total_seconds()
            if (last_seen and (now - last_seen) > idle_timeout) or (now - login_at) > absolute_timeout:
                logout_user()
                session.clear()
                return
            is_background_poll = (
                request.endpoint in BACKGROUND_POLL_ENDPOINTS
                or request.headers.get('X-Background-Poll') == '1'
            )
            if not is_background_poll or last_seen is None:
                session['admin_last_seen'] = now

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors"""
        return {'error': 'Page not found'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        db.session.rollback()
        app.logger.error(f'Server Error: {error}')
        return {'error': 'Internal server error'}, 500

    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 errors"""
        return {'error': 'Access forbidden'}, 403

    @app.errorhandler(413)
    def file_too_large_error(error):
        """Handle uploads exceeding MAX_CONTENT_LENGTH"""
        return {'error': 'File is too large'}, 413

    @app.errorhandler(429)
    def rate_limit_error(error):
        """Handle requests exceeding a Flask-Limiter rate limit"""
        return {'error': 'Too many requests. Please try again later.'}, 429

    # Context processors
    @app.context_processor
    def inject_church_info():
        """Inject church information into all templates"""
        from app.models import LiveStreamSetting, Devotion, Ebook, Testimony
        try:
            live_stream = db.session.get(LiveStreamSetting, 1)
        except Exception:
            live_stream = None

        # Live counts for the blog sidebar's Categories widget — computed
        # once here instead of duplicated in every /blog/* route. Cached for
        # 60s: this runs on EVERY template render (admin pages included), so
        # uncached it was 4 extra COUNT queries per page view.
        blog_category_counts = cache.get('blog_category_counts')
        if blog_category_counts is None:
            try:
                blog_category_counts = {
                    'devotional': Devotion.query.count(),
                    'worship': Ebook.query.filter_by(category='worship').count(),
                    'leadership': Ebook.query.filter_by(category='leadership').count(),
                    'testimonies': Testimony.query.filter_by(status='approved').count(),
                }
                cache.set('blog_category_counts', blog_category_counts, timeout=60)
            except Exception:
                blog_category_counts = {'devotional': 0, 'worship': 0, 'leadership': 0, 'testimonies': 0}

        from app.security import site_base_url
        from app.site_settings import get_church_info

        # Admin-editable site info (developer/pastor, /admin/site-settings),
        # cached and invalidated on save; falls back to the shipped defaults
        # if the site_settings table is empty or unreadable.
        church_info = get_church_info()

        return {
            'church_info': church_info,
            'site_settings': church_info,
            'live_stream': live_stream,
            'blog_category_counts': blog_category_counts,
            'paystack_public_key': app.config.get('PAYSTACK_PUBLIC_KEY', ''),
            # Absolute public base URL (no trailing slash) from SITE_URL —
            # use instead of request.url_root (Host-header controlled).
            'site_url': site_base_url(),
        }

    @app.template_global()
    def youtube_embed_url(url):
        """Turn a youtube.com/watch?v=... or youtu.be/... URL into an embeddable one."""
        # Only ever emits https://www.youtube.com/embed/<11-char id>; anything
        # that doesn't yield a well-formed video id renders nothing.
        import re
        from urllib.parse import urlparse, parse_qs
        if not url:
            return ''
        try:
            parsed = urlparse(url.strip())
        except ValueError:
            return ''
        host = (parsed.hostname or '').lower()
        if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtube-nocookie.com'):
            return ''
        video_id = ''
        if host == 'youtu.be':
            video_id = parsed.path.lstrip('/').split('/')[0]
        elif parse_qs(parsed.query).get('v'):
            video_id = parse_qs(parsed.query)['v'][0]
        else:
            parts = [p for p in parsed.path.split('/') if p]
            if len(parts) >= 2 and parts[0] in ('embed', 'live', 'shorts', 'v'):
                video_id = parts[1]
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id or ''):
            return ''
        return f'https://www.youtube.com/embed/{video_id}'

    # Health check endpoint
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring"""
        return {'status': 'healthy', 'service': 'TAG Church Website'}, 200

    # Setup logging
    setup_logging(app)

    return app


def setup_logging(app):
    """Configure application logging"""
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        # File handler
        file_handler = RotatingFileHandler('logs/tag_church.log', maxBytes=10240000, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('TAG Church Website startup')
