"""
Newsletter delivery through Resend (resend.com) Broadcasts + Contacts.

All HTTP goes through the shared low-level client app/resend_client.py
(`request()` / `send_email()` / ResendError) — this module only knows the
newsletter-specific endpoints:

    GET   /contacts?segment_id=..&limit=100&after=..   who's in the list
    GET   /contacts/{email}                            does a contact exist?
    POST  /contacts                                    create (+ add to segment)
    POST  /contacts/{email}/segments/{segment_id}      add existing contact
    POST  /broadcasts                                  create (draft)
    PATCH /broadcasts/{id}                             update a draft
    GET   /broadcasts/{id}                             status check
    POST  /broadcasts/{id}/send                        send
    DELETE /broadcasts/{id}                            remove a draft
    POST  /emails                                      the "send a test to me"

Resend renamed Audiences to Segments; RESEND_AUDIENCE_ID holds that
segment (formerly audience) id and is sent as `segment_id`.

Config (admin Integrations page via app/integrations.py, then app.config,
then the environment):
    RESEND_API_KEY      (read by app/resend_client.py)
    MAIL_REPLY_TO       fallback reply-to (normally the sending admin)
    RESEND_AUDIENCE_ID  segment/audience the newsletter goes to
    MAIL_FROM           verified sender, e.g. "Triumphant AG <news@church.org>"
    SITE_URL            absolute https base URL for images/links in emails
"""

import logging
import os
import time
from urllib.parse import quote

from flask import current_app

from app import resend_client
from app.resend_client import ResendError

log = logging.getLogger(__name__)

REQUIRED_KEYS = ('RESEND_API_KEY', 'RESEND_AUDIENCE_ID', 'MAIL_FROM', 'SITE_URL')
ALL_ENV_KEYS = REQUIRED_KEYS

# Resend's default API rate limit is a couple of requests per second per
# team, so contact sync paces its calls (resend_client also retries a 429
# once). Patched to 0 in tests.
SYNC_PAUSE = 0.55

# Placeholder Resend swaps for each recipient's own unsubscribe link in a
# Broadcast. Passed into the template as a value (the triple braces would
# otherwise be Jinja syntax).
UNSUBSCRIBE_PLACEHOLDER = '{{{RESEND_UNSUBSCRIBE_URL}}}'


class NewsletterError(Exception):
    """A newsletter delivery step failed. `detail` is safe to show admins."""

    def __init__(self, detail, status=None):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _wrap(exc):
    msg = exc.message or exc.name or 'Unknown error'
    if exc.status is None and exc.name == 'not_configured':
        return NewsletterError("Resend isn't connected yet (RESEND_API_KEY is not set).")
    if exc.status is None:
        return NewsletterError('Could not reach Resend. Check the server\'s internet connection.')
    return NewsletterError(f'{msg} (Resend {exc.status}{" " + exc.name if exc.name else ""})',
                           status=exc.status)


def _call(method, path, json=None, idempotency_key=None):
    try:
        return resend_client.request(method, path, json=json, idempotency_key=idempotency_key)
    except ResendError as exc:
        log.error('Resend %s %s failed: %s %s', method, path.split('?')[0], exc.status, exc.name)
        raise _wrap(exc)


# ============ CONFIG ============

# Settings the admin can save on the Integrations page (app/integrations.py,
# admin-saved > env > default). Read at call time so a change applies
# without a restart. SITE_URL is deploy config, so it stays config/env only.
INTEGRATION_KEYS = ('RESEND_AUDIENCE_ID', 'MAIL_FROM', 'MAIL_REPLY_TO')


def _cfg(key, default=''):
    val = None
    if key in INTEGRATION_KEYS:
        try:
            from app.integrations import get_integration
        except ImportError:  # integrations page not installed
            get_integration = None
        if get_integration is not None:
            val = get_integration(key, None)
    if val is None or val == '':
        val = current_app.config.get(key)
    if val is None or val == '':
        val = os.getenv(key, default)
    return (val or '').strip() if isinstance(val, str) else (val or '')


def missing_keys():
    """Names (never values) of settings still needed before sending."""
    missing = [] if resend_client.is_configured() else ['RESEND_API_KEY']
    return missing + [k for k in REQUIRED_KEYS if k != 'RESEND_API_KEY' and not _cfg(k)]


def is_configured():
    return not missing_keys()


def reply_to_for(admin_email):
    """Replies go to the admin who wrote/sent the newsletter; MAIL_REPLY_TO
    only if that account somehow has no email. (Resend's From must be on a
    verified domain, but reply_to may be any address.)"""
    return (admin_email or '').strip() or _cfg('MAIL_REPLY_TO')


def site_url():
    return _cfg('SITE_URL').rstrip('/')


def segment_id():
    return _cfg('RESEND_AUDIENCE_ID')


def from_address():
    return _cfg('MAIL_FROM')


# ============ CONTACTS ============

