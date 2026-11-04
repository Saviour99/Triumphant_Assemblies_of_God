# Triumphant Assemblies of God — Church Management System

Public church website + admin dashboard for Triumphant Assemblies of God
Ghana (Accra, Dansoman, between Atomic and Glefe).

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

## Non-negotiable: dependency tracking

**Any package installed (via `pip install`, etc.) must be added to
`requirements.txt` in the same change — never leave an install untracked.**
`requirements.txt` is the single source of truth for what this project
needs; a dependency that works locally but is missing from it will fail
the moment someone else (or a fresh deploy) runs `pip install -r
requirements.txt`. Pin the version actually installed, and note what it's
for with a short comment if it's not obvious from context.

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

`Admin.role` is one of `'admin' | 'developer' | 'pastor'` (plain
`VARCHAR(20)`, no DB-level enum), shown as a colored badge (gold/admin,
blue/developer, green/pastor).

**Per-section permissions.** The admin dashboard is split into section
keys, grouped like the sidebar (`ADMIN_SECTION_GROUPS` in `app/models.py`):
Overview — `dashboard`, `giving`, `live_stream`; People — `members`,
`prayer_requests`, `messages`, `newsletter`; Content — `video_sermons`,
`audio_sermons`, `devotions`, `ebooks`, `testimonies`, `events`.
- Developer and Pastor always have every section (`Admin.permissions` is
  ignored/NULL for them). Pastor = full content access, but no account
  management.
- Role `admin` gets exactly the sections in `admins.permissions` (TEXT,
  JSON list of keys). New admins default to `['dashboard']`. **NULL means
  "role default"**: a legacy `admin` row with NULL keeps full access to all
  sections (what it had before permissions existed) until the developer
  saves its access once.
- `Admin.can(key)` / `Admin.permission_list` are the single source of
  truth; templates use `current_user.can('members')`.
- Enforcement is server-side: every section route uses
  `@permission_required('<key>')` (`app/decorators.py`) — a denied admin
  is flashed and redirected to the dashboard (JSON `/admin/api/*` → 403).
  `/admin/dashboard` itself stays open to any active admin (it's the
  landing page); without `dashboard` it shows only links to their
  sections. With `dashboard`, each figure/chart/list is limited to sections
  the admin has — `/admin/api/chart-data` and `/admin/api/recent-activity`
  filter the same way and are cached per permission set
  (`_permission_cache_key`), so admins never share a cached payload.
  The sidebar hides links the account can't use. Any new admin route must
  get a `@permission_required(...)` (or `@developer_required`).

**Account management** (`app/admin_manage.py` routes on `admin_bp`,
`@developer_required`): `/admin/accounts` lists accounts; Add admin
(name, email, role, temporary password via the in-page generator, active
toggle, section checkboxes); the account edit page has an Access panel
(role, active, sections) and an Access history table. Accounts are never
deleted — `admins.is_active` (`Admin.is_active_account`) soft-deactivates
them: `login_user()` refuses them and the admin decorators sign out a
deactivated admin on their next request. Lockout guard: a developer can't
demote or deactivate themselves, and at least one active developer must
always remain. Every create/role/sections/activation change is written to
`admin_account_logs` (`AdminAccountLog`: whose account, who changed it,
action, details, when). The three original accounts are still seeded once
by `init_db.py` from `.env` (`ADMIN_DEFAULT_*` / `DEVELOPER_DEFAULT_*` /
`PASTOR_DEFAULT_*`), each with a hardcoded fallback default.

- `app/decorators.py`: `@admin_required` / `@member_required`, layered on
  top of Flask-Login's session handling, so a logged-in Member can't hit
  `/admin/*` and vice versa. `@permission_required(section_key)` adds the
  per-section check above. `@developer_required` is stricter still —
  only `role == 'developer'` passes, used for account management and the
  login-audit log.
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
  sermons, devotions, live-stream toggle, giving overview. Account
  management (add/access/activate), testimonies and events routes live in
  `app/admin_manage.py`, registered on the same `admin_bp` (imported at the
  bottom of `app/admin.py`).
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
      pruning (`app/admin.py::devotion_add`). The pre-check is TOCTOU-racy
      by nature (two admins could both pass it before either commits) —
      the DB `UNIQUE` constraint is the real guardrail; the commit is
      wrapped in `try/except IntegrityError` so a genuine race ends in a
      clean flash message, not a 500.
- [x] Paystack giving: `Giving` extended in place (`paystack_reference`
      has a DB `UNIQUE` constraint, `status`, `member_id`).
      `/api/giving/init` creates the pending row. Two independent paths
      can mark it `completed`, and both go through
      `app/routes.py::_set_donation_status_once` (a single conditional
      `UPDATE ... WHERE status IN (...)`, never a Python read-then-write)
      so they can't double-process or race each other:
      - `/api/paystack/verify` — client-triggered after the Inline JS
        popup closes; calls Paystack's verify-transaction API before
        trusting anything. Best-effort — the browser might never call it.
      - `/api/paystack/webhook` — server-to-server, authoritative
        fallback for when the browser doesn't call verify (closed tab,
        dropped network). Trusts the payload only after checking the
        `X-Paystack-Signature` header (HMAC-SHA512 over the raw body with
        `PAYSTACK_SECRET_KEY`); exempted from CSRF (no session on a
        server-to-server call — the signature is the auth) and from
        rate-limiting (exempted via `@limiter.exempt`, since it's Paystack
        calling in, not a public user). To use this in production, add
        `https://<your-domain>/api/paystack/webhook` as the webhook URL
        in the Paystack dashboard.
- [x] Contact page map (keyless Google Maps embed, real address — no
      invented coordinates) + "Get Directions" via `navigator.geolocation`
- [x] Newsletter via Mailchimp (`app/admin_newsletter.py` routes on
      `admin_bp`, `app/mailchimp.py` Marketing API v3 client via
      `requests`, `app/newsletter_render.py` + `templates/email/
      newsletter.html`). Admin writes plain text (escaped, then blank
      line = paragraph, "- " = bullet, bare URLs linked, `**bold**`);
      it's rendered into the branded email with live preview, saved as a
      `newsletter_campaigns` draft, test-sent to the writer, then sent to
      the whole audience after a confirm page. Send first syncs local
      `newsletter_subscribers` (batch, `update_existing: false` so
      Mailchimp unsubscribes stick), reply-to = the sending admin's email
      (free-mail → `MAILCHIMP_REPLY_TO` fallback). Double-send guard:
      conditional `UPDATE ... WHERE status IN ('draft','failed')` →
      `sending`, same pattern as `_set_donation_status_once`. Env:
      `MAILCHIMP_API_KEY`, `MAILCHIMP_AUDIENCE_ID`, `SITE_URL` required;
      `MAILCHIMP_SERVER_PREFIX`/`_FROM_NAME`/`_REPLY_TO` optional —
      without them drafting/preview still works, sending is disabled.
- [x] CSRF on every POST route/form; parameterized queries via the ORM

## Location

"Triumphant Assemblies of God Ghana" — Dansoman, between Atomic and Glefe,
Accra, Ghana. Used as the literal address string for the contact-page map
and directions link (`app/templates/public/contact.html`) — don't invent
lat/lng coordinates for it.
