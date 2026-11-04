"""
Transactional email tests (app/email_utils.py + app/resend_client.py).
Self-contained SQLite app; every HTTP call is mocked — no network.
"""
import logging
from unittest import mock

import pytest
import requests

import config as config_module
from app import create_app, db as _db
from app import email_utils, resend_client
from app.models import Admin, Member

MAIL_KEYS = ('RESEND_API_KEY', 'MAIL_FROM', 'MAIL_REPLY_TO', 'MAIL_NOTIFY_TO',
             'SMTP_HOST', 'SMTP_FROM', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_PORT')
SITE = 'https://church.example.org'
SENDER = 'Triumphant Assemblies of God <no-reply@mail.church.example.org>'


@pytest.fixture
def mail_app(tmp_path, monkeypatch):
    for k in MAIL_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(config_module.TestingConfig, 'SQLALCHEMY_DATABASE_URI',
                        f"sqlite:///{tmp_path / 'mail.db'}")
    monkeypatch.setattr(config_module.TestingConfig, 'CACHE_TYPE', 'SimpleCache')
    monkeypatch.setattr(resend_client, 'RETRY_DELAY', 0)
    app = create_app('testing')
    app.config['RATELIMIT_ENABLED'] = False
    for k in MAIL_KEYS:
        app.config[k] = ''
    app.config['SITE_URL'] = SITE
    with app.app_context():
        _db.create_all()
        admin = Admin(username='dev', email='dev@church.example.org', role='developer')
        admin.set_password('Secret123!xyz')
        member = Member(full_name='Ama Mensah', email='ama@church.example.org')
        member.set_password('Secret123!xyz')
        _db.session.add_all([admin, member])
        _db.session.commit()
        yield app
        _db.session.remove()


@pytest.fixture
def resend_on(mail_app):
    mail_app.config['RESEND_API_KEY'] = 're_test_123'
    mail_app.config['MAIL_FROM'] = SENDER
    return mail_app


def _resp(status=200, body=None):
    r = mock.Mock()
    r.status_code = status
    r.reason = 'X'
    r.content = b'{}' if body is not None else b''
    r.json.return_value = body if body is not None else {}
    return r


# ------------------------------------------------------------ provider choice

def test_provider_selection(mail_app):
    with mail_app.test_request_context():
        assert email_utils.provider() is None
        mail_app.config['SMTP_HOST'] = 'smtp.example.org'
        assert email_utils.provider() == 'smtp'
        mail_app.config['RESEND_API_KEY'] = 're_x'
        assert email_utils.provider() == 'resend'
        assert resend_client.is_configured()


def test_no_provider_returns_false_without_http(mail_app):
    with mail_app.test_request_context(), mock.patch('requests.request') as req:
        assert email_utils.send_email('a@example.org', 'Hi', 'body') is False
        req.assert_not_called()


# ------------------------------------------------------------ Resend payload

def test_resend_payload_shape(resend_on):
    resend_on.config['MAIL_REPLY_TO'] = 'office@church.example.org'
    with resend_on.test_request_context(), \
            mock.patch('requests.request', return_value=_resp(200, {'id': 'em_1'})) as req:
        ok = email_utils.send_email('a@example.org', 'Hello', 'plain', html='<p>x</p>',
                                    tags=[{'name': 'category', 'value': 't'}],
                                    idempotency_key='k-1')
    assert ok is True
    args, kwargs = req.call_args
    assert args == ('POST', 'https://api.resend.com/emails')
    assert kwargs['timeout'] == 10
    assert kwargs['headers']['Authorization'] == 'Bearer re_test_123'
    assert kwargs['headers']['Idempotency-Key'] == 'k-1'
    assert kwargs['json'] == {
        'from': SENDER, 'to': ['a@example.org'], 'subject': 'Hello',
        'html': '<p>x</p>', 'text': 'plain',
        'reply_to': 'office@church.example.org',
        'tags': [{'name': 'category', 'value': 't'}],
    }


def test_idempotency_key_generated_when_missing(resend_on):
    with resend_on.test_request_context(), \
            mock.patch('requests.request', return_value=_resp(200, {'id': 'e'})) as req:
        email_utils.send_email('a@example.org', 'S', 'b')
    assert req.call_args.kwargs['headers']['Idempotency-Key'].startswith('tag-')


def test_missing_from_does_not_send(resend_on):
    resend_on.config['MAIL_FROM'] = ''
    with resend_on.test_request_context(), mock.patch('requests.request') as req:
        assert email_utils.send_email('a@example.org', 'S', 'b') is False
        req.assert_not_called()


def test_subject_newlines_stripped(resend_on):
    with resend_on.test_request_context(), \
            mock.patch('requests.request', return_value=_resp(200, {'id': 'e'})) as req:
        email_utils.send_email('a@example.org', 'Hi\r\nBcc: x@evil.test', 'b')
    assert '\n' not in req.call_args.kwargs['json']['subject']


# ------------------------------------------------------------ failures/retry

def test_validation_error_returns_false_and_logs_without_body(resend_on, caplog):
    err = _resp(403, {'statusCode': 403, 'name': 'validation_error',
                      'message': 'The domain is not verified.'})
    caplog.set_level(logging.INFO)
    with resend_on.test_request_context(), mock.patch('requests.request', return_value=err) as req:
        assert email_utils.send_email('a@example.org', 'S', 'SECRET-BODY-123') is False
    assert req.call_count == 1  # 4xx is not retried
    assert 'status=403 validation_error' in caplog.text
    assert 'The domain is not verified.' in caplog.text
    assert 'SECRET-BODY-123' not in caplog.text
    assert 're_test_123' not in caplog.text


def test_retry_once_on_5xx_then_success(resend_on):
    seq = [_resp(503, {'name': 'service_unavailable', 'message': 'down'}), _resp(200, {'id': 'e'})]
    with resend_on.test_request_context(), mock.patch('requests.request', side_effect=seq) as req:
        assert email_utils.send_email('a@example.org', 'S', 'b', idempotency_key='same') is True
    assert req.call_count == 2
    keys = {c.kwargs['headers']['Idempotency-Key'] for c in req.call_args_list}
    assert keys == {'same'}


def test_retry_only_once_on_rate_limit(resend_on):
    rl = _resp(429, {'name': 'rate_limit_exceeded', 'message': 'slow down'})
    with resend_on.test_request_context(), mock.patch('requests.request', return_value=rl) as req:
        assert email_utils.send_email('a@example.org', 'S', 'b') is False
    assert req.call_count == 2


def test_quota_429_not_retried(resend_on):
    q = _resp(429, {'name': 'daily_quota_exceeded', 'message': 'quota'})
    with resend_on.test_request_context(), mock.patch('requests.request', return_value=q) as req:
        assert email_utils.send_email('a@example.org', 'S', 'b') is False
    assert req.call_count == 1


def test_network_error_returns_false_without_raising(resend_on):
    with resend_on.test_request_context(), \
            mock.patch('requests.request', side_effect=requests.ConnectionError('boom')) as req:
        assert email_utils.send_email('a@example.org', 'S', 'b') is False
    assert req.call_count == 2  # safe to repeat: carries an Idempotency-Key


def test_client_request_raises_resend_error(resend_on):
    with resend_on.app_context(), \
            mock.patch('requests.request', return_value=_resp(422, {'name': 'invalid_parameter',
                                                                   'message': 'bad'})):
        with pytest.raises(resend_client.ResendError) as ei:
            resend_client.request('POST', '/emails', json={})
    assert ei.value.status == 422 and ei.value.name == 'invalid_parameter'


# ------------------------------------------------------------ reset flows

GENERIC = b'If that email is registered, a reset link has been sent.'


@pytest.mark.parametrize('path,email,audience', [
    ('/members/forgot-password', 'ama@church.example.org', 'member'),
    ('/admin/forgot-password', 'dev@church.example.org', 'admin'),
])
def test_reset_sends_branded_email(resend_on, path, email, audience):
    with mock.patch('requests.request', return_value=_resp(200, {'id': 'e'})) as req:
        r = resend_on.test_client().post(path, data={'email': email}, follow_redirects=True)
    assert GENERIC in r.data
    payload = req.call_args.kwargs['json']
    assert payload['to'] == [email]
    assert f'{SITE}/' in payload['text'] and 'reset-password/' in payload['text']
    assert 'Reset password' in payload['html'] and '#0D2B6B' in payload['html']
    assert '30 minutes' in payload['text']
    assert payload['tags'] == [{'name': 'category', 'value': f'password_reset_{audience}'}]
    assert req.call_args.kwargs['headers']['Idempotency-Key'].startswith('tag-')


@pytest.mark.parametrize('path,email', [
    ('/members/forgot-password', 'ama@church.example.org'),
    ('/members/forgot-password', 'nobody@church.example.org'),
    ('/admin/forgot-password', 'dev@church.example.org'),
    ('/admin/forgot-password', 'nobody@church.example.org'),
])
def test_reset_generic_message_even_when_resend_fails(resend_on, path, email):
    with mock.patch('requests.request', return_value=_resp(500, {'name': 'application_error',
                                                                 'message': 'x'})):
        r = resend_on.test_client().post(path, data={'email': email}, follow_redirects=True)
    assert r.status_code == 200
    assert GENERIC in r.data


def test_no_reset_link_in_logs_when_not_debug(mail_app, caplog):
    caplog.set_level(logging.DEBUG)
    assert not mail_app.debug
    r = mail_app.test_client().post('/members/forgot-password',
                                    data={'email': 'ama@church.example.org'},
                                    follow_redirects=True)
    assert GENERIC in r.data
    assert '[email stub]' in caplog.text
    assert 'reset-password/' not in caplog.text


# ------------------------------------------------------------ notifications

def test_contact_form_notifies_and_survives_email_failure(resend_on):
    resend_on.config['MAIL_NOTIFY_TO'] = 'office@church.example.org'
    body = {'name': 'Kofi', 'email': 'kofi@church.example.org', 'phone': '',
            'subject': 'Hello', 'message': 'A message to the church office.'}
    with mock.patch('app.routes.validate_email', return_value=True), \
            mock.patch('requests.request', side_effect=requests.Timeout('t')) as req:
        r = resend_on.test_client().post('/api/contact-form', json=body)
    assert r.status_code == 201
    payload = req.call_args.kwargs['json']
    assert payload['to'] == ['office@church.example.org']
    assert payload['reply_to'] == 'kofi@church.example.org'


def test_prayer_request_no_notify_when_unset(resend_on):
    body = {'name': 'Esi', 'email': 'esi@church.example.org', 'topic': 'Health',
            'message': 'Please pray for my recovery.'}
    with mock.patch('app.routes.validate_email', return_value=True), \
            mock.patch('requests.request') as req:
        r = resend_on.test_client().post('/api/prayer-request', json=body)
    assert r.status_code == 201
    req.assert_not_called()


def test_template_escapes_user_content(resend_on):
    with resend_on.test_request_context():
        html, text = email_utils.render_transactional(
            'S', 'H', ['p'], details=[('Message', '<script>alert(1)</script>')])
    assert '<script>alert(1)' not in html
    assert f'{SITE}/static/img/logo2.png' in html
