import os
from app import create_app

if __name__ == '__main__':
    config_name = os.getenv('FLASK_ENV', 'development')
    app = create_app(config_name)
    # Development server only (production runs under gunicorn). Binds to
    # localhost by default so the Werkzeug debugger — which allows arbitrary
    # code execution — is never reachable from the network. Set RUN_HOST
    # deliberately to override (and FLASK_DEBUG=0 if you do).
    host = os.getenv('RUN_HOST', '127.0.0.1')
    port = int(os.getenv('PORT', '5001'))
    debug_env = os.getenv('FLASK_DEBUG')
    if debug_env is None:
        debug = bool(app.config.get('DEBUG', False))
    else:
        debug = debug_env.strip().lower() in ('1', 'true', 'yes', 'on')
    app.run(debug=debug, host=host, port=port)