def _segment_contacts():
    """{email_lower: contact} for every contact currently in the segment."""
    out = {}
    after = None
    for _ in range(1000):  # hard stop: 100k contacts
        path = f'/contacts?segment_id={quote(segment_id())}&limit=100'
        if after:
            path += f'&after={quote(after)}'
        data = _call('GET', path)
        rows = data.get('data') or []
        for c in rows:
            if c.get('email'):
                out[c['email'].strip().lower()] = c
        if not data.get('has_more') or not rows:
            break
        after = rows[-1].get('id')
        time.sleep(SYNC_PAUSE)
    return out


def audience_count():
    """Subscribed contacts in the segment (unsubscribed ones are skipped by
    Resend when a Broadcast goes out)."""
    return sum(1 for c in _segment_contacts().values() if not c.get('unsubscribed'))


def sync_contacts(emails):
    """Make sure every website sign-up is a contact in the newsletter
    segment — without ever re-subscribing someone who opted out.

    Unsubscribing happens in Resend (the {{{RESEND_UNSUBSCRIBE_URL}}} link
    sets the contact's global `unsubscribed` flag), not in our
    newsletter_subscribers table. So:
      - already in the segment          -> left completely alone
      - exists in Resend, not in segment -> only added to the segment
        (POST /contacts/{email}/segments/{id}); `unsubscribed` is never
        sent, so an opted-out contact stays opted out (and an opted-out
        contact isn't added at all)
      - doesn't exist in Resend         -> created with unsubscribed=false
        and the segment
    We never call "create" for an address that already exists, because
    create carries `unsubscribed` and could flip an opt-out back.

    Returns {'new': n, 'added': n, 'skipped_unsubscribed': n, 'errors': n}.
    One bad address doesn't block the newsletter: per-address failures are
    counted and logged, not raised.
    """
    seg = segment_id()
    wanted = []
    seen = set()
    for e in emails:
        e = (e or '').strip().lower()
        if e and e not in seen:
            seen.add(e)
            wanted.append(e)

    current = _segment_contacts()
    totals = {'new': 0, 'added': 0, 'skipped_unsubscribed': 0, 'errors': 0}
    for email in wanted:
        if email in current:
            continue
        enc = quote(email, safe='@')
        try:
            time.sleep(SYNC_PAUSE)
            try:
                existing = resend_client.request('GET', f'/contacts/{enc}')
            except ResendError as exc:
                if exc.status != 404:
                    raise
                existing = None
            time.sleep(SYNC_PAUSE)
            if existing is None:
                resend_client.request('POST', '/contacts', json={
                    'email': email, 'unsubscribed': False, 'segments': [{'id': seg}],
                })
                totals['new'] += 1
            elif existing.get('unsubscribed'):
                totals['skipped_unsubscribed'] += 1
            else:
                resend_client.request('POST', f'/contacts/{enc}/segments/{quote(seg)}')
                totals['added'] += 1
        except ResendError as exc:
            if exc.status is None or exc.status in (401, 403):
                raise _wrap(exc)  # whole sync is doomed; stop early
            totals['errors'] += 1
            log.warning('Resend contact sync failed for one address: %s %s', exc.status, exc.name)
    return totals


# ============ BROADCASTS ============

def _broadcast_payload(subject, html, reply_to, name):
    payload = {
        'segment_id': segment_id(),
        'from': from_address(),
        'subject': subject,
        'html': html,
        'name': name,
    }
    if reply_to:
        payload['reply_to'] = reply_to
    return payload


def create_broadcast(subject, html, reply_to, name):
    data = _call('POST', '/broadcasts', json=_broadcast_payload(subject, html, reply_to, name))
    if not data.get('id'):
        raise NewsletterError('Resend did not return a broadcast id.')
    return data['id']


def update_broadcast(broadcast_id, subject, html, reply_to, name):
    return _call('PATCH', f'/broadcasts/{quote(broadcast_id)}',
                 json=_broadcast_payload(subject, html, reply_to, name))


def get_broadcast(broadcast_id):
    return _call('GET', f'/broadcasts/{quote(broadcast_id)}')


def broadcast_was_sent(data):
    """Anything past 'draft' (queued/sending/sent/scheduled) means Resend
    has accepted it for sending."""
    status = (data or {}).get('status') or 'draft'
    return status != 'draft'


def send_broadcast(broadcast_id):
    # The Idempotency-Key makes a retried send (e.g. after a timeout) a
    # no-op on Resend's side for 24h.
    return _call('POST', f'/broadcasts/{quote(broadcast_id)}/send', json={},
                 idempotency_key=f'newsletter-send-{broadcast_id}')


def delete_broadcast(broadcast_id):
    return _call('DELETE', f'/broadcasts/{quote(broadcast_id)}')


def send_test(to, subject, html, reply_to):
    try:
        return resend_client.send_email(
            from_address(), to, f'[Test] {subject}', html=html, reply_to=reply_to or None,
            tags={'category': 'newsletter_test'},
        )
    except ResendError as exc:
        log.error('Resend test email failed: %s %s', exc.status, exc.name)
        raise _wrap(exc)
