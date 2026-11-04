"""
Giving thank-you / receipt page (/giving/thank-you): renders each state,
never leaks donor PII, and sends the no-store / noindex headers.
"""
import uuid

import pytest

from app.models import Giving

DONOR_NAME = 'Abena Mensah-Boateng'
DONOR_EMAIL = 'abena.private@example.com'


def _donation(db, status):
    d = Giving(
        amount='1234.50', giving_type='building_fund',
        donor_name=DONOR_NAME, donor_email=DONOR_EMAIL,
        paystack_reference=uuid.uuid4().hex, status=status,
    )
    db.session.add(d)
    db.session.commit()
    return d


def _assert_private(html):
    assert DONOR_EMAIL not in html
    assert 'Mensah' not in html
    assert 'Boateng' not in html


def _assert_headers(resp):
    assert resp.status_code == 200
    assert resp.headers['Cache-Control'] == 'no-store'
    assert 'noindex' in resp.headers['X-Robots-Tag']
    html = resp.get_data(as_text=True)
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert 'onclick=' not in html.lower()


@pytest.mark.parametrize('status,heading', [
    ('completed', 'Thank you, Abena'),
    ('pending', 'confirming your payment'),
    ('failed', "didn't go through"),
])
def test_states_render_without_pii(client, db, status, heading):
    d = _donation(db, status)
    resp = client.get(f'/giving/thank-you?reference={d.paystack_reference}')
    _assert_headers(resp)
    html = resp.get_data(as_text=True)
    assert heading in html
    assert 'GH₵&nbsp;1,234.50' in html
    assert 'Building Fund' in html
    assert d.paystack_reference in html
    _assert_private(html)
    if status == 'completed':
        assert '2 Corinthians 9:7' in html and 'payPrint' in html
    if status == 'pending':
        assert 'data-verify-url="/api/paystack/verify"' in html and 'payCheckAgain' in html
    if status == 'failed':
        assert 'Try again' in html


@pytest.mark.parametrize('ref', ['', 'does-not-exist', 'bad ref!', "x' OR 1=1--", 'a' * 101])
def test_unknown_or_invalid_reference_is_generic(client, db, ref):
    _donation(db, 'completed')
    resp = client.get('/giving/thank-you', query_string={'reference': ref})
    _assert_headers(resp)
    html = resp.get_data(as_text=True)
    assert "couldn't find that payment" in html
    assert 'GH₵' not in html
    _assert_private(html)
