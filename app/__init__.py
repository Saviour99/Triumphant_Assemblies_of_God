"""
Flask Application Factory
Initializes and configures the TAG Church website application
"""

import pymysql
pymysql.install_as_MySQLdb()  # Use pymysql as a drop-in

from flask import Flask, session
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
limiter = Limiter(key_func=get_remote_address, default_limits=['200 per day', '50 per hour'])

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
        if kind == 'admin':
            return db.session.get(Admin, int(raw_id))
        if kind == 'member':
            return db.session.get(Member, int(raw_id))
        return None

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
    # "remember me" style session used elsewhere.
    @app.before_request
    def enforce_admin_session_timeout():
        from flask import request
        from flask_login import current_user, logout_user
        from datetime import datetime
        if not request.path.startswith('/admin'):
            return
        from app.models import Admin
        if current_user.is_authenticated and isinstance(current_user, Admin):
            last_seen = session.get('admin_last_seen')
            now = datetime.utcnow().timestamp()
            timeout = app.config['ADMIN_SESSION_LIFETIME'].total_seconds()
            if last_seen and (now - last_seen) > timeout:
                logout_user()
                session.clear()
            else:
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
            live_stream = LiveStreamSetting.query.get(1)
        except Exception:
            live_stream = None

        # Live counts for the blog sidebar's Categories widget — computed
        # once here instead of duplicated in every /blog/* route.
        try:
            blog_category_counts = {
                'devotional': Devotion.query.count(),
                'worship': Ebook.query.filter_by(category='worship').count(),
                'leadership': Ebook.query.filter_by(category='leadership').count(),
                'testimonies': Testimony.query.count(),
            }
        except Exception:
            blog_category_counts = {'devotional': 0, 'worship': 0, 'leadership': 0, 'testimonies': 0}

        return {
            'church_info': {
                'name': 'Triumphant Assemblies of God (TAG)',
                'address': 'Zuman, between Atomic and Glefe, Accra, Ghana',
                'phone': '+233 501 116 130',
                'email': 'info@tag.com',
                'digital_address': 'GA-123-456',
                'tagline': 'A Place of Triumph, Love & Purpose'
            },
            'live_stream': live_stream,
            'blog_category_counts': blog_category_counts,
            'paystack_public_key': app.config.get('PAYSTACK_PUBLIC_KEY', '')
        }

    @app.template_global()
    def youtube_embed_url(url):
        """Turn a youtube.com/watch?v=... or youtu.be/... URL into an embeddable one."""
        if not url:
            return ''
        if 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
        elif 'v=' in url:
            video_id = url.split('v=')[-1].split('&')[0]
        elif '/embed/' in url:
            return url
        else:
            return url
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
