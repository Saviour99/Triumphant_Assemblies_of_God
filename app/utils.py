"""
Shared input-sanitization and content-validation helpers, used by both the
public API endpoints (app/routes.py) and the admin dashboard (app/admin.py).
"""

import re
from urllib.parse import urlparse

import email_validator as _email_validator_module
from email_validator import validate_email as _validate_email_lib, EmailNotValidError, caching_resolver

# WTForms' Email(check_deliverability=True) uses email-validator's global
# DNS timeout (15s by default) — too long to block a request worker on.
_email_validator_module.DEFAULT_TIMEOUT = 3

from app import cache

HTML_TAG_PATTERN = re.compile(r'<[^>]*>')
DANGEROUS_CHARS_PATTERN = re.compile(r'[<>"\'%;()&+]')

YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}

# Reused across calls so repeated submissions for the same domain (e.g. many
# @gmail.com signups) hit an in-memory DNS cache instead of a fresh lookup
# each time. This is process-local, separate from Flask-Caching.
_dns_resolver = caching_resolver(timeout=3)  # short: runs inside request handlers


def validate_email(email):
    """Validate email syntax AND confirm the domain can actually receive
    mail (MX/A record lookup), so a well-formed but made-up address like
    'name@fake123xyz.com' is rejected, not just malformed ones. Fails open
    (accepts the address) only when the DNS check itself errors out for a
    reason unrelated to deliverability, so a transient resolver hiccup on
    our end can't block a real user from submitting a form."""
    if not email:
        return False
    try:
        _validate_email_lib(email, check_deliverability=True, dns_resolver=_dns_resolver)
        return True
    except EmailNotValidError:
        return False


def sanitize_text(text):
    """Strip HTML tags and other dangerous characters from free-text input.
    Used on every admin/public form field before it's persisted, so stored
    values can never carry markup/script content even though Jinja2 already
    autoescapes on render (defense in depth)."""
    if not text:
        return ''
    text = text.strip()
    text = HTML_TAG_PATTERN.sub('', text)
    text = DANGEROUS_CHARS_PATTERN.sub('', text)
    return text


def sanitize_multiline_text(text):
    """Same as sanitize_text, but preserves line breaks — for fields where
    each line is a distinct item (e.g. one prayer point per line) rather
    than a single paragraph. Blank lines are dropped."""
    if not text:
        return ''
    lines = [sanitize_text(line) for line in text.splitlines()]
    return '\n'.join(line for line in lines if line)


def is_youtube_url(url):
    """Only allow youtube.com/youtu.be URLs — this value gets embedded
    directly in an <iframe src>, so it must not accept arbitrary URLs."""
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    return parsed.scheme in ('http', 'https') and parsed.netloc.lower() in YOUTUBE_HOSTS


# Known file signatures ("magic bytes") for the audio formats this project
# accepts. Extension/MIME-type checks alone can be spoofed by renaming an
# arbitrary file — this verifies the actual file content.
_MP3_ID3_SIGNATURE = b'ID3'


def _looks_like_mp3_frame_sync(first_two_bytes):
    if len(first_two_bytes) < 2:
        return False
    return first_two_bytes[0] == 0xFF and (first_two_bytes[1] & 0xE0) == 0xE0


def _looks_like_mp4_ftyp(header_bytes):
    # ISO base media file format: bytes 4-7 spell out "ftyp".
    return len(header_bytes) >= 8 and header_bytes[4:8] == b'ftyp'


def is_valid_audio_file(file_storage):
    """Check the uploaded file's actual bytes look like MP3/MP4 audio,
    not just its filename extension. Reads a small header, then rewinds
    the stream so the caller can still .save() the full file afterward."""
    try:
        header = file_storage.stream.read(12)
    finally:
        file_storage.stream.seek(0)

    if not header:
        return False

    if header[:3] == _MP3_ID3_SIGNATURE:
        return True
    if _looks_like_mp3_frame_sync(header[:2]):
        return True
    if _looks_like_mp4_ftyp(header):
        return True
    return False


_IMAGE_SIGNATURES = (
    b'\xff\xd8\xff',        # JPEG
    b'\x89PNG\r\n\x1a\n',   # PNG
    b'GIF87a',               # GIF
    b'GIF89a',
)


def is_valid_image_file(file_storage):
    """Same idea as is_valid_audio_file, for avatar photo uploads."""
    try:
        header = file_storage.stream.read(8)
    finally:
        file_storage.stream.seek(0)

    if not header:
        return False
    return any(header.startswith(sig) for sig in _IMAGE_SIGNATURES)


def is_valid_pdf_file(file_storage):
    """Same idea again, for e-book uploads."""
    try:
        header = file_storage.stream.read(5)
    finally:
        file_storage.stream.seek(0)

    if not header:
        return False
    return header.startswith(b'%PDF-')


@cache.memoize(timeout=300)
def get_ebooks_by_category(category):
    """Cached e-book reading-list query for the public /blog/worship and
    /blog/leadership pages. Only the DB fetch is cached (not the rendered
    page), so the live per-request CSRF token in the page is never stale.
    Invalidated from app/admin.py's ebook add/edit/delete routes."""
    from app.models import Ebook
    return Ebook.query.filter_by(category=category).order_by(Ebook.title.asc()).all()


def is_valid_photo_file(file_storage):
    """Magic-byte check for photo uploads that accept JPEG, PNG or WebP
    (member/admin testimony photos). WebP is a RIFF container whose bytes
    8-11 spell 'WEBP'."""
    try:
        header = file_storage.stream.read(12)
    finally:
        file_storage.stream.seek(0)

    if not header:
        return False
    if header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
    return header[:4] == b'RIFF' and header[8:12] == b'WEBP'


@cache.memoize(timeout=300)
def get_testimonies(limit=None):
    """Cached query of APPROVED testimonies for /blog and /blog/testimonies.
    Pending/rejected member submissions are never public. Invalidated from
    the admin testimony routes (app/admin_manage.py)."""
    from app.models import Testimony
    query = Testimony.query.filter_by(status='approved').order_by(Testimony.created_at.desc())
    return query.limit(limit).all() if limit else query.all()
