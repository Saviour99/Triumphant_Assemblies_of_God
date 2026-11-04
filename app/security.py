"""
Small, dependency-free security helpers shared by the public site, the
member area and the admin dashboard.

Kept free of module-level `app` imports so it can be imported from
app/__init__.py (limiter key function) without a circular import.
"""

import hashlib
import hmac
from urllib.parse import urlparse

from flask import current_app, has_request_context, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash


# ---------------------------------------------------------------- redirects

def safe_next_url(target):
    """Return `target` only if it's a same-site relative path, else None.

    Blocks open redirects through `?next=`: absolute URLs, scheme-relative
    `//evil.example`, backslash tricks (`/\\evil.example`, which browsers
    normalise to `//`), and anything with a scheme such as `javascript:`."""
    if not target or not isinstance(target, str):
        return None
    target = target.strip()
    if not target.startswith('/') or target.startswith('//') or '\\' in target:
        return None
    if any(ord(ch) < 32 for ch in target):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


# ------------------------------------------------------------ absolute URLs

def site_base_url():
    """Configured public base URL (SITE_URL), never derived from the
    request's Host header. Falls back to the request's own root only when
    SITE_URL is unset (development) — production refuses to start without
    it (config.ProductionConfig.init_app)."""
    base = (current_app.config.get('SITE_URL') or '').rstrip('/')
    if base:
        return base
    return request.url_root.rstrip("/") if has_request_context() else ""


def external_url(endpoint, **values):
    """Absolute URL for `endpoint` built on SITE_URL, so a forged Host
    header can't poison reset links, sitemap entries, etc."""
    return site_base_url() + url_for(endpoint, **values)


# ----------------------------------------------------------------- client IP

def client_ip():
    """Best-effort real client IP. With CLOUDFLARE_PROXY on, trusts the
    CF-Connecting-IP header (only safe when the origin accepts traffic from
    Cloudflare alone). Otherwise request.remote_addr, which ProxyFix
    already rewrites when TRUST_PROXY is on."""
    if current_app.config.get('CLOUDFLARE_PROXY'):
        cf_ip = (request.headers.get('CF-Connecting-IP') or '').strip()
        if cf_ip:
            return cf_ip[:64]
    return request.remote_addr or '127.0.0.1'


# ------------------------------------------------- password-bound tokens/sessions

def password_fingerprint(password_hash):
    """Short keyed digest of a user's current password hash. Embedded in
    reset tokens and the login session so both stop working the moment the
    password changes (reset tokens become single-use; other sessions are
    dropped). Keyed with SECRET_KEY so it reveals nothing about the hash."""
    key = current_app.config['SECRET_KEY'].encode('utf-8')
    return hmac.new(key, (password_hash or '').encode('utf-8'), hashlib.sha256).hexdigest()[:32]


def fingerprints_match(expected, password_hash):
    if not expected or not isinstance(expected, str):
        return False
    return hmac.compare_digest(expected, password_fingerprint(password_hash))


_DUMMY_HASH = None


def burn_password_check(raw_password):
    """Run a full password-hash check against a throwaway hash, so a login
    attempt for an unknown email takes as long as one for a real account
    (prevents user enumeration by response timing)."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = generate_password_hash('not-a-real-password-timing-equaliser')
    check_password_hash(_DUMMY_HASH, raw_password or '')
    return False


def bind_session_to_password(user):
    """Call right after login_user() (and after a user changes their own
    password) so app/__init__.py's user_loader keeps accepting this session
    only while the password stays the same."""
    from flask import session
    session['_pw_fp'] = password_fingerprint(user.password_hash)
