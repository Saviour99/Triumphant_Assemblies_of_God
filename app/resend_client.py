"""
Low-level Resend (resend.com) REST client — the single place the app talks
to the Resend API. Shared by transactional email (app/email_utils.py) and
anything else that needs Resend (e.g. newsletter Broadcasts/Audiences).

Plain `requests`, no SDK (same style as the Paystack and Mailchimp code).

    request(method, path, json=None, idempotency_key=None) -> dict
        Generic call, e.g. request('POST', '/emails', json={...}).
        Raises ResendError on any failure (network, non-2xx, bad JSON).
    send_email(...) -> str
        POST /emails; returns the Resend email id. Raises ResendError.
    is_configured() -> bool
        True when RESEND_API_KEY is set.

Retry policy: one retry after a short backoff on HTTP 5xx, on 429
`rate_limit_exceeded` (never on daily/monthly quota 429s — retrying can't
help), on 409 `concurrent_idempotent_requests`, and on network errors when
the call is safe to repeat (GET, or a request carrying an Idempotency-Key,
which Resend de-duplicates for 24h). The same Idempotency-Key is reused on
the retry, so a retried POST /emails can never send twice.

Errors are logged by callers; ResendError carries only the HTTP status, the
Resend error name and its message — never the API key or request body.
"""

import os
import time

import requests
from flask import current_app

BASE_URL = 'https://api.resend.com'
TIMEOUT = 10          # seconds, per attempt
RETRY_DELAY = 1.0     # seconds before the single retry

# 429 names worth retrying; quota exhaustion is not.
_RETRYABLE_429 = {'rate_limit_exceeded'}
_RETRYABLE_409 = {'concurrent_idempotent_requests', 'resource_locked'}


class ResendError(Exception):
    """A failed Resend call. `status` is the HTTP status (None for a
    network error), `name` Resend's error type (e.g. 'validation_error'),
    `message` its human-readable message."""

    def __init__(self, status, name, message):
        self.status = status
        self.name = name or ''
        self.message = message or ''
        super().__init__(f"Resend error {status} {self.name}: {self.message}".strip())


def _cfg(key, default=''):
    """Read a setting at call time: admin-saved integration value
    (app/integrations.py::get_integration) > app.config > env > default.
    The integrations module is imported lazily; if it isn't there (or
    fails), fall back to config/env."""
    val = None
    try:
        from app.integrations import get_integration
        val = get_integration(key, None)
    except Exception:  # noqa: BLE001 — missing module / no app context
        val = None
    if val is None or val == '':
        try:
            val = current_app.config.get(key)
        except RuntimeError:  # outside an app context
            val = None
    if val is None or val == '':
        val = os.getenv(key, default)
    return (val or '').strip() if isinstance(val, str) else val


get_setting = _cfg  # public alias for other modules


def api_key():
    return _cfg('RESEND_API_KEY')


def is_configured():
    return bool(api_key())


def _parse_error(resp):
    """Resend errors look like {"statusCode": 422, "name": "...",
    "message": "..."}; tolerate anything else."""
    name, message = '', ''
    try:
        data = resp.json()
        if isinstance(data, dict):
            name = str(data.get('name') or '')
            message = str(data.get('message') or data.get('error') or '')
    except ValueError:
        pass
    if not message:
        message = (getattr(resp, 'reason', '') or 'HTTP error')
    return ResendError(resp.status_code, name, message[:300])


def _should_retry(err, can_repeat):
    if err.status is None:
        return can_repeat
    if err.status >= 500:
        return True
    if err.status == 429:
        return err.name in _RETRYABLE_429 or not err.name
    if err.status == 409:
        return err.name in _RETRYABLE_409
    return False


def request(method, path, json=None, idempotency_key=None, timeout=TIMEOUT):
    """Call the Resend API and return the decoded JSON (dict; {} for an
    empty body). Raises ResendError on failure."""
    key = api_key()
    if not key:
        raise ResendError(None, 'not_configured', 'RESEND_API_KEY is not set')

    method = method.upper()
    url = BASE_URL + (path if path.startswith('/') else '/' + path)
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'User-Agent': 'triumphant-ag-church/1.0',
    }
    if idempotency_key:
        headers['Idempotency-Key'] = str(idempotency_key)[:256]
    can_repeat = method == 'GET' or bool(idempotency_key)

    last_err = None
    for attempt in range(2):
        if attempt:
            time.sleep(RETRY_DELAY)
        try:
            resp = requests.request(method, url, json=json, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_err = ResendError(None, type(e).__name__, 'network error contacting Resend')
        else:
            if 200 <= resp.status_code < 300:
                if not resp.content:
                    return {}
                try:
                    data = resp.json()
                except ValueError:
                    raise ResendError(resp.status_code, 'invalid_response', 'non-JSON success body')
                return data if isinstance(data, dict) else {'data': data}
            last_err = _parse_error(resp)
        if attempt == 0 and _should_retry(last_err, can_repeat):
            continue
        break
    raise last_err


def send_email(from_addr, to, subject, html=None, text=None, reply_to=None,
               tags=None, idempotency_key=None):
    """POST /emails. `to` is a string or list; `tags` a dict or list of
    {name, value} (ASCII letters/digits/_/- only). Returns the email id."""
    payload = {
        'from': from_addr,
        'to': [to] if isinstance(to, str) else list(to),
        'subject': subject,
    }
    if html is not None:
        payload['html'] = html
    if text is not None:
        payload['text'] = text
    if reply_to:
        payload['reply_to'] = reply_to
    if tags:
        if isinstance(tags, dict):
            tags = [{'name': k, 'value': v} for k, v in tags.items()]
        payload['tags'] = list(tags)
    data = request('POST', '/emails', json=payload, idempotency_key=idempotency_key)
    return data.get('id', '')
