"""
Shared pytest fixtures. Tests run against the dedicated `tag_church_test`
database (see config.py::TestingConfig) — never the real app database.

Uses db.create_all()/drop_all() to manage the isolated test schema only.
This is intentionally different from the rest of the project (init_db.py
is additive-only and is the schema source of truth for the real database
per CLAUDE.md) — a throwaway per-test-run schema on a dedicated test DB
doesn't touch real data and is standard pytest practice.
"""
import pytest

from app import create_app, db as _db
from app.models import Admin


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def admin_user(db):
    admin = Admin(username='TestAdmin', email='testadmin@example.com', role='admin')
    admin.set_password('TestPassword123!')
    db.session.add(admin)
    db.session.commit()
    return admin


@pytest.fixture
def logged_in_admin_client(client, admin_user):
    client.post('/admin/login', data={
        'email': admin_user.email,
        'password': 'TestPassword123!',
    })
    return client
