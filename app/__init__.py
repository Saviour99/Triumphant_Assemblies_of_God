"""
Flask Application Factory
Initializes and configures the TAG Church website application
"""

import pymysql
pymysql.install_as_MySQLdb()  # Use pymysql as a drop-in

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_compress import Compress
from flask_talisman import Talisman
import os
import logging
from logging.handlers import RotatingFileHandler

# Initialize extensions
db = SQLAlchemy()
cache = Cache()
compress = Compress()

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
    
    # Security headers with Talisman
    Talisman(app, 
        force_https=app.config.get('FORCE_HTTPS', False),
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        content_security_policy={
            'default-src': "'self'",
            'script-src': ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "www.youtube.com", "s.ytimg.com"],
            'style-src': ["'self'", "'unsafe-inline'", "fonts.googleapis.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"],
            'font-src': ["'self'", "fonts.gstatic.com", "cdnjs.cloudflare.com"],
            'img-src': ["'self'", "data:", "https:", "source.unsplash.com"],
            'frame-src': ["'self'", "www.youtube.com", "www.google.com"],
            'connect-src': ["'self'"],
        }
    )
    
    # Register blueprints
    from app.routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors"""
        return {'error': 'Page not found'}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        try:
            db.connection.rollback()
        except:
            pass
        app.logger.error(f'Server Error: {error}')
        return {'error': 'Internal server error'}, 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 errors"""
        return {'error': 'Access forbidden'}, 403
    
    # Context processors
    @app.context_processor
    def inject_church_info():
        """Inject church information into all templates"""
        return {
            'church_info': {
                'name': 'Triumphant Assemblies of God (TAG)',
                'address': 'Accra, Ghana',
                'phone': '+233 501 116 130',
                'email': 'info@tag.com',
                'digital_address': 'GA-123-456',
                'tagline': 'A Place of Triumph, Love & Purpose'
            }
        }
    
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
