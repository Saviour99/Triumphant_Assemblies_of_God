"""
Minimal Mailchimp Marketing API v3 client, called directly with `requests`
(no SDK — same approach as the Paystack integration in app/routes.py).

Config (all read from app.config, which config.py fills from .env):
    MAILCHIMP_API_KEY        "<key>-us21" style key
    MAILCHIMP_SERVER_PREFIX  "us21" — derived from the key's suffix if blank
    MAILCHIMP_AUDIENCE_ID    the audience (list) the newsletter goes to
    MAILCHIMP_FROM_NAME      sender display name
    MAILCHIMP_REPLY_TO       fallback reply-to address (see choose_reply_to)
    SITE_URL                 absolute https base URL for images/links in emails

Every call has a timeout. Any failure — network error, non-2xx response, a
response that isn't JSON — is raised as MailchimpError whose `detail` is
the human-readable explanation from Mailchimp's error body (their errors
are RFC 7807 problem documents: {"title", "status", "detail", ...}), so
the admin UI can show it directly. Nothing here logs the API key.
"""

import logging

import requests
from flask import current_app

log = logging.getLogger(__name__)

# (connect, read) seconds. Batch-subscribe of 500 members can take a few
# seconds on Mailchimp's side, so the read timeout is generous.
TIMEOUT = (5, 30)
BATCH_SIZE = 500  # Mailchimp's limit for POST /lists/{list_id}

REQUIRED_KEYS = ('MAILCHIMP_API_KEY', 'MAILCHIMP_AUDIENCE_ID', 'SITE_URL')
ALL_ENV_KEYS = (
    'MAILCHIMP_API_KEY', 'MAILCHIMP_SERVER_PREFIX', 'MAILCHIMP_AUDIENCE_ID',
    'MAILCHIMP_FROM_NAME', 'MAILCHIMP_REPLY_TO', 'SITE_URL',
)

# Consumer mailboxes publish strict DMARC policies, so Mailchimp can't send
# "from" them — it rewrites the From address to its own domain. Reply-to
# on these still works, but a church address on an authenticated domain
# (MAILCHIMP_REPLY_TO) is preferred when one is configured.
FREE_MAIL_DOMAINS = frozenset({
    'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk', 'ymail.com',
    'hotmail.com', 'hotmail.co.uk', 'outlook.com', 'live.com', 'msn.com',
    'aol.com', 'icloud.com', 'me.com', 'mac.com', 'proton.me',
    'protonmail.com', 'gmx.com', 'mail.com', 'zoho.com', 'yandex.com',
})


class MailchimpError(Exception):
    """A Mailchimp call failed. `detail` is safe to show to an admin."""

    def __init__(self, detail, status=None, title=None):
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.title = title


# ============ CONFIG ============

def _cfg(key, default=''):
    return (current_app.config.get(key) or default or '').strip()


def server_prefix():
    """Explicit MAILCHIMP_SERVER_PREFIX, else the data-center suffix of the
    API key ("abc123-us21" -> "us21"). '' if neither is usable."""
    prefix = _cfg('MAILCHIMP_SERVER_PREFIX')
    if prefix:
        return prefix
    key = _cfg('MAILCHIMP_API_KEY')
    if '-' in key:
        return key.rsplit('-', 1)[1]
    return ''


def missing_keys():
    """Names (never values) of the settings still needed before sending."""
    missing = [k for k in REQUIRED_KEYS if not _cfg(k)]
    if _cfg('MAILCHIMP_API_KEY') and not server_prefix():
        missing.append('MAILCHIMP_SERVER_PREFIX')
    return missing


def is_configured():
    return not missing_keys()


def site_url():
    return _cfg('SITE_URL').rstrip('/')


def from_name():
    return _cfg('MAILCHIMP_FROM_NAME', 'Triumphant Assemblies of God')


def choose_reply_to(admin_email):
    """Pick the campaign reply-to address for the admin who is sending.

    Mailchimp sends "from" the reply_to address, and expects it to be on a
    domain verified/authenticated in the account; otherwise it may
    substitute its own domain. The writing admin's own address is used by
    default. If that's a free-mail address (gmail etc.) and a church
    fallback MAILCHIMP_REPLY_TO is set, the fallback is used instead.

    Returns (address, hint) — hint is a short note for the admin, or None.
    """
    admin_email = (admin_email or '').strip()
    fallback = _cfg('MAILCHIMP_REPLY_TO')
    domain = admin_email.rsplit('@', 1)[-1].lower() if '@' in admin_email else ''
    if not admin_email:
        return fallback, None
    if domain in FREE_MAIL_DOMAINS:
        if fallback:
            return fallback, (
                f'Your account email is a {domain} address, so replies go to '
                f'{fallback} (MAILCHIMP_REPLY_TO) instead.'
            )
        return admin_email, (
            f'Your account email is a {domain} address. Mailchimp will send from '
            f'its own domain and replies still reach you, but setting '
            f'MAILCHIMP_REPLY_TO to an address on the church\'s own domain '
            f'(authenticated in Mailchimp) improves deliverability.'
        )
    return admin_email, None


# ============ HTTP ============

def _base_url():
    return f'https://{server_prefix()}.api.mailchimp.com/3.0'


