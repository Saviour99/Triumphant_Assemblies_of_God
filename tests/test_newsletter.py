"""
Newsletter / Mailchimp tests. Self-contained: they run against a throwaway
SQLite file in pytest's tmp_path (not the MySQL test DB the other tests
use), and every Mailchimp HTTP call is mocked — nothing touches the network.
"""
from unittest import mock

import pytest
import requests

import config as config_module
from app import create_app, db as _db
from app import mailchimp
from app.models import Admin, NewsletterCampaign, NewsletterSubscriber
from app.newsletter_render import format_body, is_http_url, render_email

MC_ENV = {
    'MAILCHIMP_API_KEY': 'abc123-us21',
    'MAILCHIMP_AUDIENCE_ID': 'aud1',
    'SITE_URL': 'https://church.example.org',
    'MAILCHIMP_REPLY_TO': '',
    'MAILCHIMP_SERVER_PREFIX': '',
}


@pytest.fixture
def nl_app(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.TestingConfig, 'SQLALCHEMY_DATABASE_URI',
                        f"sqlite:///{tmp_path / 'nl.db'}")
    # The installed Flask-Caching may be newer than the pin and reject the
    # legacy 'simple' alias; the class name works on every version.
    monkeypatch.setattr(config_module.TestingConfig, 'CACHE_TYPE', 'SimpleCache')
    app = create_app('testing')
    app.config['RATELIMIT_ENABLED'] = False
    for k in MC_ENV:
        app.config[k] = ''
    with app.app_context():
        _db.create_all()
        admin = Admin(username='pastor', email='pastor@church.example.org', role='pastor')
        admin.set_password('Secret123!')
        _db.session.add(admin)
        _db.session.add_all([NewsletterSubscriber(email='a@example.com'),
                             NewsletterSubscriber(email='b@example.com')])
        _db.session.commit()
        yield app
        _db.session.remove()


@pytest.fixture
def admin_client(nl_app):
    c = nl_app.test_client()
    r = c.post('/admin/login', data={'email': 'pastor@church.example.org', 'password': 'Secret123!'})
    assert r.status_code == 302
    return c


def _resp(status=200, body=None):
    r = mock.Mock()
    r.status_code = status
    r.ok = 200 <= status < 300
    r.content = b'' if body is None else b'x'
    r.json.return_value = body
    if body is None:
        r.json.side_effect = ValueError
    return r


# ============ app/mailchimp.py ============

def test_server_prefix_and_missing_keys(nl_app):
    assert mailchimp.missing_keys() == ['MAILCHIMP_API_KEY', 'MAILCHIMP_AUDIENCE_ID', 'SITE_URL']
    nl_app.config.update(MC_ENV)
    assert mailchimp.server_prefix() == 'us21'
    assert mailchimp.is_configured()
    nl_app.config['MAILCHIMP_SERVER_PREFIX'] = 'us5'
    assert mailchimp.server_prefix() == 'us5'
    nl_app.config.update(MAILCHIMP_SERVER_PREFIX='', MAILCHIMP_API_KEY='nodash')
    assert 'MAILCHIMP_SERVER_PREFIX' in mailchimp.missing_keys()


def test_not_configured_raises_without_http(nl_app):
    with mock.patch('app.mailchimp.requests.request') as req:
        with pytest.raises(mailchimp.MailchimpError):
            mailchimp.send('c1')
        req.assert_not_called()


def test_batch_subscribe_chunks_and_never_updates_existing(nl_app):
    nl_app.config.update(MC_ENV)
    emails = [f'u{i}@example.com' for i in range(1203)] + ['U0@example.com', '']
    with mock.patch('app.mailchimp.requests.request',
                    return_value=_resp(200, {'total_created': 1, 'total_updated': 0,
                                             'error_count': 0, 'errors': []})) as req:
        totals = mailchimp.batch_subscribe(emails)
    assert req.call_count == 3  # 500 + 500 + 203 (dupes/blank dropped)
    sizes = [len(c.kwargs['json']['members']) for c in req.call_args_list]
    assert sizes == [500, 500, 203]
    for c in req.call_args_list:
        assert c.args[0] == 'POST'
        assert c.args[1] == 'https://us21.api.mailchimp.com/3.0/lists/aud1'
        assert c.kwargs['json']['update_existing'] is False
        assert c.kwargs['json']['members'][0]['status_if_new'] == 'subscribed'
        assert c.kwargs['auth'] == ('anystring', 'abc123-us21')
        assert c.kwargs['timeout']
    assert totals['new'] == 3


def test_error_detail_is_surfaced(nl_app):
    nl_app.config.update(MC_ENV)
    body = {'title': 'Invalid Resource', 'status': 400, 'detail': 'The campaign is not ready to send.',
            'errors': [{'field': 'reply_to', 'message': 'domain not verified'}]}
    with mock.patch('app.mailchimp.requests.request', return_value=_resp(400, body)):
        with pytest.raises(mailchimp.MailchimpError) as exc:
            mailchimp.send('c1')
    assert 'The campaign is not ready to send.' in exc.value.detail
    assert 'reply_to: domain not verified' in exc.value.detail
    assert exc.value.status == 400


