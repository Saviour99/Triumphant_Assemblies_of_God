"""
Admin-editable integration settings (email provider credentials etc.).

Other modules read settings ONLY through:

    from app.integrations import get_integration
    api_key = get_integration('RESEND_API_KEY')            # '' / None if unset
    sender  = get_integration('MAIL_FROM', 'Church <no-reply@example.org>')

Precedence: value saved by the developer in /admin/integrations
            > current_app.config[key] / os.environ[key]
            > `default`.

Every value is stored Fernet-encrypted in the `integration_settings` table
(see init_db.py). The Fernet key comes from INTEGRATIONS_ENCRYPTION_KEY if
set, otherwise it is derived from SECRET_KEY with HKDF-SHA256. If that key
changes, saved values can no longer be decrypted: they are treated as unset
(falling back to .env) and the admin page shows "needs re-entering".

Caching: only the *ciphertext* rows are cached (Flask-Caching, short TTL) so
plaintext secrets never land in Redis; decryption happens in-process on each
read. The cache is invalidated on every save/remove.

get_integration() never raises: if the table doesn't exist yet (init_db.py
not run) or the DB is unavailable it logs once and falls back to env.
"""

import base64
import logging
import os
import re

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app

log = logging.getLogger(__name__)

# key -> metadata used by the admin page. Order = display order.
INTEGRATION_KEYS = {
    'RESEND_API_KEY': {
        'label': 'Resend API key', 'secret': True,
        'help': 'Resend dashboard → API Keys → Create API key (starts with "re_"). '
                'Use "Sending access" unless the newsletter needs Audiences, '
                'which requires "Full access".',
    },
    'RESEND_AUDIENCE_ID': {
        'label': 'Audience ID', 'secret': False,
        'help': 'Resend dashboard → Audiences → open the audience → copy its ID '
                '(used for newsletter contacts/broadcasts).',
    },
    'MAIL_FROM': {
        'label': 'From address', 'secret': False,
        'help': 'e.g. Triumphant AG <no-reply@yourdomain.org>. The domain must be '
                'verified first under Resend dashboard → Domains.',
    },
    'MAIL_REPLY_TO': {
        'label': 'Reply-to address', 'secret': False,
        'help': 'Where replies to automated emails go (e.g. the church office inbox).',
    },
    'MAIL_NOTIFY_TO': {
        'label': 'Notification inbox', 'secret': False,
        'help': 'Inbox that receives admin notifications (new prayer requests, '
                'messages, donations).',
    },
}

CACHE_KEY = 'integration_settings:ciphertexts:v1'
CACHE_TTL = 60  # seconds

_HKDF_SALT = b'tag-church/integration-settings/v1'
_HKDF_INFO = b'fernet-key:integration_settings'

_warned_unavailable = False


# ---------------------------------------------------------------- crypto ---

def _fernet():
    """Fernet built from INTEGRATIONS_ENCRYPTION_KEY or HKDF(SECRET_KEY)."""
    cfg = current_app.config
    raw = cfg.get('INTEGRATIONS_ENCRYPTION_KEY') or os.getenv('INTEGRATIONS_ENCRYPTION_KEY')
    if raw:
        material = raw.encode('utf-8')
        # Accept a ready-made Fernet key (Fernet.generate_key()) as-is.
        try:
            if len(base64.urlsafe_b64decode(material)) == 32:
                return Fernet(material)
        except Exception:
            pass
    else:
        material = (cfg.get('SECRET_KEY') or '').encode('utf-8')
    derived = HKDF(algorithm=hashes.SHA256(), length=32,
                   salt=_HKDF_SALT, info=_HKDF_INFO).derive(material)
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_value(plaintext):
    return _fernet().encrypt((plaintext or '').encode('utf-8')).decode('ascii')