def _request(method, path, json=None, params=None):
    if not is_configured():
        raise MailchimpError(
            "Mailchimp isn't connected yet. Missing settings: " + ', '.join(missing_keys())
        )
    url = _base_url() + path
    try:
        resp = requests.request(
            method, url,
            auth=('anystring', _cfg('MAILCHIMP_API_KEY')),
            json=json, params=params, timeout=TIMEOUT,
        )
    except requests.Timeout:
        log.error('Mailchimp %s %s timed out', method, path)
        raise MailchimpError('Mailchimp took too long to respond. Please try again.')
    except requests.RequestException as exc:
        log.error('Mailchimp %s %s failed: %s', method, path, exc.__class__.__name__)
        raise MailchimpError('Could not reach Mailchimp. Check the server\'s internet connection.')

    if resp.status_code == 204 or not resp.content:
        if resp.ok:
            return {}
    try:
        body = resp.json()
    except ValueError:
        body = None

    if not resp.ok:
        body = body if isinstance(body, dict) else {}
        detail = body.get('detail') or body.get('title') or f'HTTP {resp.status_code}'
        errors = body.get('errors')
        if isinstance(errors, list) and errors:
            extra = '; '.join(
                f"{e.get('field', '')}: {e.get('message', '')}".strip(': ')
                for e in errors[:3] if isinstance(e, dict)
            )
            if extra:
                detail = f'{detail} ({extra})'
        log.error('Mailchimp %s %s -> %s: %s', method, path, resp.status_code, detail)
        raise MailchimpError(detail, status=resp.status_code, title=body.get('title'))

    if body is None:
        raise MailchimpError('Mailchimp returned an unexpected response.', status=resp.status_code)
    return body


# ============ API CALLS ============

def audience_member_count():
    """Subscribed contacts in the configured audience, per Mailchimp."""
    data = _request('GET', f"/lists/{_cfg('MAILCHIMP_AUDIENCE_ID')}",
                    params={'fields': 'stats.member_count'})
    return int((data.get('stats') or {}).get('member_count') or 0)


def batch_subscribe(emails):
    """Add the website's newsletter sign-ups to the Mailchimp audience, in
    chunks of at most 500 (Mailchimp's per-request limit).

    update_existing is deliberately False and status_if_new is
    "subscribed": brand-new addresses are added as subscribed, but anyone
    already in the audience is left exactly as Mailchimp has them. That
    matters because unsubscribes happen in Mailchimp (the *|UNSUB|* link),
    not in our newsletter_subscribers table — with update_existing=True we
    would re-subscribe people who opted out every time we sent, which is
    both rude and a CAN-SPAM/GDPR problem.

    Returns totals: {'new': n, 'updated': n, 'errors': n, 'error_samples': [...]}.
    Per-address errors (e.g. an invalid or previously-cleaned address) are
    counted, not raised — one bad address shouldn't block the newsletter.
    """
    audience = _cfg('MAILCHIMP_AUDIENCE_ID')
    clean = []
    seen = set()
    for e in emails:
        e = (e or '').strip().lower()
        if e and e not in seen:
            seen.add(e)
            clean.append(e)

    totals = {'new': 0, 'updated': 0, 'errors': 0, 'error_samples': []}
    for i in range(0, len(clean), BATCH_SIZE):
        chunk = clean[i:i + BATCH_SIZE]
        data = _request('POST', f'/lists/{audience}', json={
            'members': [{'email_address': e, 'status_if_new': 'subscribed'} for e in chunk],
            'update_existing': False,
        })
        totals['new'] += int(data.get('total_created') or 0)
        totals['updated'] += int(data.get('total_updated') or 0)
        errs = data.get('errors') or []
        totals['errors'] += int(data.get('error_count') or len(errs))
        for err in errs[:5 - len(totals['error_samples'])]:
            totals['error_samples'].append(err.get('error') or '')
    return totals


def _settings(subject, preview_text, title, reply_to):
    return {
        'subject_line': subject,
        'preview_text': preview_text or '',
        'title': title,
        'from_name': from_name(),
        'reply_to': reply_to,
    }


def create_campaign(subject, preview_text, title, reply_to):
    """Create a regular campaign to the whole audience. Returns the
    campaign dict (id, recipients.recipient_count, ...)."""
    return _request('POST', '/campaigns', json={
        'type': 'regular',
        'recipients': {'list_id': _cfg('MAILCHIMP_AUDIENCE_ID')},
        'settings': _settings(subject, preview_text, title, reply_to),
    })


def update_campaign(campaign_id, subject, preview_text, title, reply_to):
    return _request('PATCH', f'/campaigns/{campaign_id}', json={
        'recipients': {'list_id': _cfg('MAILCHIMP_AUDIENCE_ID')},
        'settings': _settings(subject, preview_text, title, reply_to),
    })


def get_campaign(campaign_id):
    return _request('GET', f'/campaigns/{campaign_id}',
                    params={'fields': 'id,status,emails_sent,recipients.recipient_count'})


def set_content(campaign_id, html):
    return _request('PUT', f'/campaigns/{campaign_id}/content', json={'html': html})


def send_test(campaign_id, emails):
    return _request('POST', f'/campaigns/{campaign_id}/actions/test',
                    json={'test_emails': list(emails), 'send_type': 'html'})


def send(campaign_id):
    return _request('POST', f'/campaigns/{campaign_id}/actions/send')


def delete_campaign(campaign_id):
    """Removes a Mailchimp-side *draft* campaign (an API call, not SQL)."""
    return _request('DELETE', f'/campaigns/{campaign_id}')
