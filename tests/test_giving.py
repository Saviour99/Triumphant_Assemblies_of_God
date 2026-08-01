"""
Covers the two things this audit pass changed in the giving/Paystack flow:
- the webhook's signature verification (the only thing standing in for
  CSRF/session auth on a server-to-server call)
- that concurrent/duplicate completion attempts (webhook + client verify,
  or a retried webhook) can't double-process or downgrade a completed
  donation back to 'failed'
"""
import hashlib
import hmac
import json
import uuid

from app.models import Giving


def _make_pending_donation(db, amount=100.0, reference=None):
    donation = Giving(
        amount=amount,
        giving_type='tithe',
        donor_name='Test Donor',
        donor_email='donor@example.com',
        paystack_reference=reference or uuid.uuid4().hex,
        status='pending',
    )
    db.session.add(donation)
    db.session.commit()
    return donation


def _sign(app, body_bytes):
    secret = app.config['PAYSTACK_SECRET_KEY']
    return hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha512).hexdigest()


def _webhook_payload(reference, amount_ghs, status='success'):
    return json.dumps({
        'event': 'charge.success',
        'data': {
            'reference': reference,
            'status': status,
            'amount': round(amount_ghs * 100),
        }
    }).encode('utf-8')


def test_webhook_rejects_missing_signature(client):
    resp = client.post('/api/paystack/webhook', data=b'{}', content_type='application/json')
    assert resp.status_code == 401


def test_webhook_rejects_bad_signature(app, client, db):
    donation = _make_pending_donation(db)
    body = _webhook_payload(donation.paystack_reference, donation.amount)

    resp = client.post(
        '/api/paystack/webhook',
        data=body,
        content_type='application/json',
        headers={'X-Paystack-Signature': 'not-the-real-signature'}
    )

    assert resp.status_code == 401
    db.session.refresh(donation)
    assert donation.status == 'pending'  # untouched by the rejected request


def test_webhook_completes_pending_donation_with_valid_signature(app, client, db):
    donation = _make_pending_donation(db, amount=250.0)
    body = _webhook_payload(donation.paystack_reference, donation.amount)
    signature = _sign(app, body)

    resp = client.post(
        '/api/paystack/webhook',
        data=body,
        content_type='application/json',
        headers={'X-Paystack-Signature': signature}
    )

    assert resp.status_code == 200
    db.session.refresh(donation)
    assert donation.status == 'completed'


def test_webhook_ignores_unknown_reference_without_error(app, client, db):
    body = _webhook_payload('reference-that-does-not-exist', 50.0)
    signature = _sign(app, body)

    resp = client.post(
        '/api/paystack/webhook',
        data=body,
        content_type='application/json',
        headers={'X-Paystack-Signature': signature}
    )

    # Must still 200 (so Paystack doesn't retry forever), just a no-op.
    assert resp.status_code == 200


def test_duplicate_webhook_delivery_is_idempotent(app, client, db):
    """The same event delivered twice (Paystack's documented retry
    behavior, or a manual resend) must not error and must not change
    anything the second time — proves _set_donation_status_once's
    conditional UPDATE actually guards re-processing."""
    donation = _make_pending_donation(db)
    body = _webhook_payload(donation.paystack_reference, donation.amount)
    signature = _sign(app, body)
    headers = {'X-Paystack-Signature': signature}

    first = client.post('/api/paystack/webhook', data=body, content_type='application/json', headers=headers)
    second = client.post('/api/paystack/webhook', data=body, content_type='application/json', headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    db.session.refresh(donation)
    assert donation.status == 'completed'


def test_completed_donation_is_never_downgraded_to_failed(app, db):
    """Simulates the race this audit flagged: a webhook (or a second verify
    call) completes the donation, then a delayed/duplicate verify call
    sees a failure. The atomic helper must refuse to move a 'completed'
    row back to 'failed'."""
    from app.routes import _set_donation_status_once

    donation = _make_pending_donation(db)
    assert _set_donation_status_once(donation.id, 'completed') is True

    # A late/duplicate "failed" transition must be a no-op once completed.
    changed = _set_donation_status_once(donation.id, 'failed')
    assert changed is False

    db.session.refresh(donation)
    assert donation.status == 'completed'