def decrypt_value(token):
    """Plaintext, or None if the token can't be decrypted (key changed)."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError):
        return None


# ----------------------------------------------------------------- reads ---

def _saved_ciphertexts():
    """{key: value_encrypted} for all saved rows; {} if the table is missing."""
    global _warned_unavailable
    from app import cache
    try:
        rows = cache.get(CACHE_KEY)
    except Exception:
        rows = None
    if rows is not None:
        return rows
    try:
        from app import db
        from app.models import IntegrationSetting
        rows = {r.setting_key: r.value_encrypted
                for r in db.session.query(IntegrationSetting).all()}
    except Exception as exc:  # table missing / DB down -> env fallback
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        if not _warned_unavailable:
            log.warning('integration_settings unavailable (%s); using .env values. '
                        'Run init_db.py to create the table.', type(exc).__name__)
            _warned_unavailable = True
        return {}
    try:
        cache.set(CACHE_KEY, rows, timeout=CACHE_TTL)
    except Exception:
        pass
    return rows


def invalidate_cache():
    from app import cache
    try:
        cache.delete(CACHE_KEY)
    except Exception:
        pass


def _env_value(key):
    try:
        val = current_app.config.get(key)
    except RuntimeError:
        val = None
    if val in (None, ''):
        val = os.getenv(key)
    return val if val not in (None, '') else None


def get_integration(key, default=None):
    """Admin-saved value > app config / env > default. Never raises."""
    try:
        token = _saved_ciphertexts().get(key)
        if token:
            val = decrypt_value(token)
            if val:
                return val
        val = _env_value(key)
        return val if val is not None else default
    except Exception:
        log.exception('get_integration(%s) failed; returning default', key)
        return default


def integration_status(key):
    """For the admin page: {'source': 'admin'|'env'|'unset', 'needs_reentry',
    'masked'} — never contains a secret value."""
    meta = INTEGRATION_KEYS.get(key, {})
    token = _saved_ciphertexts().get(key)
    needs_reentry = False
    val, source = None, 'unset'
    if token:
        val = decrypt_value(token)
        if val:
            source = 'admin'
        else:
            needs_reentry = True
    if source == 'unset':
        val = _env_value(key)
        if val:
            source = 'env'
    if meta.get('secret'):
        display = mask_secret(val) if val else ''
    else:
        display = val or ''
    return {'source': source, 'needs_reentry': needs_reentry, 'display': display}


def mask_secret(val):
    if not val:
        return ''
    prefix = 're_' if val.startswith('re_') else ''
    return f'{prefix}••••{val[-4:]}' if len(val) > 8 else '••••'


# ---------------------------------------------------------------- writes ---

def set_integration(key, value, admin_id=None):
    """Upsert an encrypted value. Caller commits."""
    from app import db
    from app.models import IntegrationSetting
    from datetime import datetime
    row = db.session.query(IntegrationSetting).filter_by(setting_key=key).first()
    if row is None:
        row = IntegrationSetting(setting_key=key)
        db.session.add(row)
    row.value_encrypted = encrypt_value(value)
    row.is_secret = bool(INTEGRATION_KEYS.get(key, {}).get('secret'))
    row.updated_by_admin_id = admin_id
    row.updated_at = datetime.utcnow()


def remove_integration(key):
    """Delete the single saved row for `key` (falls back to .env). Caller commits."""
    from app import db
    from app.models import IntegrationSetting
    row = db.session.query(IntegrationSetting).filter_by(setting_key=key).first()
    if row is not None:
        db.session.delete(row)
        return True
    return False


# ------------------------------------------------------------ validation ---

_EMAIL_RE = re.compile(r'^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$')
_NAMED_RE = re.compile(r'^\s*([^<>]+?)\s*<\s*([^<>\s]+)\s*>\s*$')


def valid_address(value, allow_name=True):
    value = (value or '').strip()
    if _EMAIL_RE.match(value):
        return True
    if allow_name:
        m = _NAMED_RE.match(value)
        return bool(m and _EMAIL_RE.match(m.group(2)))
    return False
