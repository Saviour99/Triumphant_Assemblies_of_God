"""
Covers the devotion_add TOCTOU fix: the "already posted today?" check is a
separate query from the commit, so a genuine race (two admins, or a
double-submit) must end in a clean redirect + flash message via the DB's
UNIQUE constraint on devotion_date, not an unhandled 500.
"""
from datetime import date

from app.models import Devotion


def _devotion_form_data(title='Test Devotion'):
    return {
        'title': title,
        'quote': 'Test quote',
        'quote_theme': 'Test Theme',
        'writer_name': 'Test Writer',
        'reflection': 'Test reflection body.',
        'prayer_points': 'Point one\nPoint two',
        'declaration': 'Test declaration.',
    }


def test_devotion_add_succeeds_when_none_posted_today(logged_in_admin_client, db):
    resp = logged_in_admin_client.post(
        '/admin/devotions/add', data=_devotion_form_data(), follow_redirects=True
    )
    assert resp.status_code == 200
    assert Devotion.query.filter_by(devotion_date=date.today()).count() == 1


def test_devotion_add_race_returns_clean_error_not_500(logged_in_admin_client, db, monkeypatch):
    """Simulates the actual TOCTOU window the fix targets: the route's
    "already posted today?" pre-check has to see nothing (as it would if a
    concurrent admin's insert lands *after* that check but *before* this
    request's commit), while the database genuinely already has a row for
    today by commit time — so the UNIQUE constraint on devotion_date fires
    for real, and the try/except must turn that into a clean redirect
    instead of a 500.

    Only the pre-check is faked (via monkeypatch); the INSERT, the UNIQUE
    violation, and the except/rollback all run for real against the test
    database."""
    winner = Devotion(
        title='Already Posted', quote='q', quote_theme='t', writer_name='w',
        reflection='r', declaration='d', devotion_date=date.today()
    )
    db.session.add(winner)
    db.session.commit()

    from unittest.mock import MagicMock
    mock_query = MagicMock()
    mock_query.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(Devotion, 'query', mock_query)

    resp = logged_in_admin_client.post(
        '/admin/devotions/add', data=_devotion_form_data('Racing Devotion')
    )

    assert resp.status_code == 302  # not a 500
    assert resp.headers['Location'].endswith('/admin/devotions')

    monkeypatch.undo()  # restore the real Devotion.query before following the redirect

    followed = logged_in_admin_client.get(resp.headers['Location'])
    assert b'already posted' in followed.data.lower()


def test_devotion_add_race_does_not_insert_the_losing_row(logged_in_admin_client, db, monkeypatch):
    """Same race as above — confirms the loser's row genuinely never
    landed (the rollback actually rolled back), not just that the response
    looked clean."""
    winner = Devotion(
        title='Already Posted', quote='q', quote_theme='t', writer_name='w',
        reflection='r', declaration='d', devotion_date=date.today()
    )
    db.session.add(winner)
    db.session.commit()

    from unittest.mock import MagicMock
    mock_query = MagicMock()
    mock_query.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(Devotion, 'query', mock_query)

    logged_in_admin_client.post('/admin/devotions/add', data=_devotion_form_data('Racing Devotion'))

    monkeypatch.undo()  # restore the real Devotion.query before asserting

    assert Devotion.query.filter_by(devotion_date=date.today()).count() == 1
    assert Devotion.query.filter_by(title='Racing Devotion').count() == 0
