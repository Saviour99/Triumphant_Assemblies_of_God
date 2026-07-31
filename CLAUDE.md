# Triumphant Assemblies of God — Church Management System

Public church website + admin dashboard for Triumphant Assemblies of God
Ghana (Accra, Zuman area, between Atomic and Glefe).

## Tech stack (authoritative — not Django)

The original product spec was written with Django-flavored language. This
repo is, and stays, **Flask**:

- **Backend**: Flask 2.3, application-factory pattern (`app/__init__.py`).
- **ORM**: Flask-SQLAlchemy (`app/models.py`). MySQL via PyMySQL (installed
  as a drop-in `MySQLdb` replacement).
- **Auth**: Flask-Login (two model classes, one login manager — see below),
  Flask-WTF for CSRF + forms, `werkzeug.security` for password hashing.
- **Frontend**: Jinja2 templates, Bootstrap 5, vanilla JS, Chart.js (admin
  dashboard, via CDN). Gold (`#C8973A`) / royal blue (`#0D2B6B`) theme —
  see `app/static/css/style.css` custom properties.
- **Payments**: Paystack, called directly via `requests` (no SDK).
- **Schema bootstrap**: `init_db.py` (raw `MySQLdb`, additive only). Not
  Alembic/Flask-Migrate — deliberately skipped, see below.

If you're asked to implement something from the original spec and it says
"Django," translate it into the Flask equivalent instead of introducing a
second framework.

## Non-negotiable: data safety

**No code may ever `DROP` or `TRUNCATE` a table**, in `init_db.py`, in a
migration, in an admin route, anywhere. All deletes operate on a single
record. Prefer soft delete (see `Member.is_active_member`) where the row
might be referenced elsewhere (e.g. a member with donation history);
hard-delete single rows only when nothing else references them (e.g.
`VideoSermon`, `AudioSermon`). Bulk pruning (e.g. the devotion 60-record
cap) must be a single bounded `DELETE ... WHERE id IN (...)` targeting only
the specific excess rows — never a loop of admin-triggered deletes framed
as "clean up everything," never `TRUNCATE`.

This is enforced by a Claude Code hook in `.claude/settings.json` that
blocks Bash commands and Edit/Write file changes containing
`DROP TABLE` / `DROP DATABASE` / `TRUNCATE`. If the hook fires and you
believe it's a false positive, stop and ask rather than working around it.

## Schema bootstrap: `init_db.py` is canonical

`init_db.py` is a standalone script (not part of the Flask app) that
`CREATE DATABASE IF NOT EXISTS`s and then additively creates/alters tables.
`app/models.py` is a hand-maintained SQLAlchemy mirror of the same tables —
**keep the two in sync by hand** when you add a column or table. There is
no `db.create_all()` anywhere in the app lifecycle and no Alembic/
Flask-Migrate; this is a single-developer project and additive raw SQL is
simpler to audit against the no-DROP rule than a migrations framework. Run
`python init_db.py` after changing either file (it's idempotent).

## Auth architecture

Two separate model classes — `Admin` and `Member` (`app/models.py`) — share
one `flask_login.LoginManager`. Each model's `get_id()` returns a
compound id (`"admin:<id>"` / `"member:<id>"`); the shared `user_loader` in
`app/__init__.py` dispatches on the prefix. This exists because Admin and
Member are structurally different (separate login pages, separate
password-reset flows, near-zero field overlap) — don't collapse them into
a single `User(role)` table.

- `app/decorators.py`: `@admin_required` / `@member_required`, layered on
  top of Flask-Login's session handling, so a logged-in Member can't hit
  `/admin/*` and vice versa.
- Admin sessions get a shorter idle timeout (`ADMIN_SESSION_LIFETIME` in
  `config.py`, enforced in `app/__init__.py`'s `before_request` hook) than
  the general 7-day member session.
- Password reset (`app/admin.py`, `app/auth.py`): `itsdangerous`
  time-limited tokens (1hr) + `app/email_utils.py::send_email()`. No SMTP
  is configured for this project yet — by default the reset link is
  logged (and flashed in debug mode) instead of emailed. Set `SMTP_HOST`
  in `.env` to send real email; no code changes needed.

## Blueprints

- `main_bp` / `api_bp` (`app/routes.py`) — public site + JSON API.
- `admin_bp` (`app/admin.py`, `/admin` prefix) — dashboard, member mgmt,
  sermons, devotions, live-stream toggle, giving overview.
- `auth_bp` (`app/auth.py`, `/members` prefix) — member register/login/
  logout/profile/password-reset.

## Feature checklist (spec → implementation)

- [x] Admin login (dedicated page, session timeout, forgot password)
- [x] Member registration/login/profile/password-reset on the public site
- [x] "Go Live" toggle (`LiveStreamSetting`, singleton row, `admin_bp`) —
      public live-stream section on the homepage only renders when live
- [x] Member management (admin CRUD, soft delete, profile + donation
      history view)
- [x] Video sermon management (YouTube URL, title, preacher, date,
      message, delete)
- [x] Audio sermon management (upload, delete, single-track playback via
      `main.js`)
- [x] Dashboard stats (`admin/dashboard.html` + `/admin/api/chart-data`):
      total members, total donations, donation trend + member growth
      charts, recent registrations/donations
- [x] Daily devotion management: one per day (app-level pre-check + DB
      `UNIQUE` constraint on `devotion_date`), auto-set date, latest-60
      pruning (`app/admin.py::devotion_add`)
- [x] Paystack giving: `Giving` extended in place (`paystack_reference`,
      `status`, `member_id`), `/api/giving/init` + `/api/paystack/verify`
      (server-side verification only — browser callback is never trusted)
- [x] Contact page map (keyless Google Maps embed, real address — no
      invented coordinates) + "Get Directions" via `navigator.geolocation`
- [x] CSRF on every POST route/form; parameterized queries via the ORM

## Location

"Triumphant Assemblies of God Ghana" — Zuman, between Atomic and Glefe,
Accra, Ghana. Used as the literal address string for the contact-page map
and directions link (`app/templates/public/contact.html`) — don't invent
lat/lng coordinates for it.