def test_timeout_and_network_errors(nl_app):
    nl_app.config.update(MC_ENV)
    with mock.patch('app.mailchimp.requests.request', side_effect=requests.Timeout):
        with pytest.raises(mailchimp.MailchimpError, match='too long'):
            mailchimp.get_campaign('c1')
    with mock.patch('app.mailchimp.requests.request', side_effect=requests.ConnectionError):
        with pytest.raises(mailchimp.MailchimpError, match='reach Mailchimp'):
            mailchimp.get_campaign('c1')


def test_send_204_and_campaign_payload(nl_app):
    nl_app.config.update(MC_ENV)
    with mock.patch('app.mailchimp.requests.request', return_value=_resp(204)) as req:
        assert mailchimp.send('c1') == {}
    assert req.call_args.args[1].endswith('/campaigns/c1/actions/send')
    with mock.patch('app.mailchimp.requests.request', return_value=_resp(200, {'id': 'c9'})) as req:
        mailchimp.create_campaign('Hello', 'pre', 'Title', 'pastor@church.example.org')
    payload = req.call_args.kwargs['json']
    assert payload['type'] == 'regular'
    assert payload['recipients'] == {'list_id': 'aud1'}
    assert payload['settings']['reply_to'] == 'pastor@church.example.org'
    assert payload['settings']['from_name'] == 'Triumphant Assemblies of God'


def test_choose_reply_to(nl_app):
    assert mailchimp.choose_reply_to('p@church.org') == ('p@church.org', None)
    addr, hint = mailchimp.choose_reply_to('p@gmail.com')
    assert addr == 'p@gmail.com' and 'MAILCHIMP_REPLY_TO' in hint
    nl_app.config['MAILCHIMP_REPLY_TO'] = 'office@church.org'
    addr, hint = mailchimp.choose_reply_to('p@Gmail.com')
    assert addr == 'office@church.org' and hint


# ============ rendering ============

def test_format_body_escapes_and_formats(nl_app):
    with nl_app.test_request_context():
        html = str(format_body(
            'Hello <script>alert(1)</script> **friends**\n\n- one\n- two https://x.org/a?b=1&c=2.\n\n'
            'Bad javascript:alert(1) "quote"'))
    assert '<script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<strong>friends</strong>' in html
    assert html.count('<li ') == 2
    assert 'href="https://x.org/a?b=1&amp;c=2"' in html  # trailing "." not in link
    assert 'href="javascript' not in html
    assert '&#34;quote&#34;' in html


def test_is_http_url():
    assert is_http_url('https://example.org/x')
    assert not is_http_url('javascript:alert(1)')
    assert not is_http_url('https://')
    assert not is_http_url('ftp://example.org')


def test_email_template_merge_tags_and_absolute_logo(nl_app):
    nl_app.config.update(MC_ENV)
    with nl_app.test_request_context():
        html = render_email('Sub <b>', 'Body', cta_label='Go', cta_url='https://x.org')
        prev = render_email('Sub', 'Body', for_preview=True)
        bad = render_email('Sub', 'Body', cta_label='Go', cta_url='javascript:alert(1)')
    assert '*|UNSUB|*' in html and '*|LIST:ADDRESSLINE|*' in html and '*|REWARDS|*' in html
    assert 'src="https://church.example.org/static/img/logo2.png"' in html
    assert 'Sub &lt;b&gt;' in html and 'Sub <b>' not in html
    assert 'Dansoman, between Atomic and Glefe, Accra, Ghana' in html
    assert 'v:roundrect' in html and 'href="https://x.org"' in html
    assert '*|UNSUB|*' not in prev
    assert 'javascript:' not in bad


# ============ admin routes ============

def test_newsletter_landing_and_compose_render(admin_client):
    r = admin_client.get('/admin/newsletter-subscribers')
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "Mailchimp isn't connected yet" in page and 'MAILCHIMP_API_KEY' in page
    assert 'Write a newsletter' in page
    r = admin_client.get('/admin/newsletter/compose')
    assert r.status_code == 200 and 'previewFrame' in r.get_data(as_text=True)


def test_preview_escapes_script(admin_client):
    r = admin_client.post('/admin/newsletter/preview', data={
        'subject': '<script>alert("s")</script>', 'body_text': 'Hi <script>alert(1)</script>'})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '<script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html


def test_save_draft_validates_cta(admin_client, nl_app):
    r = admin_client.post('/admin/newsletter/compose', data={
        'action': 'save', 'subject': 'Hi', 'body_text': 'Body',
        'cta_label': 'Go', 'cta_url': 'javascript:alert(1)'})
    assert r.status_code == 200 and 'http:// or https://' in r.get_data(as_text=True)
    r = admin_client.post('/admin/newsletter/compose', data={
        'action': 'save', 'subject': 'Hi', 'body_text': 'Body', 'cta_label': 'Go',
        'cta_url': 'https://x.org'})
    assert r.status_code == 302
    c = NewsletterCampaign.query.one()
    assert c.status == 'draft' and c.author_admin_id is not None
    r = admin_client.get(f'/admin/newsletter/{c.id}')
    assert r.status_code == 200
    assert 'disabled' in r.get_data(as_text=True)  # send buttons off without Mailchimp


def _draft():
    c = NewsletterCampaign(subject='Sunday', body_text='Come!', status='draft')
    _db.session.add(c)
    _db.session.commit()
    return c.id


def test_send_flow_and_no_double_send(admin_client, nl_app):
    nl_app.config.update(MC_ENV)
    cid = _draft()

    calls = []

    def fake(method, url, **kw):
        calls.append((method, url.split('/3.0')[1], kw.get('json')))
        if url.endswith('/lists/aud1') and method == 'POST':
            return _resp(200, {'total_created': 2, 'total_updated': 0, 'error_count': 0, 'errors': []})
        if url.endswith('/campaigns') and method == 'POST':
            return _resp(200, {'id': 'mc1', 'recipients': {'recipient_count': 2}})
        if url.endswith('/content'):
            return _resp(200, {'html': '...'})
        if url.endswith('/actions/send'):
            return _resp(204)
        raise AssertionError(url)

    # Without the confirmation tick nothing happens.
    with mock.patch('app.mailchimp.requests.request', side_effect=fake):
        r = admin_client.post(f'/admin/newsletter/{cid}/send', data={})
    assert r.status_code == 302 and not calls

    with mock.patch('app.mailchimp.requests.request', side_effect=fake):
        r = admin_client.post(f'/admin/newsletter/{cid}/send', data={'confirm': 'yes'})
        r2 = admin_client.post(f'/admin/newsletter/{cid}/send', data={'confirm': 'yes'})
    assert r.status_code == 302 and r2.status_code == 302
    sends = [c for c in calls if c[1].endswith('/actions/send')]
    assert len(sends) == 1
    content = next(c for c in calls if c[1].endswith('/content'))
    assert '*|UNSUB|*' in content[2]['html']
    create = next(c for c in calls if c[1] == '/campaigns')
    assert create[2]['settings']['reply_to'] == 'pastor@church.example.org'
    c = _db.session.get(NewsletterCampaign, cid)
    _db.session.refresh(c)
    assert c.status == 'sent' and c.mailchimp_campaign_id == 'mc1' and c.recipient_count == 2


def test_send_failure_marks_failed_with_detail(admin_client, nl_app):
    nl_app.config.update(MC_ENV)
    cid = _draft()
    err = _resp(400, {'title': 'Bad', 'detail': 'Your audience has no physical address.'})
    with mock.patch('app.mailchimp.requests.request', return_value=err):
        r = admin_client.post(f'/admin/newsletter/{cid}/send', data={'confirm': 'yes'},
                              follow_redirects=True)
    assert 'Your audience has no physical address.' in r.get_data(as_text=True)
    c = _db.session.get(NewsletterCampaign, cid)
    _db.session.refresh(c)
    assert c.status == 'failed' and 'physical address' in c.error


def test_csrf_required_on_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.TestingConfig, 'SQLALCHEMY_DATABASE_URI',
                        f"sqlite:///{tmp_path / 'csrf.db'}")
    monkeypatch.setattr(config_module.TestingConfig, 'WTF_CSRF_ENABLED', True)
    monkeypatch.setattr(config_module.TestingConfig, 'CACHE_TYPE', 'SimpleCache')
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        r = app.test_client().post('/admin/newsletter/preview', data={'subject': 'x'})
        assert r.status_code == 400
        _db.session.remove()


def test_linkify_cannot_inject_attributes_or_schemes(nl_app):
    cases = [
        'https://x.org/"onmouseover="alert(1)',
        "https://x.org/a'onclick='alert(1)",
        'https://x.org/`x` https://x.org/<img src=x onerror=alert(1)>',
        'javascript:alert(1) JaVaScRiPt:alert(2) data:text/html;base64,PHNjcmlwdD4=',
        'vbscript:msgbox(1) <a href="javascript:alert(3)">x</a>',
        '**<img src=x onerror=alert(4)>** and **"bold"**',
        'https://x.org/?q=&quot;&lt;',
    ]
    with nl_app.test_request_context():
        out = [str(format_body(c)) for c in cases]
    joined = '\n'.join(out)
    assert '<img' not in joined and '<script' not in joined
    assert 'href="javascript' not in joined.lower()
    assert 'href="data:' not in joined and 'href="vbscript' not in joined
    assert 'onmouseover="' not in joined and "onclick='" not in joined
    # Each generated href is a single http(s) URL with no quote/bracket in it.
    import re
    for href in re.findall(r'href="([^"]*)"', joined):
        assert href.startswith(('https://', 'http://'))
        assert not set('<>"\'`') & set(href)
    assert 'href="https://x.org/"' in out[0] and '&#34;onmouseover=&#34;alert(1)' in out[0]
    assert '<strong>&lt;img src=x onerror=alert(4)&gt;</strong>' in out[5]
    assert '<strong>&#34;bold&#34;</strong>' in out[5]
    assert 'href="https://x.org/?q=&amp;quot;&amp;lt"' in out[6]  # trailing ";" is punctuation
